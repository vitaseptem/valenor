"""
Gerenciador de Skills — instale e compartilhe skills com Claude Code,
Codex e Antigravity.

Uma *skill* é uma pasta contendo um `SKILL.md` (mesmo formato de skill
progressiva usado pelo Claude Code): um cabeçalho com `name`/`description`
seguido das instruções. O VALEN pode:

  • instalar skills a partir de um caminho local ou repositório git;
  • criar (scaffold) uma skill nova;
  • instalar a skill no diretório de outra ferramenta (Claude Code, Codex,
    Antigravity) além do vault nativo do VALEN;
  • carregar as skills do VALEN nos subagentes (divulgação progressiva:
    nome+descrição sempre, corpo completo quando couber no orçamento).

Skills manager — install/share skills with Claude Code, Codex and Antigravity.

NOTA: os diretórios-alvo de Claude Code/Codex/Antigravity são os padrões
conhecidos e podem ser sobrescritos por variável de ambiente
(`VALEN_SKILLS_<TOOL>_DIR`). Se a sua instalação usar outro caminho, ajuste.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .paths import skills_dir

# Diretórios padrão por ferramenta (sobrescrevíveis por env).
# Default per-tool directories (best-effort; override via env).
_TOOL_DEFAULTS = {
    "valenor": None,  # resolvido por skills_dir()
    "claude-code": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "antigravity": Path.home() / ".antigravity" / "skills",
}

TOOLS = tuple(_TOOL_DEFAULTS.keys())

_NAME_RE = re.compile(r"^name:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_DESC_RE = re.compile(r"^description:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def tool_dir(tool: str) -> Path:
    """Diretório de instalação de skills para a ferramenta dada."""
    env = os.environ.get(f"VALEN_SKILLS_{tool.upper().replace('-', '_')}_DIR")
    if env:
        return Path(env)
    if tool == "valenor":
        return skills_dir()
    default = _TOOL_DEFAULTS.get(tool)
    if default is None:
        raise ValueError(f"Ferramenta desconhecida / unknown tool: {tool!r}")
    return default


@dataclass
class Skill:
    name: str
    description: str
    path: Path  # diretório da skill
    body: str   # conteúdo completo do SKILL.md

    @classmethod
    def from_dir(cls, d: Path) -> "Skill | None":
        md = d / "SKILL.md"
        if not md.exists():
            return None
        body = md.read_text(encoding="utf-8", errors="ignore")
        nm = _NAME_RE.search(body)
        ds = _DESC_RE.search(body)
        name = (nm.group(1).strip() if nm else d.name)
        desc = (ds.group(1).strip() if ds else "")
        return cls(name=name, description=desc, path=d, body=body)


SKILL_TEMPLATE = """---
name: {name}
description: {description}
---

# {name}

{description}

## Quando usar / When to use
- Descreva aqui os gatilhos. / Describe the triggers here.

## Instruções / Instructions
1. Passo a passo da skill. / Step-by-step of the skill.
"""


class SkillManager:
    """Instala, lista e carrega skills."""

    def __init__(self, base: Path | None = None) -> None:
        self.base = base or skills_dir()
        self.base.mkdir(parents=True, exist_ok=True)

    # -- listagem ---------------------------------------------------------
    def list(self, tool: str = "valenor") -> list[Skill]:
        root = tool_dir(tool)
        if not root.exists():
            return []
        out: list[Skill] = []
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            sk = Skill.from_dir(d)
            if sk:
                out.append(sk)
        return out

    # -- instalação -------------------------------------------------------
    def _install_dir(self, src: Path, tool: str, name: str | None) -> Skill:
        sk = Skill.from_dir(src)
        if sk is None:
            raise ValueError(str(src))
        dest_root = tool_dir(tool)
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / (name or src.name)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        installed = Skill.from_dir(dest)
        assert installed is not None
        return installed

    def install(self, source: str, *, tool: str = "valenor",
                name: str | None = None) -> Skill:
        """Instala de um caminho local OU de uma URL git (clona via `git`)."""
        if source.endswith(".git") or source.startswith(("http://", "https://", "git@")):
            return self._install_from_git(source, tool, name)
        src = Path(source).expanduser().resolve()
        if not src.is_dir():
            raise ValueError(str(source))
        # Permite apontar para o pai contendo SKILL.md, ou para a própria pasta.
        if not (src / "SKILL.md").exists():
            raise ValueError(str(source))
        return self._install_dir(src, tool, name)

    def _install_from_git(self, url: str, tool: str, name: str | None) -> Skill:
        git = shutil.which("git")
        if not git:
            raise RuntimeError("git não encontrado no PATH / git not found in PATH")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([git, "clone", "--depth", "1", url, tmp],
                           check=True, capture_output=True, text=True, timeout=120)
            root = Path(tmp)
            if (root / "SKILL.md").exists():
                return self._install_dir(root, tool, name or _repo_name(url))
            # procura o primeiro SKILL.md aninhado
            for md in root.rglob("SKILL.md"):
                return self._install_dir(md.parent, tool, name or md.parent.name)
            raise ValueError(url)

    def scaffold(self, name: str, *, tool: str = "valenor",
                 description: str = "") -> Skill:
        """Cria uma skill nova a partir de um template."""
        dest = tool_dir(tool) / name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(
            SKILL_TEMPLATE.format(name=name, description=description or name),
            encoding="utf-8",
        )
        sk = Skill.from_dir(dest)
        assert sk is not None
        return sk

    # -- injeção nos agentes ---------------------------------------------
    def system_block(self, names: list[str] | None = None,
                     char_budget: int = 8000) -> tuple[str, int]:
        """Bloco de skills para o System Prompt (divulgação progressiva).

        Retorna (texto, quantidade_carregada).
        """
        skills = self.list("valenor")
        if names:
            wanted = {n.lower() for n in names}
            skills = [s for s in skills if s.name.lower() in wanted
                      or s.path.name.lower() in wanted]
        if not skills:
            return "", 0

        lines = ["## SKILLS DISPONÍVEIS / AVAILABLE SKILLS",
                 "Use estas skills quando forem relevantes à tarefa. "
                 "Use these skills when relevant to the task.\n"]
        for s in skills:
            lines.append(f"- **{s.name}** — {s.description}")
        lines.append("")
        budget = char_budget
        for s in skills:
            if budget <= 0:
                break
            chunk = s.body[:budget]
            lines.append(f"### SKILL: {s.name}\n{chunk}")
            budget -= len(chunk)
        return "\n".join(lines), len(skills)


def _repo_name(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return tail[:-4] if tail.endswith(".git") else tail
