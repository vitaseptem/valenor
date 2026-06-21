"""Camada de internacionalização (Inglês + Português).

VALEN fala os dois idiomas. O idioma é resolvido por (nesta ordem):
`--lang`, env `VALEN_LANG`, locale do sistema (`LANG`), com fallback `en`.
O modo especial `both` exibe as mensagens-chave em inglês e português.

VALEN speaks both languages. Language is resolved by (in order): `--lang`,
`VALEN_LANG` env, system locale (`LANG`), falling back to `en`. The special
`both` mode renders key messages in English and Portuguese.
"""

from __future__ import annotations

import os

LANGS = ("en", "pt", "both")

# Cada chave: {"en": "...", "pt": "..."}. Use {placeholders} nomeados.
STRINGS: dict[str, dict[str, str]] = {
    "no_api_key": {
        "en": "ANTHROPIC_API_KEY is not set. Export your key first:\n"
              '  export ANTHROPIC_API_KEY="your-key"',
        "pt": "ANTHROPIC_API_KEY não está definida. Exporte sua chave antes:\n"
              '  export ANTHROPIC_API_KEY="sua-chave"',
    },
    "no_prompt": {
        "en": "No prompt provided. Exiting.",
        "pt": "Nenhum prompt fornecido. Encerrando.",
    },
    "interrupted": {
        "en": "Interrupted by user.",
        "pt": "Interrompido pelo usuário.",
    },
    "ask_prompt": {
        "en": "describe the software you want: ",
        "pt": "descreva o software desejado: ",
    },
    "header_prompt": {"en": "Prompt", "pt": "Prompt"},
    "header_engine": {"en": "Engine", "pt": "Motor"},
    "pipeline_title": {"en": "Parallel Pipeline", "pt": "Pipeline Paralelo"},
    "col_agent": {"en": "Agent", "pt": "Agente"},
    "col_status": {"en": "Status", "pt": "Status"},
    "col_tokens": {"en": "Tokens (out)", "pt": "Tokens (out)"},
    "col_files": {"en": "Files", "pt": "Arquivos"},
    "col_time": {"en": "Time", "pt": "Tempo"},
    "col_detail": {"en": "Detail", "pt": "Detalhe"},
    "st_waiting": {"en": "waiting", "pt": "aguardando"},
    "st_thinking": {"en": "thinking", "pt": "pensando"},
    "st_generating": {"en": "generating", "pt": "gerando"},
    "st_done": {"en": "done", "pt": "concluído"},
    "st_error": {"en": "error", "pt": "erro"},
    "bundle_node": {
        "en": "Consolidation Node — bundle_processed_data",
        "pt": "Nó de Consolidação — bundle_processed_data",
    },
    "lint_title": {"en": "Lint & Validation", "pt": "Lint & Validação"},
    "bundle_ok": {
        "en": "BUNDLE CONSOLIDATED SUCCESSFULLY",
        "pt": "BUNDLE CONSOLIDADO COM SUCESSO",
    },
    "bundle_pending": {
        "en": "BUNDLE HAS PENDING ISSUES",
        "pt": "BUNDLE COM PENDÊNCIAS",
    },
    "s_session": {"en": "Session", "pt": "Sessão"},
    "s_dir": {"en": "Directory", "pt": "Diretório"},
    "s_files": {"en": "Files", "pt": "Arquivos"},
    "s_tokens": {"en": "Tokens (out)", "pt": "Tokens (out)"},
    "s_agents": {"en": "Agents", "pt": "Agentes"},
    "s_valid": {"en": "valid", "pt": "válidos"},
    "mem_learned": {
        "en": "Memory updated — learnings recorded in the vault",
        "pt": "Memória atualizada — aprendizados registrados no vault",
    },
    "mem_recalled": {
        "en": "Recalled {n} related note(s) from memory",
        "pt": "Lembrei de {n} nota(s) relacionada(s) da memória",
    },
    "mem_empty": {"en": "Memory vault is empty.", "pt": "O vault de memória está vazio."},
    "mem_not_found": {"en": "Note not found: {title}", "pt": "Nota não encontrada: {title}"},
    "mem_outgoing": {"en": "Outgoing links", "pt": "Links de saída"},
    "mem_backlinks": {"en": "Backlinks", "pt": "Backlinks"},
    "skills_none": {"en": "No skills installed.", "pt": "Nenhuma skill instalada."},
    "skills_installed": {"en": "Installed: {name}", "pt": "Instalada: {name}"},
    "skills_loaded": {
        "en": "Loaded {n} skill(s) into the agents",
        "pt": "Carreguei {n} skill(s) nos agentes",
    },
    "skills_invalid": {
        "en": "Source has no SKILL.md: {src}",
        "pt": "Fonte sem SKILL.md: {src}",
    },
    "lang_directive": {
        "en": "Write all code comments and Markdown deliverables (.md) in English.",
        "pt": "Escreva todos os comentários de código e entregáveis Markdown (.md) "
              "em português.",
    },
    "lang_directive_both": {
        "en": "Write code comments and Markdown deliverables bilingually "
              "(English and Portuguese).",
        "pt": "Escreva comentários de código e entregáveis Markdown de forma "
              "bilíngue (inglês e português).",
    },
}


def detect_lang(override: str | None = None) -> str:
    """Resolve o idioma efetivo / resolve the effective language."""
    if override:
        ov = override.lower()
        if ov in LANGS:
            return ov
    env = (os.environ.get("VALEN_LANG") or os.environ.get("LANG") or "").lower()
    if env in LANGS:
        return env
    if env.startswith("pt"):
        return "pt"
    return "en"


def t(key: str, lang: str = "en", **kw: object) -> str:
    """Traduz `key` para `lang`. Em `both`, junta inglês e português."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    if lang == "both":
        en = entry["en"].format(**kw)
        pt = entry["pt"].format(**kw)
        return en if en == pt else f"{en}  ·  {pt}"
    return entry.get(lang, entry["en"]).format(**kw)
