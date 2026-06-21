#!/usr/bin/env python3
"""
VALEN — Orquestrador Multiagente Assíncrono de Desenvolvimento de Software.

Uma CLI estilo Claude Code: um prompt central dispara, em paralelo, três
subagentes especialistas (Backend Elixir/Phoenix, Frontend multiplataforma e
QA/ExUnit) que consomem a API da Anthropic via asyncio. Os resultados convergem
para um nó de consolidação (`bundle_processed_data`) que valida os artefatos em
disco, roda um linter básico e exibe um status de sucesso no terminal.

Funciona em Linux, macOS, Windows e Termux (Android).

Uso:
    export ANTHROPIC_API_KEY="sua-chave"
    python valen.py --prompt "Um app de lista de tarefas com autenticação"
    # ou, interativo:
    python valen.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- SDK da Anthropic -------------------------------------------------------
try:
    import anthropic
except ImportError:  # pragma: no cover - mensagem amigável
    print(
        "Dependências ausentes. Rode:  pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Backend aiohttp (alta concorrência). Opcional: cai para httpx no Termux.
try:
    from anthropic import DefaultAioHttpClient  # type: ignore

    _HAS_AIOHTTP = True
except Exception:  # pragma: no cover - depende do ambiente
    DefaultAioHttpClient = None  # type: ignore
    _HAS_AIOHTTP = False

from agents import ALL_AGENTS, FILE_CLOSE, FILE_OPEN, Agent

console = Console()

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_EFFORT = "high"
MAX_TOKENS = 32000  # streaming obrigatório para valores altos (ver get_final_message)


# ===========================================================================
# Estado e resultados
# ===========================================================================

@dataclass
class AgentRun:
    """Estado vivo + resultado de um subagente durante a execução."""

    agent: Agent
    status: str = "aguardando"  # aguardando | pensando | gerando | concluído | erro
    tokens_in: int = 0
    tokens_out: int = 0
    files: list[Path] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - self.started_at


# ===========================================================================
# Parsing do protocolo de arquivos
# ===========================================================================

_FILE_BLOCK_RE = re.compile(
    re.escape(FILE_OPEN) + r"\s*(?P<path>.+?)\s*===\s*\n"
    r"(?P<body>.*?)"
    r"(?:\n)?" + re.escape(FILE_CLOSE),
    re.DOTALL,
)


def _safe_relpath(raw: str) -> Path | None:
    """Sanitiza o caminho proposto pelo modelo, barrando path traversal.

    Retorna um Path relativo seguro, ou None se o caminho escapar da raiz.
    """
    candidate = raw.strip().strip("/").replace("\\", "/")
    if not candidate or candidate in (".", ".."):
        return None
    p = Path(candidate)
    # Rejeita absolutos e qualquer componente '..'.
    if p.is_absolute() or any(part == ".." for part in p.parts):
        return None
    return p


def parse_and_write_files(raw_text: str, dest_root: Path) -> list[Path]:
    """Extrai blocos do protocolo e grava cada arquivo sob `dest_root`.

    Confina toda escrita à `dest_root` (canonicalização + verificação).
    Retorna a lista de arquivos efetivamente escritos.
    """
    written: list[Path] = []
    dest_root = dest_root.resolve()

    for match in _FILE_BLOCK_RE.finditer(raw_text):
        rel = _safe_relpath(match.group("path"))
        if rel is None:
            continue
        target = (dest_root / rel).resolve()
        # Defesa final: o alvo precisa permanecer dentro da raiz do agente.
        if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
            continue
        body = match.group("body")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(target)

    return written


# ===========================================================================
# Execução de um agente (streaming assíncrono)
# ===========================================================================

async def run_agent(
    client: "anthropic.AsyncAnthropic",
    run: AgentRun,
    user_prompt: str,
    session_dir: Path,
    *,
    model: str,
    effort: str,
    extra_context: str = "",
) -> None:
    """Dispara um subagente: streaming da resposta, parsing e escrita em disco.

    Atualiza `run` in-place para que a UI ao vivo reflita o progresso.
    """
    run.started_at = time.monotonic()
    run.status = "pensando"

    content = user_prompt
    if extra_context:
        content = (
            f"{user_prompt}\n\n"
            f"--- CONTEXTO DOS ARTEFATOS JÁ GERADOS ---\n{extra_context}"
        )

    chunks: list[str] = []
    try:
        async with client.messages.stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=run.agent.system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            async for event in stream:
                etype = event.type
                if etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block is not None and block.type == "text":
                        run.status = "gerando"
                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        run.status = "gerando"
                        chunks.append(delta.text)
                        # Estimativa viva de progresso (≈4 chars/token).
                        run.tokens_out = sum(len(c) for c in chunks) // 4

            final = await stream.get_final_message()

        # Métricas reais de uso.
        usage = getattr(final, "usage", None)
        if usage is not None:
            run.tokens_in = getattr(usage, "input_tokens", 0) or 0
            run.tokens_out = getattr(usage, "output_tokens", 0) or run.tokens_out

        raw_text = "".join(chunks)
        agent_dir = session_dir / run.agent.key
        run.files = parse_and_write_files(raw_text, agent_dir)

        if not run.files:
            # Salva a resposta crua para depuração quando nada foi parseado.
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "_RAW_RESPONSE.txt").write_text(raw_text, encoding="utf-8")
            run.status = "erro"
            run.error = "nenhum arquivo no protocolo (veja _RAW_RESPONSE.txt)"
        else:
            run.status = "concluído"

    except anthropic.APIStatusError as exc:
        run.status = "erro"
        run.error = f"API {exc.status_code}: {exc.message}"
    except anthropic.APIConnectionError:
        run.status = "erro"
        run.error = "falha de conexão com a API"
    except Exception as exc:  # robustez: um agente não derruba o pipeline
        run.status = "erro"
        run.error = str(exc)
    finally:
        run.finished_at = time.monotonic()


# ===========================================================================
# Renderização rica (tabela de progresso ao vivo)
# ===========================================================================

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_STATUS_STYLE = {
    "aguardando": ("dim", "·"),
    "pensando": ("yellow", "◐"),
    "gerando": ("cyan", "▸"),
    "concluído": ("bold green", "✔"),
    "erro": ("bold red", "✘"),
}


def render_dashboard(runs: list[AgentRun], session_id: str, tick: int) -> Panel:
    """Monta o painel de progresso paralelo (estilo pipeline)."""
    table = Table(box=ROUNDED, expand=True, border_style="grey37")
    table.add_column("Agente", style="bold", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Tokens (out)", justify="right", no_wrap=True)
    table.add_column("Arquivos", justify="right", no_wrap=True)
    table.add_column("Tempo", justify="right", no_wrap=True)
    table.add_column("Detalhe", overflow="fold")

    for run in runs:
        style, glyph = _STATUS_STYLE.get(run.status, ("white", "?"))
        active = run.status in ("pensando", "gerando")
        spin = _SPINNER_FRAMES[tick % len(_SPINNER_FRAMES)] if active else glyph
        status_cell = Text(f"{spin} {run.status}", style=style)
        detail = run.error or ("" if run.status != "concluído" else "ok")
        table.add_row(
            Text(f"{run.agent.emoji} {run.agent.name}", style=run.agent.color),
            status_cell,
            f"{run.tokens_out:,}",
            str(len(run.files)),
            f"{run.elapsed:5.1f}s",
            Text(detail, style="red" if run.error else "green"),
        )

    header = Text(f"  sessão {session_id}", style="dim")
    return Panel(
        Group(header, table),
        title="[bold]⚡ VALEN · Pipeline Paralelo[/bold]",
        border_style="bright_magenta",
        box=ROUNDED,
    )


async def _animate(live: Live, runs: list[AgentRun], session_id: str, stop: asyncio.Event) -> None:
    """Atualiza o dashboard ~12x/s enquanto o pipeline roda."""
    tick = 0
    while not stop.is_set():
        live.update(render_dashboard(runs, session_id, tick))
        tick += 1
        await asyncio.sleep(0.08)
    live.update(render_dashboard(runs, session_id, tick))


# ===========================================================================
# Nó de Consolidação — bundle_processed_data
# ===========================================================================

def _balanced_delimiters(text: str) -> bool:
    """Checagem leve e cross-platform de delimitadores balanceados."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    in_str: str | None = None
    prev = ""
    for ch in text:
        if in_str:
            if ch == in_str and prev != "\\":
                in_str = None
        elif ch in ("'", '"'):
            in_str = ch
        elif ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
        prev = ch
    return not stack


