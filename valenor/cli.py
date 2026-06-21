#!/usr/bin/env python3
"""
VALEN — Orquestrador Multiagente Assíncrono / Async multi-agent orchestrator.

Entry point do comando `valenor`. Subcomandos:
  valenor [build] [PROMPT]   constrói software com os 3 agentes (default)
  valenor memory ...         vault de memória estilo Obsidian
  valenor skills ...         instala/lista skills (Claude Code, Codex, Antigravity)

`valenor "um app de tarefas"` é atalho para `valenor build -p "..."`.
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

try:
    import anthropic
except ImportError:  # pragma: no cover
    print("Dependências ausentes / missing deps. Run: pip install -r requirements.txt",
          file=sys.stderr)
    raise SystemExit(1)

try:
    from anthropic import DefaultAioHttpClient  # type: ignore

    _HAS_AIOHTTP = True
except Exception:  # pragma: no cover
    DefaultAioHttpClient = None  # type: ignore
    _HAS_AIOHTTP = False

from .agents import ALL_AGENTS, FILE_CLOSE, FILE_OPEN, Agent, compose_system
from .i18n import detect_lang, t
from .memory import MemoryVault, record_session
from .skills import TOOLS, SkillManager, tool_dir

console = Console()

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_EFFORT = "high"
MAX_TOKENS = 32000


# ===========================================================================
# Estado / state
# ===========================================================================

@dataclass
class AgentRun:
    agent: Agent
    status: str = "waiting"  # waiting | thinking | generating | done | error
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
# Protocolo de arquivos / file protocol
# ===========================================================================

_FILE_BLOCK_RE = re.compile(
    re.escape(FILE_OPEN) + r"\s*(?P<path>.+?)\s*===\s*\n"
    r"(?P<body>.*?)"
    r"(?:\n)?" + re.escape(FILE_CLOSE),
    re.DOTALL,
)


def _safe_relpath(raw: str) -> Path | None:
    candidate = raw.strip().strip("/").replace("\\", "/")
    if not candidate or candidate in (".", ".."):
        return None
    p = Path(candidate)
    if p.is_absolute() or any(part == ".." for part in p.parts):
        return None
    return p


def parse_and_write_files(raw_text: str, dest_root: Path) -> list[Path]:
    """Extrai blocos do protocolo e grava cada arquivo sob `dest_root`."""
    written: list[Path] = []
    dest_root = dest_root.resolve()
    for match in _FILE_BLOCK_RE.finditer(raw_text):
        rel = _safe_relpath(match.group("path"))
        if rel is None:
            continue
        target = (dest_root / rel).resolve()
        if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
            continue
        body = match.group("body")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(target)
    return written


# ===========================================================================
# Execução de um agente / agent execution
# ===========================================================================

async def run_agent(
    client: "anthropic.AsyncAnthropic",
    run: AgentRun,
    user_prompt: str,
    session_dir: Path,
    *,
    model: str,
    effort: str,
    lang: str,
    skills_block: str = "",
    memory_block: str = "",
    artifacts: str = "",
) -> None:
    run.started_at = time.monotonic()
    run.status = "thinking"

    sections = [user_prompt]
    if memory_block:
        sections.append("--- MEMÓRIA RELEVANTE / RELEVANT MEMORY ---\n" + memory_block)
    if artifacts:
        sections.append("--- ARTEFATOS JÁ GERADOS / EXISTING ARTIFACTS ---\n" + artifacts)
    content = "\n\n".join(sections)

    system = compose_system(run.agent, lang, skills_block)
    chunks: list[str] = []
    try:
        async with client.messages.stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block is not None and block.type == "text":
                        run.status = "generating"
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        run.status = "generating"
                        chunks.append(delta.text)
                        run.tokens_out = sum(len(c) for c in chunks) // 4
            final = await stream.get_final_message()

        usage = getattr(final, "usage", None)
        if usage is not None:
            run.tokens_in = getattr(usage, "input_tokens", 0) or 0
            run.tokens_out = getattr(usage, "output_tokens", 0) or run.tokens_out

        raw_text = "".join(chunks)
        agent_dir = session_dir / run.agent.key
        run.files = parse_and_write_files(raw_text, agent_dir)
        if not run.files:
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "_RAW_RESPONSE.txt").write_text(raw_text, encoding="utf-8")
            run.status = "error"
            run.error = "no files in protocol (see _RAW_RESPONSE.txt)"
        else:
            run.status = "done"
    except anthropic.APIStatusError as exc:
        run.status, run.error = "error", f"API {exc.status_code}: {exc.message}"
    except anthropic.APIConnectionError:
        run.status, run.error = "error", "connection failure"
    except Exception as exc:
        run.status, run.error = "error", str(exc)
    finally:
        run.finished_at = time.monotonic()


# ===========================================================================
# UI / rendering
# ===========================================================================

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_STATUS_STYLE = {
    "waiting": ("dim", "·"),
    "thinking": ("yellow", "◐"),
    "generating": ("cyan", "▸"),
    "done": ("bold green", "✔"),
    "error": ("bold red", "✘"),
}


def render_dashboard(runs: list[AgentRun], session_id: str, tick: int, lang: str) -> Panel:
    table = Table(box=ROUNDED, expand=True, border_style="grey37")
    table.add_column(t("col_agent", lang), style="bold", no_wrap=True)
    table.add_column(t("col_status", lang), no_wrap=True)
    table.add_column(t("col_tokens", lang), justify="right", no_wrap=True)
    table.add_column(t("col_files", lang), justify="right", no_wrap=True)
    table.add_column(t("col_time", lang), justify="right", no_wrap=True)
    table.add_column(t("col_detail", lang), overflow="fold")

    for run in runs:
        style, glyph = _STATUS_STYLE.get(run.status, ("white", "?"))
        active = run.status in ("thinking", "generating")
        spin = _SPINNER[tick % len(_SPINNER)] if active else glyph
        label = t(f"st_{run.status}", lang)
        detail = run.error or ("ok" if run.status == "done" else "")
        table.add_row(
            Text(f"{run.agent.emoji} {run.agent.name}", style=run.agent.color),
            Text(f"{spin} {label}", style=style),
            f"{run.tokens_out:,}",
            str(len(run.files)),
            f"{run.elapsed:5.1f}s",
            Text(detail, style="red" if run.error else "green"),
        )

    return Panel(
        Group(Text(f"  {t('s_session', lang)} {session_id}", style="dim"), table),
        title=f"[bold]⚡ VALEN · {t('pipeline_title', lang)}[/bold]",
        border_style="bright_magenta", box=ROUNDED,
    )


async def _animate(live: Live, runs: list[AgentRun], session_id: str,
                   lang: str, stop: asyncio.Event) -> None:
    tick = 0
    while not stop.is_set():
        live.update(render_dashboard(runs, session_id, tick, lang))
        tick += 1
        await asyncio.sleep(0.08)
    live.update(render_dashboard(runs, session_id, tick, lang))


# ===========================================================================
# Lint / bundle
# ===========================================================================

def _balanced_delimiters(text: str) -> bool:
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
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"unreadable: {exc}"
    if not text.strip():
        return False, "empty file"
    if suffix == ".py":
        import py_compile

        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            return False, f"python syntax: {exc.msg}"
        return True, "py ok"
    if suffix in (".ex", ".exs"):
        return (True, "elixir ok") if _balanced_delimiters(text) else \
            (False, "unbalanced delimiters")
    if suffix in (".json", ".dart", ".ts", ".tsx", ".js", ".jsx"):
        return (True, "ok") if _balanced_delimiters(text) else \
            (False, "unbalanced delimiters")
    return True, "ok"


def _run_external_linters(session_dir: Path) -> list[str]:
    notes: list[str] = []
    mix = shutil.which("mix")
    if mix and (session_dir / "backend" / "mix.exs").exists():
        try:
            proc = subprocess.run([mix, "format", "--check-formatted"],
                                  cwd=session_dir / "backend",
                                  capture_output=True, text=True, timeout=60)
            notes.append("mix format: ok" if proc.returncode == 0
                         else "mix format: not formatted (non-blocking)")
        except Exception as exc:
            notes.append(f"mix format: skipped ({exc})")
    elif not mix:
        notes.append("mix not on PATH — external Elixir lint skipped")
    return notes


async def bundle_processed_data(runs: list[AgentRun], session_dir: Path,
                                session_id: str, lang: str) -> bool:
    console.print()
    console.rule(f"[bold bright_cyan]🧩 {t('bundle_node', lang)}")

    all_files = [f for r in runs for f in r.files]
    failures: list[str] = []
    for run in runs:
        if run.status == "error":
            failures.append(f"{run.agent.name}: {run.error}")
        elif not run.files:
            failures.append(f"{run.agent.name}: no files generated")

    lint_table = Table(box=ROUNDED, expand=True, border_style="grey37",
                       title=t("lint_title", lang))
    lint_table.add_column(t("col_detail", lang), overflow="fold")
    lint_table.add_column(t("col_status", lang), no_wrap=True)
    lint_ok = 0
    root = session_dir.resolve()
    for path in all_files:
        ok, msg = _lint_file(path)
        rel = path.relative_to(root) if path.is_absolute() else path
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
    for note in _run_external_linters(session_dir):
        console.print(f"  [dim]›[/dim] {note}")

    total_tokens = sum(r.tokens_out for r in runs)
    success = not failures

    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="dim")
    summary.add_column()
    summary.add_row(t("s_session", lang), session_id)
    summary.add_row(t("s_dir", lang), str(session_dir))
    summary.add_row(t("s_files", lang), f"{len(all_files)} ({lint_ok} {t('s_valid', lang)})")
    summary.add_row(t("s_tokens", lang), f"{total_tokens:,}")
    summary.add_row(t("s_agents", lang), ", ".join(
        f"[{r.agent.color}]{r.agent.emoji} {t('st_' + r.status, lang)}[/]" for r in runs))

    if success:
        console.print(Panel(
            Group(Text(f"✨  {t('bundle_ok', lang)}  ✨", style="bold green",
                       justify="center"), Text(""), summary),
            border_style="bold green", box=ROUNDED))
    else:
        console.print(Panel(
            Group(Text(f"⚠  {t('bundle_pending', lang)}", style="bold red",
                       justify="center"), Text(""), summary, Text(""),
                  Text("\n".join(f"• {f}" for f in failures), style="red")),
            border_style="bold red", box=ROUNDED))
    return success


# ===========================================================================
# Orquestração / orchestration
# ===========================================================================

def _read_artifacts(session_dir: Path, keys: tuple[str, ...], limit: int = 24000) -> str:
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
            snippet = text[:budget]
            parts.append(f"### {path.relative_to(session_dir)}\n{snippet}")
            budget -= len(snippet)
    return "\n\n".join(parts)


def build_client() -> "anthropic.AsyncAnthropic":
    if _HAS_AIOHTTP and DefaultAioHttpClient is not None:
        return anthropic.AsyncAnthropic(http_client=DefaultAioHttpClient())
    return anthropic.AsyncAnthropic()


async def orchestrate(user_prompt: str, *, model: str, effort: str, output_dir: Path,
                      run_qa: bool, lang: str, use_memory: bool,
                      skill_names: list[str] | None) -> bool:
    session_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    session_dir = (output_dir / session_id).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "PROMPT.md").write_text(user_prompt, encoding="utf-8")

    # Skills → bloco injetado em todos os agentes.
    sk = SkillManager()
    skills_block, n_skills = sk.system_block(skill_names)
    # Memória → recall relacionado ao prompt.
    vault = MemoryVault()
    memory_block = vault.recall(user_prompt) if use_memory else ""

    parallel_agents = [a for a in ALL_AGENTS if not a.depends_on]
    dependent_agents = [a for a in ALL_AGENTS if a.depends_on] if run_qa else []
    runs = {a.key: AgentRun(agent=a) for a in ALL_AGENTS}
    ordered = [runs[a.key] for a in ALL_AGENTS]

    backend_label = "aiohttp" if _HAS_AIOHTTP else "httpx (fallback)"
    info = Group(
        Text(f"📥 {t('header_prompt', lang)}: {user_prompt}", style="bold"),
        Text(f"🧠 {t('header_engine', lang)}: {model} · effort={effort} · "
             f"{backend_label} · lang={lang}", style="dim"),
    )
    console.print(Panel(info, title="[bold bright_magenta]VALEN[/bold bright_magenta]",
                        border_style="bright_magenta", box=ROUNDED))
    if n_skills:
        console.print(f"  [green]✓[/green] {t('skills_loaded', lang, n=n_skills)}")
    if memory_block:
        n = memory_block.count("### [[")
        console.print(f"  [green]✓[/green] {t('mem_recalled', lang, n=max(n, 1))}")

    client = build_client()
    try:
        with Live(render_dashboard(ordered, session_id, 0, lang),
                  console=console, refresh_per_second=12) as live:
            stop = asyncio.Event()
            animator = asyncio.create_task(_animate(live, ordered, session_id, lang, stop))

            # FASE 1: fan-out paralelo / parallel fan-out
            await asyncio.gather(*[
                run_agent(client, runs[a.key], user_prompt, session_dir,
                          model=model, effort=effort, lang=lang,
                          skills_block=skills_block, memory_block=memory_block)
                for a in parallel_agents
            ])
            # FASE 2: agentes dependentes / dependent agents
            for agent in dependent_agents:
                ctx = _read_artifacts(session_dir, agent.depends_on)
                await run_agent(client, runs[agent.key], user_prompt, session_dir,
                                model=model, effort=effort, lang=lang,
                                skills_block=skills_block, memory_block=memory_block,
                                artifacts=ctx)
            stop.set()
            await animator
    finally:
        await client.close()

    # FASE 3: consolidação / consolidation
    success = await bundle_processed_data(ordered, session_dir, session_id, lang)

    # Aprendizado: grava na memória após sucesso.
    if use_memory and success:
        summary = [(r.agent.name, r.status, len(r.files), r.tokens_out) for r in ordered]
        record_session(vault, session_id, user_prompt, summary, session_dir, lang)
        console.print(f"  [green]✓[/green] {t('mem_learned', lang)}")

    return success


# ===========================================================================
# Subcomandos: memory & skills
# ===========================================================================

def cmd_memory(args: argparse.Namespace, lang: str) -> int:
    vault = MemoryVault()
    action = args.action
    if action == "list":
        titles = vault.list_titles()
        if not titles:
            console.print(t("mem_empty", lang)); return 0
        for tt in titles:
            console.print(f"• [cyan]{tt}[/cyan]")
        return 0
    if action == "search":
        for title, score in vault.search(args.query):
            console.print(f"[cyan]{title}[/cyan]  [dim](score {score})[/dim]")
        return 0
    if action == "show":
        note = vault.read(args.title)
        if not note:
            console.print(t("mem_not_found", lang, title=args.title)); return 1
        console.print(Panel(note.text, title=note.title, border_style="cyan"))
        return 0
    if action == "links":
        note = vault.read(args.title)
        if not note:
            console.print(t("mem_not_found", lang, title=args.title)); return 1
        out = ", ".join(f"[[{x}]]" for x in note.links) or "—"
        back = ", ".join(f"[[{x}]]" for x in vault.backlinks(args.title)) or "—"
        console.print(f"[bold]{t('mem_outgoing', lang)}:[/bold] {out}")
        console.print(f"[bold]{t('mem_backlinks', lang)}:[/bold] {back}")
        return 0
    if action == "graph":
        for note in vault.all_notes():
            if note.links:
                console.print(f"[cyan]{note.title}[/cyan] → " +
                              ", ".join(note.links))
        return 0
    if action == "add":
        vault.write(args.title, args.body or "",
                    links=tuple(args.link or ()))
        console.print(f"[green]✓[/green] {args.title}")
        return 0
    return 2


def cmd_skills(args: argparse.Namespace, lang: str) -> int:
    mgr = SkillManager()
    action = args.action
    if action == "list":
        skills = mgr.list(args.tool)
        if not skills:
            console.print(t("skills_none", lang)); return 0
        for s in skills:
            console.print(f"• [cyan]{s.name}[/cyan] — {s.description}")
        return 0
    if action == "where":
        for tool in TOOLS:
            console.print(f"{tool:14} [dim]{tool_dir(tool)}[/dim]")
        return 0
    if action == "install":
        try:
            sk = mgr.install(args.source, tool=args.tool, name=args.name)
        except ValueError as exc:
            console.print(f"[red]✘[/red] {t('skills_invalid', lang, src=exc)}"); return 1
        except Exception as exc:
            console.print(f"[red]✘[/red] {exc}"); return 1
        console.print(f"[green]✓[/green] {t('skills_installed', lang, name=sk.name)} "
                      f"→ [dim]{sk.path}[/dim]")
        return 0
    if action == "new":
        sk = mgr.scaffold(args.name, tool=args.tool, description=args.desc or "")
        console.print(f"[green]✓[/green] {sk.path / 'SKILL.md'}")
        return 0
    return 2


# ===========================================================================
# CLI
# ===========================================================================

def _prompt_interactive(lang: str) -> str:
    label = t("ask_prompt", lang)
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML

        session = PromptSession()
        return session.prompt(
            HTML(f"<ansibrightmagenta><b>valenor ✦ </b></ansibrightmagenta>{label}")
        ).strip()
    except Exception:
        return input(f"valenor ✦ {label}").strip()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="valenor",
        description="Async multi-agent software-development orchestrator (Anthropic API). "
                    "Orquestrador multiagente assíncrono.")
    p.add_argument("-l", "--lang", choices=("en", "pt", "both"),
                   help="UI language / idioma (default: auto).")
    sub = p.add_subparsers(dest="command")

    b = sub.add_parser("build", help="Build software with the agents (default).")
    b.add_argument("-p", "--prompt")
    b.add_argument("-m", "--model", default=DEFAULT_MODEL)
    b.add_argument("-e", "--effort", default=DEFAULT_EFFORT,
                   choices=["low", "medium", "high", "xhigh", "max"])
    b.add_argument("-o", "--output-dir", default=Path("valen_output"), type=Path)
    b.add_argument("--no-qa", action="store_true")
    b.add_argument("--no-memory", action="store_true", help="Disable learning memory.")
    b.add_argument("-s", "--skills", help="Comma-separated skill names to load.")

    m = sub.add_parser("memory", help="Obsidian-style learning memory.")
    msub = m.add_subparsers(dest="action", required=True)
    msub.add_parser("list")
    sp = msub.add_parser("search"); sp.add_argument("query")
    sp = msub.add_parser("show"); sp.add_argument("title")
    sp = msub.add_parser("links"); sp.add_argument("title")
    msub.add_parser("graph")
    sp = msub.add_parser("add"); sp.add_argument("title")
    sp.add_argument("--body", default=""); sp.add_argument("--link", action="append")

    s = sub.add_parser("skills", help="Install/list skills (Claude Code, Codex, Antigravity).")
    ssub = s.add_subparsers(dest="action", required=True)
    sl = ssub.add_parser("list"); sl.add_argument("--tool", choices=TOOLS, default="valenor")
    si = ssub.add_parser("install"); si.add_argument("source")
    si.add_argument("--tool", choices=TOOLS, default="valenor")
    si.add_argument("--name")
    sn = ssub.add_parser("new"); sn.add_argument("name")
    sn.add_argument("--tool", choices=TOOLS, default="valenor")
    sn.add_argument("--desc", default="")
    ssub.add_parser("where")
    return p


_SUBCOMMANDS = {"build", "memory", "skills"}


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # Extrai `-l/--lang` (em qualquer posição) antes de decidir o atalho.
    # Pull out `-l/--lang` (anywhere) before deciding the shorthand.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("-l", "--lang", choices=("en", "pt", "both"))
    known, rest = pre.parse_known_args(raw)
    lang = detect_lang(known.lang)

    # Atalho: `valenor "prompt"` → build. / Shorthand to build.
    if rest and rest[0] not in _SUBCOMMANDS and not rest[0].startswith("-"):
        rest = ["build", "--prompt", " ".join(rest)]

    parser = _build_parser()
    args = parser.parse_args(rest)
    command = args.command or "build"

    if command == "memory":
        return cmd_memory(args, lang)
    if command == "skills":
        return cmd_skills(args, lang)

    # build (default)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(f"[bold red]✘[/bold red] {t('no_api_key', lang)}")
        return 2

    prompt = (getattr(args, "prompt", None) or "").strip() or _prompt_interactive(lang)
    if not prompt:
        console.print(f"[red]{t('no_prompt', lang)}[/red]")
        return 2

    skill_names = [s.strip() for s in args.skills.split(",")] if getattr(args, "skills", None) else None
    try:
        success = asyncio.run(orchestrate(
            prompt, model=args.model, effort=args.effort, output_dir=args.output_dir,
            run_qa=not args.no_qa, lang=lang, use_memory=not args.no_memory,
            skill_names=skill_names))
    except KeyboardInterrupt:
        console.print(f"\n[yellow]{t('interrupted', lang)}[/yellow]")
        return 130
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
