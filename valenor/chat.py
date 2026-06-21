"""
Terminal interativo estilo Claude Code / Claude Code-style interactive terminal.

Um REPL com banner de boas-vindas, prompt persistente, histórico, comandos
`/slash` e *auto-suggest*. Cada mensagem comum dispara o pipeline multiagente
(o mesmo `orchestrate`), como o Claude Code roda uma tarefa por turno.

A REPL with a welcome banner, persistent prompt, history, `/slash` commands and
auto-suggest. Each plain message runs the multi-agent pipeline.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from rich.box import ROUNDED
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cli import DEFAULT_EFFORT, DEFAULT_MODEL, console, orchestrate
from .i18n import t
from .paths import valen_home

EFFORTS = ("low", "medium", "high", "xhigh", "max")
LANGS = ("en", "pt", "both")

_COMMANDS = (
    "/help", "/status", "/model", "/effort", "/lang",
    "/qa", "/memory", "/skills", "/clear", "/exit", "/quit",
)


@dataclass
class ChatState:
    lang: str
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    output_dir: Path = Path("valen_output")
    run_qa: bool = True
    use_memory: bool = True
    skill_names: list[str] | None = None


# ---------------------------------------------------------------------------
# Apresentação / presentation
# ---------------------------------------------------------------------------

def _banner(state: ChatState) -> Panel:
    body = Group(
        Text(f"✻ {t('chat_welcome', state.lang)}", style="bold bright_magenta"),
        Text(""),
        Text(f"  {t('chat_hint', state.lang)}", style="dim"),
        Text(""),
        Text(f"  {t('chat_cwd', state.lang)}: {os.getcwd()}", style="dim"),
    )
    return Panel(body, border_style="bright_magenta", box=ROUNDED, padding=(1, 2))


def _status_panel(state: ChatState) -> Panel:
    g = Table.grid(padding=(0, 2))
    g.add_column(justify="right", style="dim")
    g.add_column()
    g.add_row("model", state.model)
    g.add_row("effort", state.effort)
    g.add_row("lang", state.lang)
    g.add_row("qa", "on" if state.run_qa else "off")
    g.add_row("memory", "on" if state.use_memory else "off")
    g.add_row("skills", ",".join(state.skill_names) if state.skill_names else "all")
    return Panel(g, title=t("chat_status", state.lang), border_style="cyan", box=ROUNDED)


def _help_panel(state: ChatState) -> Panel:
    rows = [
        ("/help", "this help / esta ajuda"),
        ("/status", "current setup / configuração atual"),
        ("/model <id>", "set model / definir modelo"),
        ("/effort <low|…|max>", "reasoning effort / esforço"),
        ("/lang <en|pt|both>", "UI language / idioma"),
        ("/qa", "toggle QA agent / liga-desliga QA"),
        ("/memory [list|search <q>]", "learning memory / memória"),
        ("/skills", "loaded skills / skills carregadas"),
        ("/clear", "clear screen / limpar tela"),
        ("/exit", "quit / sair"),
        ("<text>", "build software / construir software"),
    ]
    table = Table(box=ROUNDED, border_style="grey37", expand=True)
    table.add_column(t("chat_help_title", state.lang), style="bold cyan", no_wrap=True)
    table.add_column("")
    for cmd, desc in rows:
        table.add_row(cmd, desc)
    return Panel(table, border_style="cyan", box=ROUNDED)


# ---------------------------------------------------------------------------
# Entrada / input (prompt_toolkit com fallback p/ input())
# ---------------------------------------------------------------------------

class _Reader:
    """Lê linhas do usuário; usa prompt_toolkit se houver TTY, senão input()."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self._session = None
        self._fallback = False
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
            from prompt_toolkit.completion import WordCompleter
            from prompt_toolkit.history import FileHistory

            valen_home().mkdir(parents=True, exist_ok=True)
            self._session = PromptSession(
                history=FileHistory(str(valen_home() / "history")),
                auto_suggest=AutoSuggestFromHistory(),
                completer=WordCompleter(list(_COMMANDS), sentence=True),
            )
        except Exception:
            self._fallback = True

    def read(self, state: ChatState) -> str | None:
        try:
            if self._session is not None and not self._fallback:
                from prompt_toolkit.formatted_text import HTML

                return self._session.prompt(
                    HTML("<ansibrightmagenta><b>valenor ›</b></ansibrightmagenta> "),
                    bottom_toolbar=HTML(
                        f" {state.model} · effort={state.effort} · "
                        f"lang={state.lang} · qa={'on' if state.run_qa else 'off'} "
                    ),
                )
            return input("valenor › ")
        except EOFError:
            return None
        except KeyboardInterrupt:
            return ""  # cancela a linha / cancel the line
        except Exception:
            # Qualquer falha do prompt_toolkit → cai para input() dali em diante.
            self._fallback = True
            try:
                return input("valenor › ")
            except EOFError:
                return None