def _lint_file(path: Path) -> tuple[bool, str]:
    """Lint básico por extensão. Retorna (ok, mensagem)."""
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"ilegível: {exc}"

    if not text.strip():
        return False, "arquivo vazio"

    if suffix == ".py":
        import py_compile

        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            return False, f"sintaxe python: {exc.msg}"
        return True, "py ok"

    if suffix in (".ex", ".exs"):
        if not _balanced_delimiters(text):
            return False, "delimitadores desbalanceados"
        return True, "elixir (heurística) ok"

    if suffix in (".json", ".dart", ".ts", ".tsx", ".js", ".jsx"):
        if not _balanced_delimiters(text):
            return False, "delimitadores desbalanceados"
        return True, "ok"

    return True, "ok"


def _run_external_linters(session_dir: Path) -> list[str]:
    """Roda linters externos só se existirem no PATH (Termux-safe)."""
    notes: list[str] = []
    mix = shutil.which("mix")
    if mix:
        backend = session_dir / "backend"
        if (backend / "mix.exs").exists():
            try:
                proc = subprocess.run(
                    [mix, "format", "--check-formatted"],
                    cwd=backend,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                notes.append(
                    "mix format: ok" if proc.returncode == 0
                    else "mix format: arquivos não formatados (não-bloqueante)"
                )
            except Exception as exc:
                notes.append(f"mix format: ignorado ({exc})")
    else:
        notes.append("mix não encontrado no PATH — lint Elixir externo pulado")
    return notes


async def bundle_processed_data(
    runs: list[AgentRun], session_dir: Path, session_id: str
) -> bool:
    """Nó de consolidação: valida artefatos, faz lint e exibe o sucesso.

    Roda DEPOIS de todos os agentes (chamado após o asyncio.gather). Retorna
    True se o bundle foi considerado íntegro.
    """
    console.print()
    console.rule("[bold bright_cyan]🧩 Nó de Consolidação — bundle_processed_data")

    all_files: list[Path] = [f for r in runs for f in r.files]
    failures: list[str] = []

    # 1) Validação de presença: cada agente esperado produziu algo?
    for run in runs:
        if run.status == "erro":
            failures.append(f"{run.agent.name}: {run.error}")
        elif not run.files:
            failures.append(f"{run.agent.name}: nenhum arquivo gerado")

    # 2) Lint básico em todos os arquivos escritos.
    lint_table = Table(box=ROUNDED, expand=True, border_style="grey37",
                       title="Lint & Validação")
    lint_table.add_column("Arquivo", overflow="fold")
    lint_table.add_column("Resultado", no_wrap=True)
    lint_ok = 0
    for path in all_files:
        ok, msg = _lint_file(path)
        rel = path.relative_to(session_dir.resolve()) if path.is_absolute() else path
        lint_table.add_row(
            str(rel),
            Text(f"✔ {msg}", style="green") if ok else Text(f"✘ {msg}", style="red"),
        )
        if ok:
            lint_ok += 1
        else:
            failures.append(f"lint: {rel} ({msg})")

    if all_files:
        console.print(lint_table)

    # 3) Linters externos opcionais.
    for note in _run_external_linters(session_dir):
        console.print(f"  [dim]›[/dim] {note}")

    # 4) Painel de status final.
    total_tokens = sum(r.tokens_out for r in runs)
    success = not failures

    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="dim")
    summary.add_column()
    summary.add_row("Sessão", session_id)
    summary.add_row("Diretório", str(session_dir))
    summary.add_row("Arquivos", f"{len(all_files)} ({lint_ok} válidos)")
    summary.add_row("Tokens (out)", f"{total_tokens:,}")
    summary.add_row("Agentes", ", ".join(
        f"[{r.agent.color}]{r.agent.emoji} {r.status}[/]" for r in runs
    ))

    if success:
        console.print(Panel(
            Group(
                Text("✨  BUNDLE CONSOLIDADO COM SUCESSO  ✨",
                     style="bold green", justify="center"),
                Text(""),
                summary,
            ),
            border_style="bold green",
            box=ROUNDED,
        ))
    else:
        fail_text = Text("\n".join(f"• {f}" for f in failures), style="red")
        console.print(Panel(
            Group(
                Text("⚠  BUNDLE COM PENDÊNCIAS", style="bold red", justify="center"),
                Text(""),
                summary,
                Text(""),
                fail_text,
            ),
            border_style="bold red",
            box=ROUNDED,
        ))

    return success


