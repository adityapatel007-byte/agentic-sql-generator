# Build Plan

## v1 — Web app MVP
1. Scaffold repo structure and deps
2. DB adapter layer (SQLite + Postgres) with safety enforcement
3. Schema RAG (embeddings + Chroma retrieval)
4. Agentic loop (generate → execute → observe → self-correct)
5. FastAPI backend with SSE streaming endpoint
6. React + Vite + Tailwind UI (impeccable + design-taste-frontend)
7. Eval suite (BIRD-SQL subset + custom tests)
8. Dockerize + deploy to Railway/Fly.io

## v2 — Chrome extension
- MV3 extension, React inside
- Floating overlay on any page
- DB picker (from user's registered connections)
- One-click copy + paste-into-active-tab
- Shares the FastAPI backend

## v3 — Multi-model benchmark
- Provider adapter pattern (OpenAI, OpenRouter, NVIDIA API)
- Side-by-side eval: GPT-5 nano vs Kimi K2.5 vs Nemotron 3 Nano
- Report: latency, cost, execution accuracy

## v4 — Fine-tune Nemotron 3 Nano on BIRD-SQL
- Follow Nvidia's published BIRD-SQL LoRA recipe
- Training pipeline + checkpoint management
- Eval: fine-tuned vs base Nemotron vs GPT-5 nano

## Non-goals (v1)
- Write queries (INSERT/UPDATE/DELETE) — read-only enforcement
- Cross-DB joins
- Auth/multi-tenant (single-user local first)
