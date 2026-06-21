# ⚡ VALEN

**Orquestrador Multiagente Assíncrono de Desenvolvimento de Software** — uma CLI
em Python, no estilo *Claude Code*, que transforma um único prompt em código
real produzido por três subagentes especialistas trabalhando **em paralelo**.

Um prompt central dispara subprocessos independentes que consomem a API da
Anthropic via `asyncio`, e seus resultados convergem para um **nó de
consolidação** que valida os artefatos em disco, roda um linter básico e exibe
um status de sucesso brilhante no terminal.

```
                 ┌────────────────────────┐
        prompt → │   VALEN (orquestrador) │
                 └───────────┬────────────┘
            ┌────────────────┼────────────────┐
            ▼                ▼                 │
   🟣 Backend (Elixir)   🔵 Frontend          │  (fan-out paralelo)
            └────────────────┬────────────────┘
                             ▼
                     🟢 QA (ExUnit + mocks)     (lê o código gerado)
                             ▼
                  🧩 bundle_processed_data       (valida + lint + status)
```

## Agentes

| Agente | Stack | Entregáveis |
|--------|-------|-------------|
| 🟣 **Backend** | Elixir / Phoenix / Ecto / OTP | API REST/GraphQL, contextos, schemas, migrações PostgreSQL, `API_CONTRACT.md` |
| 🔵 **Frontend** | Flutter / React Native / Tailwind+LiveView | Telas, cliente de API, estado global, `FRONTEND_NOTES.md` |
| 🟢 **QA** | ExUnit + Mox | Testes unitários/integração, mocks, `QA_REPORT.md` |

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
export ANTHROPIC_API_KEY="sua-chave"

# Direto:
python valen.py --prompt "Um app de lista de tarefas com autenticação JWT"

# Interativo (entrada com prompt_toolkit):
python valen.py
```

### Opções

| Flag | Descrição | Default |
|------|-----------|---------|
| `-p, --prompt` | Especificação do software | (interativo) |
| `-m, --model` | Modelo Anthropic | `claude-opus-4-8` |
| `-e, --effort` | Esforço de raciocínio (`low`…`max`) | `high` |
| `-o, --output-dir` | Raiz de saída | `./valen_output` |
| `--no-qa` | Pula o agente de QA | — |

Os artefatos são gravados em `valen_output/<session_id>/{backend,frontend,qa}/`.

## Detalhes técnicos

- **Assíncrono de verdade**: cada subagente é uma corrotina; o fan-out usa
  `asyncio.gather`. As requisições usam o cliente `AsyncAnthropic` com **streaming**
  (`messages.stream` + `get_final_message`) para evitar timeouts em respostas longas.
- **Adaptive thinking**: `thinking={"type": "adaptive"}` + `output_config.effort`.
- **Terminal rico**: `rich` (tabela de progresso ao vivo, spinners, painéis) e
  `prompt_toolkit` (entrada interativa).
- **Protocolo de arquivos**: cada agente emite blocos
  `=== FILE: caminho ===` … `=== END FILE ===` que o orquestrador materializa em
  disco, com sanitização contra *path traversal*.

## Termux (Android)

VALEN roda no Termux. O backend `aiohttp` é **opcional**: se ele não estiver
disponível, o VALEN cai automaticamente para o backend `httpx` do SDK — sem
nenhuma ação necessária. Os linters externos (ex.: `mix`) também são opcionais
e só rodam se estiverem no `PATH`.

```bash
pkg install python
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sua-chave"
python valen.py
```