# ===========================================================================
# Orquestração
# ===========================================================================

def _read_artifacts(session_dir: Path, keys: tuple[str, ...], limit: int = 24000) -> str:
    """Concatena (truncando) os artefatos dos agentes dados, como contexto."""
    parts: list[str] = []
    budget = limit
    for key in keys:
        root = session_dir / key
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or budget <= 0:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            rel = path.relative_to(session_dir)
            snippet = text[:budget]
            parts.append(f"### {rel}\n{snippet}")
            budget -= len(snippet)
    return "\n\n".join(parts)


def build_client() -> "anthropic.AsyncAnthropic":
    """Cria o cliente assíncrono, preferindo o backend aiohttp."""
    if _HAS_AIOHTTP and DefaultAioHttpClient is not None:
        return anthropic.AsyncAnthropic(http_client=DefaultAioHttpClient())
    return anthropic.AsyncAnthropic()


async def orchestrate(
    user_prompt: str, *, model: str, effort: str, output_dir: Path, run_qa: bool
) -> bool:
    """Fluxo completo: fan-out paralelo → QA dependente → consolidação."""
    session_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    session_dir = (output_dir / session_id).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "PROMPT.md").write_text(user_prompt, encoding="utf-8")

    parallel_agents = [a for a in ALL_AGENTS if not a.depends_on]
    dependent_agents = [a for a in ALL_AGENTS if a.depends_on]
    if not run_qa:
        dependent_agents = []

    runs = {a.key: AgentRun(agent=a) for a in ALL_AGENTS}
    ordered = [runs[a.key] for a in ALL_AGENTS]

    backend_label = "aiohttp" if _HAS_AIOHTTP else "httpx (fallback)"
    console.print(Panel(
        Group(
            Text(f"📥 Prompt: {user_prompt}", style="bold"),
            Text(f"🧠 Modelo: {model}   ·   esforço: {effort}   ·   backend: {backend_label}",
                 style="dim"),
        ),
        title="[bold bright_magenta]VALEN[/bold bright_magenta]",
        border_style="bright_magenta",
        box=ROUNDED,
    ))

    client = build_client()
    try:
        with Live(render_dashboard(ordered, session_id, 0),
                  console=console, refresh_per_second=12) as live:
            stop = asyncio.Event()
            animator = asyncio.create_task(_animate(live, ordered, session_id, stop))

            # --- FASE 1: fan-out paralelo (asyncio.gather) ---
            await asyncio.gather(*[
                run_agent(client, runs[a.key], user_prompt, session_dir,
                          model=model, effort=effort)
                for a in parallel_agents
            ])

            # --- FASE 2: agentes dependentes (QA lê o que já foi gerado) ---
            for agent in dependent_agents:
                ctx = _read_artifacts(session_dir, agent.depends_on)
                await run_agent(client, runs[agent.key], user_prompt, session_dir,
                                model=model, effort=effort, extra_context=ctx)

            stop.set()
            await animator
    finally:
        await client.close()

    # --- FASE 3: nó de consolidação ---
    return await bundle_processed_data(ordered, session_dir, session_id)


