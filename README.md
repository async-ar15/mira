# MIRA — Multi-agent Intelligent Review Agent

![MIRA Banner](mira-banner.png)

A production-grade, open source AI Pull Request Review Agent. A developer opens a PR. A webhook fires. Four specialist sub-agents run in parallel — security, code quality, test coverage, documentation. Each one reasons over the diff plus codebase context retrieved via semantic search. An aggregator merges findings into a single structured review and posts it back to the PR. Low-confidence findings route to a human approval queue.

Every phase has a gate: tests pass, evals pass, a written checkpoint before the next phase begins.

---

## What MIRA Does

- Receives a GitHub PR webhook
- Runs 4 parallel specialist sub-agents: security, quality, test coverage, docs
- Each agent reasons about its domain using the PR diff + codebase context (RAG via pgvectorscale)
- Posts structured review comments back to the GitHub PR
- Routes low-confidence findings to a human approval queue (HITL)
- Every agent action, LLM call, and decision is recorded in a Tiger Cloud hypertable
- Real-time cost and latency dashboards powered by Tiger continuous aggregates
- Learns from merged vs rejected reviews over time

---

## Data Layer — Tiger Cloud (TimescaleDB)

Most AI projects juggle three separate stores: a vector DB for RAG, a time-series store for traces, and Postgres for structured data. MIRA uses [Tiger Cloud](https://tigerdata.com) — a managed TimescaleDB instance — to collapse all three into one Postgres database.

One connection pool. One backup policy. One place to reason about the data.

### Three roles, one database

| Layer | Tiger Feature | What it does |
|---|---|---|
| Semantic memory | pgvectorscale DiskANN | Stores chunked code, ADRs, and prior reviews. 4 specialist agents query it for context on every PR. Replaces Qdrant entirely. |
| Agent events | Hypertables | Every span, LLM call, tool call, and decision lands in one time-ordered table: agent_events. Powers the trace viewer, audit trail, and cost ledger. |
| Live dashboards | Continuous aggregates | Real-time rollups for cost per PR, p95 latency per agent, rejection rate. Materialized so the dashboard stays fast as history grows. |
| Cost control | Hypertables + aggregates | Token cost attribution per agent span. Budget caps read from the same aggregate the dashboard does. |

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.10) |
| Orchestration | LangGraph (parallel fan-out, checkpointing) |
| Job Queue | Redis + ARQ |
| Memory | Tiger Cloud (pgvectorscale DiskANN + hypertables) |
| LLM | Google Gemini (routing per agent) |
| Sandbox | Docker (isolated code execution) |
| Frontend | Next.js (review dashboard, HITL queue, trace viewer) |
| Observability | OpenTelemetry + Tiger hypertables |
| Deploy | Railway |

---

## Architecture

```
GitHub PR webhook
       |
       v
FastAPI ingress  (idempotency key + HMAC)
       |
       v  enqueue(review_job)
ARQ Worker - LangGraph orchestrator
       |
       +--> security_agent
       +--> quality_agent
       +--> tests_agent
       +--> docs_agent
                |
                v
         aggregator --> HITL?
                |
                v
         post_to_github
       |         |         |
       v         v         v
   Tiger       Tiger       Tiger
   pgvector-   hyper-      continuous
   scale       tables      aggregates
   (memory)    (events)    (dashboard)
```

Modular monolith. One FastAPI service, 23 internal modules. See docs/adr/ADR-002-architecture-style.md.

---

## Local Development

```bash
cp .env.example .env
docker compose up
```

The API will be available at http://localhost:8000. Health check: GET /health

---

## 20-Phase Build Roadmap

| # | Phase | Tiger |
|---|---|---|
| 0 | Cognitive Design — autonomy level, HITL boundaries | |
| 1 | System Architecture — module graph, ADRs | |
| 2 | Frontend Engineering — dashboard shell, streaming | |
| 3 | Backend and API Layer — FastAPI, webhook, idempotency | |
| 4 | Workflow Orchestration — LangGraph, parallel fan-out | |
| 5 | LLM and Reasoning Layer — model routing, prompt registry | |
| 6 | Memory Architecture — RAG on pgvectorscale, hybrid retrieval | Tiger |
| 7 | Tooling and Sandboxing — tool registry, Docker sandbox | |
| 8 | Multi-Agent Systems — 4 specialists, contracts, aggregator | |
| 9 | Evaluation Systems — golden dataset, LLM-as-judge | |
| 10 | Observability and Tracing — OTel spans in agent_events hypertable | Tiger |
| 11 | Security Architecture — threat model, RBAC, audit trail | |
| 12 | Reliability Engineering — retries, circuit breakers, idempotency | |
| 13 | Infrastructure — Tiger Cloud provisioning, Tiger MCP wiring | Tiger |
| 14 | Data Engineering — ingestion pipeline, hypertable schema design | Tiger |
| 15 | Governance and Compliance — audit logs, explainability | |
| 16 | Economics and Cost Control — per-agent cost via continuous aggregates | Tiger |
| 17 | Developer Experience — prompt playground, trace viewer | |
| 18 | CI/CD for AI — prompt versioning, eval gates, canary releases | |
| 19 | Human in the Loop — approval queue, escalation, feedback | |
| 20 | Continuous Learning — drift detection from continuous aggregates | Tiger |

---

## Project Structure

```
backend/
  api/              REST endpoints (webhook, reviews, economics, HITL)
  agents/           4 specialist agents (security, quality, tests, docs)
  config/           Settings, environment
  data/             Ingestion pipeline, embedding, freshness
  database/         Postgres async engine + Tiger pool
  economics/        Cost repository, budget caps
  job_queue/        ARQ worker, job definitions
  memory/           TigerMemoryClient (pgvectorscale + hybrid search)
  observability/    Events spine, OTel traces
  orchestrator/     LangGraph graph, nodes, engine
  reliability/      Circuit breakers, retries
  tools/            Tool registry, Docker sandbox

docs/
  adr/              Architecture Decision Records (ADR-001 to ADR-005)

scripts/
  migrations/       2026-06-tiger-init.sql — idempotent schema DDL

tests/              Phase-by-phase test suite
frontend/           Next.js dashboard
```

---

## Key Design Decisions

- Tiger replaces both Qdrant (vectors) and plain Postgres — one connection, one backup
- Redis stays for the ARQ job queue (right tool for that job)
- agent_events hypertable is the single source of truth for traces, costs, and audit
- Continuous aggregates keep the dashboard fast at any scale — no full table scans
- DiskANN index over code_chunks gives 28x lower p95 latency at 99% recall
- HITL threshold is confidence-weighted — low-confidence findings queue for human review
- LangGraph abstracted behind core/workflow_engine.py — swappable to Temporal at scale

---

Built by [Aman Rajput](https://github.com/async-ar15)
