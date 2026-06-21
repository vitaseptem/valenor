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

## 📦 Instalação 1-comando / one-command install

Os launchers **detectam a plataforma**, criam um **ambiente virtual (`.venv`)**,
instalam o VALEN e o abrem. São idempotentes (re-execuções reaproveitam o venv).

| Plataforma | Comando |
|------------|---------|
| 🐧 Linux · 🍎 macOS · 📱 Termux | `./valenor.sh` |
| 🍎 macOS (clicável no Finder) | `valenor.command` (duplo-clique) |
| 🪟 Windows | `valenor.bat` (duplo-clique ou `valenor.bat` no terminal) |

```bash
chmod +x valenor.sh valenor.command   # só na 1ª vez no Unix
./valenor.sh                          # abre o chat / opens the chat
./valenor.sh "um app de tarefas"      # execução única / one-shot
./valenor.sh skills where             # qualquer subcomando / any subcommand
```

### Instalação manual / manual install

```bash
pip install .            # expõe o comando `valenor`
pip install -e .         # desenvolvimento / development
python -m valenor        # sem instalar / without installing
python valen.py ...      # shim de compatibilidade
```

---

## 💬 Terminal / Chat (estilo Claude Code)

`valenor` **sem argumentos** abre um terminal interativo parecido com o do
Claude Code: banner de boas-vindas, prompt persistente, histórico, *auto-suggest*
e comandos `/slash`. Cada mensagem comum dispara o pipeline multiagente (uma
tarefa por turno). / Bare `valenor` opens a Claude Code-style interactive chat.

```text
╭──────────────────────────────────────────────╮
│  ✻ Welcome to VALENOR                          │
│    /help for commands · /exit to quit          │
│    cwd: /seu/projeto                            │
╰──────────────────────────────────────────────╯
valenor › um app de tarefas com autenticação
valenor › /model claude-opus-4-8
valenor › /effort xhigh
valenor › /status
```

Comandos: `/help` `/status` `/model <id>` `/effort <low…max>` `/lang <en|pt|both>`
`/qa` `/memory [list|search]` `/skills` `/clear` `/exit`.

## 🚀 Uso / Usage

```bash
export ANTHROPIC_API_KEY="sua-chave"   # your key

valenor                                       # chat interativo / interactive chat
valenor "Um app de tarefas com auth JWT"      # atalho execução única / one-shot
valenor --lang en build -p "A todo-list app"  # explícito / explicit
valenor chat -m claude-opus-4-8 -e xhigh      # chat com opções / chat with options
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
  chat.py       # terminal/chat interativo estilo Claude Code
  agents.py     # Agent + system prompts + protocolo de arquivos
  memory.py     # vault Obsidian (wikilinks, backlinks, recall)
  skills.py     # gerenciador de skills (Claude Code / Codex / Antigravity)
  i18n.py       # camada bilíngue EN/PT
  paths.py      # ~/.valenor (memória, skills)
pyproject.toml  # define o comando `valenor`
valenor.sh      # launcher Linux/macOS/Termux (detecta SO + venv)
valenor.command # launcher clicável macOS (Apple)
valenor.bat     # launcher Windows
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
