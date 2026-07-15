# Agentic SQL Generator — Claude Code Context

This file is auto-loaded every session. It captures scope, status, and how the owner (ASP) wants to work. Read this before touching code.

## What this project is

A multi-schema natural-language-to-SQL generator using the SOTA 2026 pattern: **agentic loop with self-correction + schema-aware RAG**. Ships as a FastAPI backend, a real React UI (not Streamlit), a Chrome extension overlay, and a fine-tuned open-source model on BIRD-SQL.

This is ASP's 5th portfolio project in an 8-project LLM series aimed at landing an AI/ML job. Resume angle is: "agentic + schema RAG + fine-tuning + browser extension, all from one repo."

## Locked scope

Do not re-open these decisions unless a new hard constraint appears — they were made deliberately.

**Architecture**
- Agentic loop: generate → execute → observe error → self-correct, **max 5 iterations**
- Tools the agent sees: `retrieve_tables`, `get_sample_rows`, `execute_sql`, `get_table_relationships`
- Schema RAG: one Chroma collection per connection (not one global), doc-per-table format leading with the table name
- Read-only enforcement at two layers: `assert_read_only` (sqlglot) + adapter-level (SQLite read-only URI, Postgres read-only txn + statement_timeout)

**Models**
- v1 baseline: **Nemotron 3 Nano (`nemotron-3-nano-30b-a3b`) via NVIDIA API** (chosen 2026-07-14; MoE 30B/~3B active, 1M ctx, explicitly built for tool calling; OSS-first + same family as the v4 LoRA fine-tune → clean before/after story). `settings.default_model` defaults to `nvidia/nemotron-3-nano-30b-a3b`; override via `DEFAULT_MODEL` env var if the exact API id on build.nvidia.com differs. `settings.nvidia_base_url` = `https://integrate.api.nvidia.com/v1`.
- v3 benchmark: Nemotron Nano vs Kimi K2.5 (OpenRouter) vs GPT-5 nano (OpenAI)
- v4 fine-tune: Nemotron Nano + LoRA on BIRD-SQL, following Nvidia's published recipe

**Stack**
- Backend: FastAPI, async, Python 3.11+ (required for `asyncio.timeout`)
- UI: React + Vite + Tailwind. **Not Streamlit** — the whole point is a sleek non-AI-demo look.
- Extension: MV3, React inside, floats on any page, shares the FastAPI backend
- Deploy: Docker + Railway/Fly.io + GitHub Actions CI

## Build order (v1 → v4)

- [x] **v1 step 1** — Scaffold repo structure and deps
- [x] **v1 step 2** — DB adapter layer (SQLite + Postgres, read-only, safety layer)
- [x] **v1 step 3** — Schema RAG (Chroma + bge-small-en-v1.5, per-connection isolation)
- [x] **v1 step 4** — Agentic loop with the 4 tools above (Nemotron provider + AgentTools + AgentLoop, generate-execute-observe-correct, max 5 iterations)
- [x] **v1 step 5** — FastAPI backend with SSE streaming endpoint (connections + ask, AgentLoop.astream, typed events, TestClient coverage)
- [ ] **v1 step 6** — React + Vite + Tailwind UI (NEXT UP)
- [ ] **v1 step 7** — Eval suite (BIRD-SQL subset + custom tests)
- [ ] **v1 step 8** — Dockerize + deploy
- [ ] **v2** — Chrome extension
- [ ] **v3** — Multi-model benchmark
- [ ] **v4** — Nemotron LoRA fine-tune on BIRD-SQL

## Current test status

Last verified 2026-07-15 (Python 3.12): **104 passed, 4 skipped, 1 slow deselected**.

- 4 skipped are live-Postgres tests. Enable by exporting `TEST_POSTGRES_URL` to a running Postgres and running `pytest tests/test_postgres.py`.
- Real bge-small-en-v1.5 e2e is marked `@pytest.mark.slow`. Opt in with `pytest -m slow`. First run downloads the model (~130 MB).
- Agent tests inject a `ScriptedProvider` — the fast suite never touches the network or the real Nemotron endpoint.

Run the fast suite: `pytest -m "not slow"` from `backend/`.

## Owner preferences (ASP)

**Model choice — OSS-first.** ASP prefers open-source models over proprietary when a competitive OSS option exists. v1 baseline is Nemotron Nano (OSS, same family as the v4 fine-tune target). When picking a model for anything new, first check whether Kimi, Nemotron, Llama, Qwen, DeepSeek, etc. would work — don't default to OpenAI/Anthropic/Google APIs just because they're easy. If proprietary is genuinely the right call, explain what makes the OSS options fall short.