# ---------------------------------------------------------------------------
# Comandos / commands
# ---------------------------------------------------------------------------

def _handle_command(line: str, state: ChatState) -> bool:
    """Processa um comando /slash. Retorna False para sair do REPL."""
    parts = line.strip().split()
    cmd, args = parts[0].lower(), parts[1:]

    if cmd in ("/exit", "/quit", "/q"):
        console.print(t("chat_bye", state.lang))
        return False
    if cmd == "/help":
        console.print(_help_panel(state))
    elif cmd == "/status":
        console.print(_status_panel(state))
    elif cmd == "/clear":
        console.clear()
        console.print(_banner(state))
    elif cmd == "/model":
        if args:
            state.model = args[0]
        console.print(t("chat_set", state.lang, field="model", value=state.model))
    elif cmd == "/effort":
        if args and args[0] in EFFORTS:
            state.effort = args[0]
        console.print(t("chat_set", state.lang, field="effort", value=state.effort))
    elif cmd == "/lang":
        if args and args[0] in LANGS:
            state.lang = args[0]
        console.print(t("chat_set", state.lang, field="lang", value=state.lang))
    elif cmd == "/qa":
        state.run_qa = not state.run_qa
        console.print(t("chat_set", state.lang, field="qa",
                        value="on" if state.run_qa else "off"))
    elif cmd == "/skills":
        from .skills import SkillManager

        skills = SkillManager().list("valenor")
        if not skills:
            console.print(t("skills_none", state.lang))
        for s in skills:
            console.print(f"• [cyan]{s.name}[/cyan] — {s.description}")
    elif cmd == "/memory":
        from .memory import MemoryVault

        vault = MemoryVault()
        if args and args[0] == "list":
            for tt in vault.list_titles():
                console.print(f"• [cyan]{tt}[/cyan]")
        elif args and args[0] == "search":
            for title, score in vault.search(" ".join(args[1:])):
                console.print(f"[cyan]{title}[/cyan] [dim]({score})[/dim]")
        else:
            state.use_memory = not state.use_memory
            console.print(t("chat_set", state.lang, field="memory",
                            value="on" if state.use_memory else "off"))
    else:
        console.print(t("chat_unknown", state.lang, cmd=cmd))
    return True


# ---------------------------------------------------------------------------
# Loop principal / main loop
# ---------------------------------------------------------------------------

def run_chat(state: ChatState) -> int:
    console.print(_banner(state))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(f"  [yellow]![/yellow] {t('chat_need_key', state.lang)}")

    reader = _Reader(state.lang)
    while True:
        line = reader.read(state)
        if line is None:  # EOF / Ctrl-D
            console.print()
            console.print(t("chat_bye", state.lang))
            return 0
        line = line.strip()
        if not line:
            continue
        if line.startswith("/"):
            if not _handle_command(line, state):
                return 0
            continue
        # Mensagem comum → roda o pipeline (uma tarefa por turno).
        if not os.environ.get("ANTHROPIC_API_KEY"):
            console.print(f"  [yellow]![/yellow] {t('chat_need_key', state.lang)}")
            continue
        try:
            asyncio.run(orchestrate(
                line, model=state.model, effort=state.effort,
                output_dir=state.output_dir, run_qa=state.run_qa,
                lang=state.lang, use_memory=state.use_memory,
                skill_names=state.skill_names))
        except KeyboardInterrupt:
            console.print(f"\n[yellow]{t('interrupted', state.lang)}[/yellow]")
