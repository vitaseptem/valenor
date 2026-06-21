"""
Memória estilo Obsidian — o VALEN aprende com cada execução.

Cada nota é um arquivo Markdown no vault (`~/.valenor/memory`). As notas se
conectam por wikilinks `[[Título]]` (com alias opcional `[[Título|texto]]`),
exatamente como no Obsidian. O orquestrador:

  • antes de rodar, busca notas relacionadas ao prompt e injeta como contexto
    ("lembrar");
  • depois de uma consolidação bem-sucedida, escreve uma nota de sessão e
    cria/atualiza notas de conceito (Elixir, Phoenix, a stack de frontend
    escolhida, ExUnit…) com backlinks ("aprender").

Obsidian-style memory — VALEN learns from every run. Notes are Markdown files
linked by `[[Wikilinks]]`; the orchestrator recalls related notes before a run
and records learnings after a successful bundle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .paths import memory_dir

# [[Alvo]] ou [[Alvo|texto exibido]]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")
_SLUG_BAD = re.compile(r'[<>:"/\\|?*\n\r\t]+')
_STOPWORDS = {
    # en
    "the", "a", "an", "and", "or", "of", "to", "for", "with", "in", "on", "app",
    "with", "that", "this", "is", "are", "be", "by", "from",
    # pt
    "um", "uma", "de", "da", "do", "das", "dos", "e", "ou", "para", "com", "em",
    "que", "the", "app", "aplicativo", "sistema",
}


def _slug(title: str) -> str:
    """Converte um título em nome de arquivo seguro (preserva legibilidade)."""
    s = _SLUG_BAD.sub("", title).strip()
    return s or "untitled"


def keywords(text: str, limit: int = 8) -> list[str]:
    """Extrai palavras-chave simples de um texto (para busca/relacionamento)."""
    words = re.findall(r"[A-Za-zÀ-ÿ0-9_]{3,}", text.lower())
    seen: list[str] = []
    for w in words:
        if w in _STOPWORDS or w in seen:
            continue
        seen.append(w)
        if len(seen) >= limit:
            break
    return seen


@dataclass
class Note:
    title: str
    path: Path
    text: str

    @property
    def links(self) -> list[str]:
        return [m.strip() for m in WIKILINK_RE.findall(self.text)]


class MemoryVault:
    """Vault de notas Markdown interligadas por wikilinks."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or memory_dir())
        self.root.mkdir(parents=True, exist_ok=True)

    # -- leitura ----------------------------------------------------------
    def note_path(self, title: str) -> Path:
        return self.root / f"{_slug(title)}.md"

    def read(self, title: str) -> Note | None:
        p = self.note_path(title)
        if not p.exists():
            # fallback: case-insensitive match pelo título
            for cand in self.root.glob("*.md"):
                if cand.stem.lower() == _slug(title).lower():
                    p = cand
                    break
            else:
                return None
        return Note(title=p.stem, path=p, text=p.read_text(encoding="utf-8"))

    def all_notes(self) -> list[Note]:
        notes: list[Note] = []
        for p in sorted(self.root.glob("*.md")):
            notes.append(Note(title=p.stem, path=p, text=p.read_text(encoding="utf-8")))
        return notes

    def list_titles(self) -> list[str]:
        return [n.title for n in self.all_notes()]

    # -- escrita ----------------------------------------------------------
    def write(
        self,
        title: str,
        body: str,
        *,
        tags: tuple[str, ...] = (),
        links: tuple[str, ...] = (),
        append: bool = False,
    ) -> Path:
        """Cria ou atualiza uma nota. `links` viram wikilinks no rodapé."""
        p = self.note_path(title)
        header = f"# {title}\n"
        meta = ""
        if tags:
            meta += "tags: " + " ".join(f"#{_slug(x).replace(' ', '-')}" for x in tags) + "\n"
        link_line = ""
        if links:
            link_line = "\n\n## " + ("Relacionado / Related") + "\n" + \
                " ".join(f"[[{x}]]" for x in dict.fromkeys(links)) + "\n"

        if append and p.exists():
            existing = p.read_text(encoding="utf-8").rstrip()
            stamp = f"\n\n---\n_{datetime.now():%Y-%m-%d %H:%M}_\n\n"
            p.write_text(existing + stamp + body.rstrip() + link_line + "\n",
                         encoding="utf-8")
        else:
            p.write_text(header + meta + "\n" + body.rstrip() + link_line + "\n",
                         encoding="utf-8")
        return p

    def ensure_concept(self, name: str) -> Path:
        """Garante que existe uma nota-conceito (cria stub se faltar)."""
        p = self.note_path(name)
        if not p.exists():
            self.write(
                name,
                f"_Conceito aprendido pelo VALEN. / Concept learned by VALEN._",
                tags=("concept",),
            )
        return p

    # -- grafo / links ----------------------------------------------------
    def backlinks(self, title: str) -> list[str]:
        """Notas que apontam para `title` via wikilink."""
        target = _slug(title).lower()
        out: list[str] = []
        for n in self.all_notes():
            if n.title.lower() == target:
                continue
            if any(_slug(l).lower() == target for l in n.links):
                out.append(n.title)
        return out

    def search(self, query: str, limit: int = 5) -> list[tuple[str, int]]:
        """Busca por palavras-chave; retorna [(título, score)] ordenado."""
        terms = set(keywords(query, limit=12))
        if not terms:
            return []
        scored: list[tuple[str, int]] = []
        for n in self.all_notes():
            hay = (n.title + "\n" + n.text).lower()
            score = sum(hay.count(t) for t in terms)
            if score > 0:
                scored.append((n.title, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def recall(self, query: str, limit: int = 3, char_budget: int = 6000) -> str:
        """Monta um bloco de contexto com as notas mais relevantes ao prompt."""
        hits = self.search(query, limit=limit)
        if not hits:
            return ""
        parts: list[str] = []
        budget = char_budget
        for title, _ in hits:
            note = self.read(title)
            if not note:
                continue
            snippet = note.text[:budget]
            parts.append(f"### [[{title}]]\n{snippet}")
            budget -= len(snippet)
            if budget <= 0:
                break
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Gravação de aprendizados pós-execução
# ---------------------------------------------------------------------------

def _detect_frontend_stack(session_dir: Path) -> str | None:
    """Heurística para descobrir a stack escolhida pelo Agente Frontend."""
    fdir = session_dir / "frontend"
    if not fdir.exists():
        return None
    notes = fdir / "FRONTEND_NOTES.md"
    if notes.exists():
        head = notes.read_text(encoding="utf-8", errors="ignore").lower()
        for name, label in (
            ("flutter", "Flutter"), ("react native", "React Native"),
            ("liveview", "Phoenix LiveView"), ("react", "React"),
        ):
            if name in head:
                return label
    exts = {p.suffix.lower() for p in fdir.rglob("*") if p.is_file()}
    if ".dart" in exts:
        return "Flutter"
    if ".heex" in exts:
        return "Phoenix LiveView"
    if exts & {".tsx", ".jsx", ".ts"}:
        return "React Native"
    return None


def record_session(
    vault: MemoryVault,
    session_id: str,
    prompt: str,
    runs_summary: list[tuple[str, str, int, int]],
    session_dir: Path,
    lang: str = "en",
) -> Path:
    """Escreve a nota de sessão e atualiza notas-conceito com backlinks.

    `runs_summary`: lista de (nome_do_agente, status, nº_arquivos, tokens).
    """
    # Conceitos sempre presentes do backend + os detectados.
    concepts = ["Elixir", "Phoenix", "Ecto", "ExUnit"]
    fe = _detect_frontend_stack(session_dir)
    if fe:
        concepts.append(fe)
    # Conceitos derivados do prompt (palavras-chave de domínio).
    for kw in keywords(prompt, limit=4):
        concepts.append(kw.capitalize())

    for c in concepts:
        vault.ensure_concept(c)

    session_title = f"Session {session_id}"
    lines = [
        f"**Prompt:** {prompt}",
        "",
        "## " + ("Resultado / Result"),
    ]
    for name, status, nfiles, tokens in runs_summary:
        lines.append(f"- {name}: `{status}` — {nfiles} files, {tokens:,} tokens")
    if fe:
        lines.append("")
        lines.append(f"**Frontend stack:** [[{fe}]]")
    lines.append("")
    lines.append("## " + ("Aprendizados / Learnings"))
    lines.append(
        "- " + ("Pipeline executado com backend Elixir/Phoenix, frontend "
                "multiplataforma e QA ExUnit." if lang != "en" else
                "Ran the pipeline with an Elixir/Phoenix backend, a "
                "cross-platform frontend and ExUnit QA."))

    path = vault.write(
        session_title,
        "\n".join(lines),
        tags=("session",),
        links=tuple(dict.fromkeys(concepts)),
    )
    return path