**Ask before major decisions.** Architectural choices, stack changes, model swaps, scope changes — surface the tradeoff and let ASP call it. Small tactical choices (variable names, error message wording, test structure) are yours to make.

**Clear loose ends before advancing.** At the start of each session, do a quick pass on any active project: uncommitted files, known bugs, unpushed commits. Propose the punch list, close it, then move to new work. Do not start a shiny new feature while a broken thing sits unfixed.

**Don't re-litigate settled decisions.** If we agreed on a stack or model choice, treat it as final unless you have a concrete new reason (bug found, assumption broke, new release). ASP's phrasing from a prior session: "don't doubt yourself." Applies now to Nemotron Nano as v1 baseline.

**Be concise.** ASP has explicit preferences for terse, direct responses. Cut throat-clearing, cut recaps, cut "great question." The task list widget already shows progress — don't narrate every step in prose too.

**Files, not just code in chat.** Portfolio matters. Save real files, run real tests, actually verify things work. No "here's roughly what it would look like."

## Repo conventions

- Python 3.11+ (see `backend/pyproject.toml`)
- Ruff for lint (`ruff check .`), pytest for tests
- Async everywhere on the backend — no sync fallbacks
- Every DB adapter satisfies the `DBAdapter` protocol in `app/db/base.py`
- Every embedder satisfies the `Embedder` protocol in `app/rag/embedder.py`
- Test files mirror module layout: `app/db/postgres.py` → `tests/test_postgres.py`
- Live-DB / real-model tests use `@pytest.mark.slow` or `pytest.mark.skipif` — never make the fast suite depend on external services

## Where things are

```
backend/
  app/
    config.py                 # settings via pydantic-settings, loads .env
    db/
      base.py                 # DBAdapter protocol + TableInfo, ColumnInfo, QueryResult, ForeignKey
      safety.py               # assert_read_only — sqlglot-based, dialect-aware
      sqlite.py               # SQLiteAdapter (aiosqlite, read-only URI)
      postgres.py             # PostgresAdapter (psycopg async, read-only txn)
      registry.py             # ConnectionRegistry singleton + auto-indexing on register
    rag/
      embedder.py             # Embedder protocol + SentenceTransformer + FakeEmbedder
      schema_index.py         # SchemaIndex (Chroma, per-connection)
    agent/
      provider.py             # LLMProvider protocol + NemotronProvider (NVIDIA API, OpenAI-compat)
      tools.py                # AgentTools + TOOL_SCHEMAS (retrieve_tables, get_sample_rows, get_table_relationships, execute_sql)
      loop.py                 # AgentLoop, generate→execute→observe→correct, hard cap on iterations
    api/
      deps.py                 # DI: registry_dep, provider_dep (overridable in tests)
      connections.py          # POST /connections/sqlite|postgres, GET /connections, DELETE
      ask.py                  # POST /ask/{connection_id} — SSE stream via loop.astream()
    main.py                   # FastAPI app + CORS + lifespan (closes adapters on shutdown)
    models/
      api.py                  # RegisterPostgresRequest, ConnectionInfo, AskRequest, ...
      events.py               # IterationEvent, AssistantTextEvent, ToolCallEvent, ToolResultEvent, FinalEvent
  tests/
    conftest.py               # sample_sqlite_path fixture
    test_safety.py, test_sqlite_adapter.py, test_postgres.py, test_registry.py, test_rag.py
    test_agent_tools.py, test_agent_loop.py   # step-4 coverage; loop tests use ScriptedProvider
    test_api_connections.py, test_api_ask.py  # step-5 FastAPI + SSE; provider overridden via Depends
```

## Immediate next step

**v1 step 6 — React + Vite + Tailwind UI.** Frontend that talks to the FastAPI backend from step 5:
- Vite + React + TS + Tailwind scaffold under `ui/`.
- Screens: (1) connect-a-database (SQLite upload / Postgres form), (2) ask-a-question with live trace panel that consumes the SSE stream via `EventSource` and renders `iteration / assistant / tool_call / tool_result / final` events, (3) results table for `final_columns` / `final_rows`.
- Not Streamlit. Aim for a sleek, non-AI-demo look.
- Point at `http://localhost:8000` by default; make it configurable.

Also worth doing whenever: set `NVIDIA_API_KEY` in `backend/.env` so `scripts/smoke_nemotron.py` can exercise the real endpoint end-to-end.
