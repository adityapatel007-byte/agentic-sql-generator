# Agentic Text-to-SQL Generator

Multi-schema natural language to SQL, with an agentic self-correction loop, schema-aware RAG, a real React UI, and a Chrome extension that floats on any page.

## Why this project

Text-to-SQL is one of the highest-value LLM applications in 2026 — every data team wants it, most in-house attempts fail on real messy schemas. This build ships the SOTA pattern (agentic + schema-RAG + self-correction) and adds a fine-tuned open-source model for cost efficiency.

## What it does

- **Multi-schema.** Upload a SQLite `.db` file or paste a Postgres connection string. Backend introspects the schema, embeds table/column descriptions, and retrieves only the relevant tables per query.
- **Agentic loop.** The model gets tools (`get_schema`, `get_sample_rows`, `execute_sql`, `get_table_relationships`), tries a query, observes errors, revises. Max 5 iterations.
- **Multi-model.** GPT-5 nano (default), Kimi K2.5 (via OpenRouter), Nvidia Nemotron 3 Nano (via NVIDIA API).
- **Fine-tuned.** LoRA fine-tune of Nemotron 3 Nano on BIRD-SQL, following Nvidia's published recipe.
- **Sleek UI.** React + Vite + Tailwind — no Streamlit AI-demo look. Chat panel, SQL preview with syntax highlighting, results table, reasoning trace.
- **Chrome extension.** Floating overlay on any page — pick your configured DB, type a question, get SQL with one-click copy.

## Architecture

```
┌────────────────┐   ┌────────────────────────────┐
│  React UI      │   │  Chrome Extension          │
│  (Vite + TW)   │   │  (MV3, floating overlay)   │
└────────┬───────┘   └────────────┬───────────────┘
         │                        │
         └────────┬───────────────┘
                  │  HTTP + SSE
         ┌────────▼─────────┐
         │   FastAPI        │
         └────────┬─────────┘
                  │
    ┌─────────────┼──────────────┐
    │             │              │
┌───▼───┐  ┌──────▼────────┐ ┌───▼──────┐
│ Agent │  │ Schema RAG    │ │ DB       │
│ Loop  │  │ (Chroma +     │ │ Adapters │
│       │  │  ST embeds)   │ │ SQLite/PG│
└───┬───┘  └───────────────┘ └──────────┘
    │
┌───▼──────────────────────────────┐
│ LLM Providers                    │
│ OpenAI · OpenRouter · NVIDIA API │
└──────────────────────────────────┘
```

## Status

v1 in progress. See `plan.md` for the full v1 → v4 roadmap.

## Getting started

```bash
# backend
cd backend
pip install -e .[dev]
cp .env.example .env  # add your OPENAI_API_KEY
uvicorn app.main:app --reload

# ui
cd ui
pnpm install
pnpm dev
```

## Roadmap

- **v1** — Backend + agentic loop + schema RAG + React UI + basic evals
- **v2** — Chrome extension
- **v3** — Multi-model benchmark (GPT-5 nano vs Kimi K2.5 vs Nemotron Nano)
- **v4** — Fine-tune Nemotron 3 Nano on BIRD-SQL (LoRA)

## License

MIT