# ===========================================================================
# CLI
# ===========================================================================

def _prompt_interactive() -> str:
    """Lê o prompt interativamente com prompt_toolkit (fallback para input)."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML

        session = PromptSession()
        return session.prompt(
            HTML("<ansibrightmagenta><b>valen ✦ </b></ansibrightmagenta>"
                 "descreva o software desejado: ")
        ).strip()
    except Exception:
        return input("valen ✦ descreva o software desejado: ").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="valen",
        description="Orquestrador Multiagente Assíncrono de Desenvolvimento (Anthropic API).",
    )
    parser.add_argument("-p", "--prompt", help="Especificação do software a construir.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"Modelo Anthropic (default: {DEFAULT_MODEL}).")
    parser.add_argument("-e", "--effort", default=DEFAULT_EFFORT,
                        choices=["low", "medium", "high", "xhigh", "max"],
                        help=f"Esforço/raciocínio (default: {DEFAULT_EFFORT}).")
    parser.add_argument("-o", "--output-dir", default="valen_output", type=Path,
                        help="Raiz de saída (default: ./valen_output).")
    parser.add_argument("--no-qa", action="store_true",
                        help="Pula o agente de QA.")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]✘ ANTHROPIC_API_KEY não definida.[/bold red]\n"
            "  Exporte sua chave antes de rodar:\n"
            "  [cyan]export ANTHROPIC_API_KEY=\"sua-chave\"[/cyan]"
        )
        return 2

    prompt = (args.prompt or "").strip() or _prompt_interactive()
    if not prompt:
        console.print("[red]Nenhum prompt fornecido. Encerrando.[/red]")
        return 2

    try:
        success = asyncio.run(orchestrate(
            prompt,
            model=args.model,
            effort=args.effort,
            output_dir=args.output_dir,
            run_qa=not args.no_qa,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido pelo usuário.[/yellow]")
        return 130

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
