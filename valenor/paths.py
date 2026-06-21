"""Localização de dados persistentes do VALEN (memória, skills, config).

Tudo fica sob `~/.valenor` por padrão, sobrescrevível por variáveis de
ambiente — útil em Termux ou em ambientes com HOME não-padrão.

All persistent data lives under `~/.valenor` by default, overridable via
environment variables — handy on Termux or non-standard HOME setups.
"""

from __future__ import annotations

import os
from pathlib import Path


def valen_home() -> Path:
    """Raiz dos dados do VALEN / VALEN data root."""
    return Path(os.environ.get("VALEN_HOME", str(Path.home() / ".valenor")))


def memory_dir() -> Path:
    """Vault de memória estilo Obsidian / Obsidian-style memory vault."""
    return Path(os.environ.get("VALEN_MEMORY_DIR", str(valen_home() / "memory")))


def skills_dir() -> Path:
    """Diretório de skills nativas do VALEN / VALEN-native skills directory."""
    return Path(os.environ.get("VALEN_SKILLS_DIR", str(valen_home() / "skills")))


def ensure_dirs() -> None:
    for d in (valen_home(), memory_dir(), skills_dir()):
        d.mkdir(parents=True, exist_ok=True)
