# ⚡ VALEN / VALENOR

🇧🇷 **Orquestrador Multiagente Assíncrono de Desenvolvimento de Software** —
uma CLI em Python, estilo *Claude Code*, que transforma um único prompt em
código real produzido por três subagentes especialistas em **paralelo**.

🇬🇧 **Async multi-agent software-development orchestrator** — a Python CLI, in
the spirit of *Claude Code*, that turns a single prompt into real code produced
by three specialist sub-agents running **in parallel**.

```
                  ┌────────────────────────┐
        prompt →  │  VALENOR (orchestrator)│
                  └───────────┬────────────┘
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                  │
   🟣 Backend (Elixir)    🔵 Frontend           │  fan-out paralelo / parallel
            └─────────────────┬─────────────────┘
                              ▼
                     🟢 QA (ExUnit + mocks)        lê o código gerado / reads code
                              ▼
                  🧩 bundle_processed_data          valida + lint + status
```

---

## ✨ Recursos / Features

- **Paralelo de verdade / truly parallel** — `asyncio` + `AsyncAnthropic` com
  streaming (`messages.stream` + `get_final_message`) e *adaptive thinking*.
- **Bilíngue / Bilingual** — interface em **Inglês e Português** (`--lang en|pt|both`,
  ou auto pelo locale).
- **Memória estilo Obsidian / Obsidian-style memory** — o VALEN **aprende** a
  cada execução, gravando notas conectadas por `[[wikilinks]]`, e **lembra**
  contexto relevante antes de cada nova execução.
- **Skills** — instale e compartilhe skills com **Claude Code, Codex e
  Antigravity**, ou crie as suas.
- **Multiplataforma / cross-platform** — Linux, macOS, Windows e **Termux**
  (backend `aiohttp` opcional com fallback `httpx`).

---

## 📦 Instalação / Install

```bash
pip install .
# depois, o comando fica disponível / then the command is available:
valenor --help
```

Desenvolvimento / development: `pip install -e .`
Sem instalar / without installing: `python valen.py ...` ou `python -m valenor ...`

---

## 🚀 Uso / Usage

```bash
export ANTHROPIC_API_KEY="sua-chave"   # your key

# Atalho / shorthand:
valenor "Um app de lista de tarefas com autenticação JWT"

# Explícito / explicit, em inglês:
valenor --lang en build -p "A todo-list app with JWT auth"

# Interativo / interactive:
valenor
```

### Opções de `build`

| Flag | 🇧🇷 / 🇬🇧 | Default |
|------|-----------|---------|
| `-p, --prompt` | Especificação / spec | (interativo) |
| `-m, --model` | Modelo Anthropic / model | `claude-opus-4-8` |
| `-e, --effort` | Esforço / effort (`low`…`max`) | `high` |
| `-o, --output-dir` | Saída / output root | `./valen_output` |
| `--no-qa` | Pula QA / skip QA | — |
| `--no-memory` | Desliga a memória / disable memory | — |
| `-s, --skills` | Skills a carregar (csv) / skills to load | (todas / all) |
| `-l, --lang` | `en` · `pt` · `both` | auto |

Artefatos em / artifacts in:
`valen_output/<session_id>/{backend,frontend,qa}/`

---

## 🧠 Memória / Memory (`valenor memory ...`)

Vault Markdown em `~/.valenor/memory` com links `[[Obsidian]]`. Após cada bundle
bem-sucedido, o VALEN grava uma nota de sessão e cria/atualiza notas-conceito
(`[[Elixir]]`, `[[Phoenix]]`, a stack de frontend escolhida, `[[ExUnit]]`…).
Antes de construir, ele busca notas relacionadas e as injeta como contexto.

```bash
valenor memory list                 # lista notas / list notes
valenor memory search "auth jwt"    # busca / search
valenor memory show "Elixir"        # mostra uma nota / show a note
valenor memory links "Flutter"      # links de saída + backlinks
valenor memory graph                # grafo de links / link graph
valenor memory add "Padrão X" --body "..." --link Elixir --link Phoenix
```

---

## 🧩 Skills (`valenor skills ...`)

Uma skill é uma pasta com `SKILL.md` (mesmo formato do Claude Code).

```bash
valenor skills where                                   # diretórios por ferramenta
valenor skills new pdf-export --desc "Exporta PDF"     # cria skill / scaffold
valenor skills install ./minha-skill                   # de um caminho / from path
valenor skills install https://github.com/u/repo.git   # de git / from git
valenor skills list                                    # lista skills do VALEN

# Instalar para outra ferramenta / install into another tool:
valenor skills install ./minha-skill --tool claude-code
valenor skills install ./minha-skill --tool codex
valenor skills install ./minha-skill --tool antigravity
```

As skills do VALEN (`--tool valenor`, padrão) são injetadas nos subagentes com
**divulgação progressiva** (nome+descrição sempre; corpo quando couber).

> **Diretórios-alvo / target dirs**: os caminhos de Claude Code (`~/.claude/skills`),
> Codex (`~/.codex/skills`) e Antigravity (`~/.antigravity/skills`) são os padrões
> conhecidos e podem ser sobrescritos por variável de ambiente, ex.:
> `VALEN_SKILLS_CODEX_DIR=/caminho valenor skills install ... --tool codex`.

---

## 🤖 Agentes / Agents

| Agente | Stack | Entregáveis / Deliverables |
|--------|-------|----------------------------|
| 🟣 **Backend** | Elixir / Phoenix / Ecto / OTP | API REST/GraphQL, contextos, schemas, migrações PostgreSQL, `API_CONTRACT.md` |
| 🔵 **Frontend** | Flutter / React Native / Tailwind+LiveView | Telas, cliente de API, estado global, `FRONTEND_NOTES.md` |
| 🟢 **QA** | ExUnit + Mox | Testes unitários/integração, mocks, `QA_REPORT.md` |

---

## 📁 Estrutura / Layout

```
valenor/
  cli.py        # CLI, orquestração assíncrona, UI rich, bundle
  agents.py     # Agent + system prompts + protocolo de arquivos
  memory.py     # vault Obsidian (wikilinks, backlinks, recall)
  skills.py     # gerenciador de skills (Claude Code / Codex / Antigravity)
  i18n.py       # camada bilíngue EN/PT
  paths.py      # ~/.valenor (memória, skills)
pyproject.toml  # define o comando `valenor`
valen.py        # shim de compatibilidade
```

---

## 📱 Termux (Android)

```bash
pkg install python git
pip install .
export ANTHROPIC_API_KEY="sua-chave"
valenor
```

O backend `aiohttp` é **opcional**: se não estiver disponível, o VALEN cai
automaticamente para `httpx`. Linters externos (ex.: `mix`) também são opcionais
e só rodam se estiverem no `PATH`. / The `aiohttp` backend is optional with an
automatic `httpx` fallback; external linters are optional too.

---

## 🔧 Variáveis de ambiente / Environment variables

| Var | 🇧🇷 / 🇬🇧 |
|-----|-----------|
| `ANTHROPIC_API_KEY` | Chave da API (obrigatória p/ `build`) / API key (required for `build`) |
| `VALEN_LANG` | `en` · `pt` · `both` |
| `VALEN_HOME` | Raiz dos dados / data root (default `~/.valenor`) |
| `VALEN_MEMORY_DIR` | Vault de memória / memory vault |
| `VALEN_SKILLS_DIR` | Skills nativas / native skills |
| `VALEN_SKILLS_CLAUDE_CODE_DIR` / `_CODEX_DIR` / `_ANTIGRAVITY_DIR` | Override do destino / override target |
