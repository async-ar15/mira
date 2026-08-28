# MIRA — Complete 2-Week Execution Plan
### From Codebase to Deployed, Polished, Portfolio-Ready Product

> **Author:** Aman Rajput (`async-ar15`)  
> **Goal:** Deploy MIRA end-to-end, complete all deferred phases, and present a production-grade multi-agent system for job/internship applications.  
> **Hard Rule:** Nothing in Week 1.5 or Week 2 gets touched until the live URL is working and a real PR is reviewed by MIRA.

---

## THE MASTER CHECKLIST

```
PHASE 0  — 3-Day Core (Days 1-3)        → Live URL + Working System
PHASE 1  — Week 1 Work (Days 4-7)       → Compliance + Dashboard + Story
PHASE 2  — Week 2 Work (Days 8-14)      → Smart Routing + Full Compliance + Product
```

---

## ═══════════════════════════════════════
## PHASE 0 — Days 1-3: Make it Work, Impress, Present
## ═══════════════════════════════════════

---

## DAY 1 — Make it Work (The Blocker Day)

> **Goal:** MIRA is deployed, live URL is up, health endpoint returns OK.

---

### TASK 1.1 — Swap Qdrant → Tiger in `context_retriever.py`

**Why:** The embedder now generates 768-dim Google vectors, but `context_retriever.py` still calls Qdrant for ANN search. This is the last code blocker before deployment works.

**What to do:**
- Open `backend/memory/context_retriever.py`
- Remove the Qdrant client import and `QdrantClient` initialization
- Replace the `search()` call with a Tiger pgvectorscale DiskANN query:
  ```sql
  SELECT chunk_id, file_path, content, 
         embedding <=> $1::vector AS distance
  FROM code_chunks
  ORDER BY embedding <=> $1::vector
  LIMIT $2;
  ```
- Use the existing Tiger async connection pool from `backend/database/`
- Keep the same return shape — the rest of the system (RAG pipeline) should not need changes

**Verify:** Write a quick sanity check — embed a test string, insert it into `code_chunks`, run the retriever, confirm it returns the same chunk.

---

### TASK 1.2 — Run Tiger Cloud Migration SQL

**Why:** The Tiger schema (tables, hypertable, DiskANN index, continuous aggregates) must exist before the app can start.

**Steps:**
1. Create Tiger Cloud account at tigerdata.com (free $1,000 credits)
2. Create a "Hybrid applications" service in us-east-1
3. Get the connection string from the Connection tab
4. Convert to asyncpg format:
   ```
   postgres://tsdbadmin:PASS@host:5432/tsdb?sslmode=require
   → postgresql+asyncpg://tsdbadmin:PASS@host:5432/tsdb
   ```
5. Run the migration:
   ```bash
   psql "postgres://tsdbadmin:PASS@host:5432/tsdb?sslmode=require" < scripts/migrations/2026-06-tiger-init.sql
   ```
6. Verify with 4 SQL queries:
   ```sql
   SELECT extname FROM pg_extension;                          -- timescaledb + vectorscale
   SELECT * FROM timescaledb_information.hypertables;         -- agent_events
   SELECT indexname FROM pg_indexes WHERE tablename='code_chunks'; -- DiskANN index
   SELECT view_name FROM timescaledb_information.continuous_aggregates; -- rollups
   ```

---

### TASK 1.3 — Local `.env` Setup

**Fill in `c:\Ex\work\copy\mira\.env`:**
```env
GITHUB_WEBHOOK_SECRET=<generate: openssl rand -hex 32>
GITHUB_TOKEN=<PAT from github.com/settings/tokens — needs repo scope>
GITHUB_API_BASE_URL=https://api.github.com

DATABASE_URL=postgresql+asyncpg://tsdbadmin:PASS@host:5432/tsdb
TIGER_DATABASE_URL=postgresql+asyncpg://tsdbadmin:PASS@host:5432/tsdb
TIGER_EMBEDDING_DIM=768

REDIS_URL=redis://localhost:6379

GOOGLE_API_KEY=<from aistudio.google.com>
GOOGLE_EMBEDDING_MODEL=text-embedding-004
SECURITY_MODEL=gemini-3.1-pro-preview

APP_ENV=development
LOG_LEVEL=INFO
MAX_CONCURRENT_REVIEWS=5
CONFIDENCE_THRESHOLD=0.85
WORKFLOW_TIMEOUT_SECONDS=300
API_KEY=<generate: openssl rand -hex 32>
```

**Test locally:**
```bash
docker compose up
curl http://localhost:8000/health
# Expected: {"status": "ok", "version": "0.1.0", "env": "development"}
```

---

### TASK 1.4 — Railway Deployment

**Steps:**
1. Create Railway account at railway.app (sign up with GitHub)
2. New Project → Deploy from GitHub repo → connect `async-ar15/mira`
3. Name the auto-created service `mira-web`
4. Add Plugin → Redis (auto-injects REDIS_URL)
5. Add second service → Empty Service → name it `mira-worker`
   - Start Command: `python -m arq backend.job_queue.worker.WorkerSettings`
   - Connect to same `async-ar15/mira` repo
6. Set ALL env vars in both services (same as `.env` above but with `APP_ENV=production`)
7. Generate domain for `mira-web` → Settings → Networking → Generate Domain
8. Push to main to trigger deploy

**Verify:**
```bash
curl https://your-railway-url.up.railway.app/health
# Must return: {"status": "ok", ...}
```

> [!WARNING]
> **Day 1 is heavy.** Tasks 1.1–1.3 (Qdrant swap + Tiger setup + local test) are the hard part. If Railway deployment (Task 1.4) spills into Day 2 morning, that's fine — move Tasks 2.1–2.2 (test repo + webhook) to Day 2 afternoon and push the Loom recording to Day 3. Don't panic.

**✅ Day 1 Done when:** Local health endpoint returns OK. Railway is either live or actively deploying.

---

## DAY 2 — Make it Impressive on the Surface

> **Goal:** MIRA actually reviews a real PR. You have video proof of it.

---

### TASK 2.1 — Create GitHub Test Repositories

**Repos needed:**
1. `github.com/async-ar15/mira` — the main repo (already exists after Day 1 push)
2. `github.com/async-ar15/mira-test-repo` — the repo MIRA will review PRs on
   - Initialize with a README (repo must be non-empty)

---

### TASK 2.2 — Set Up GitHub Webhook

1. Go to `github.com/async-ar15/mira-test-repo` → Settings → Webhooks → Add webhook
2. Payload URL: `https://your-railway-url.up.railway.app/webhook/github`
3. Content type: `application/json`
4. Secret: same value as `GITHUB_WEBHOOK_SECRET` in your env
5. Events: Pull requests only
6. Save — should see green checkmark ✅

---

### TASK 2.3 — Wire PII Masking into `base_agent.py`

**Why:** Quick Phase 15 win. PII (API keys, emails, passwords in code) will never reach Gemini. Looks great on a resume. ~1 hour of work.

**What to do:**
- Open `backend/agents/base_agent.py`
- Import `backend/security/masking.py`
- Before every `call_gemini()` call, pass the content through the masker:
  ```python
  from backend.security.masking import mask_pii
  
  # Before LLM call
  sanitized_content = mask_pii(diff_content)
  # Then pass sanitized_content to the LLM
  ```
- The masker replaces patterns like API keys, JWT tokens, email addresses with `[REDACTED]`

---

### TASK 2.4 — Open a Real Test PR

1. Clone `mira-test-repo` locally
2. Create branch: `test/first-mira-review`
3. Add a Python file with some intentional code smells (missing error handling, a hardcoded secret, no docstrings)
4. Open PR against `main`
5. Watch Railway logs — `mira-web` should receive the webhook, `mira-worker` should run all 4 agents

**Expected result:** A structured review comment posted to the PR by MIRA within 2-3 minutes.

---

### TASK 2.5 — Record Loom Video

**2-minute script:**
- Screen 1 (20s): Show the MIRA GitHub repo — README, code structure
- Screen 2 (30s): Open the test PR in `mira-test-repo`
- Screen 3 (30s): Switch to Railway logs — show the webhook arriving, all 4 agents running in parallel
- Screen 4 (20s): Switch back to GitHub — show the review comment MIRA posted
- Screen 5 (20s): Open Tiger Cloud SQL editor — run `SELECT * FROM agent_events ORDER BY ts DESC LIMIT 10` — show live data

**✅ Day 2 Done when:** Real PR reviewed, Loom recorded.

---

## DAY 3 — Make it Presentable

> **Goal:** Clean repo, tight README, ready for resume/portfolio.

---

### TASK 3.1 — Write the README

**Structure:**
```markdown
# MIRA — Multi-agent Intelligent Review Agent

[badges: Railway deploy, Python version, License]

> A production-grade multi-agent system that reviews GitHub PRs using 
> parallel AI agents with human-in-the-loop oversight.

## Live Demo
- 🌐 Live URL: https://your-railway-url.up.railway.app
- 📹 Demo Video: [Loom link]

## Architecture
[Mermaid diagram — 4 agents fanning out from LangGraph orchestrator]

## Stack
| Layer | Technology |
|---|---|
| Backend | FastAPI |
| Orchestration | LangGraph |
| LLM | Google Gemini (3.7 Flash + 3.1 Pro Preview) |
| Vector Memory | Tiger Cloud (pgvectorscale DiskANN) |
| Observability | Tiger hypertables + continuous aggregates |
| Queue | Redis + ARQ |
| Deploy | Railway |

## How it works
[3-paragraph explanation: trigger → 4 agents → HITL gate → review posted]

## Quick Start
[Local setup steps]
```

---

### TASK 3.2 — Clean Git History (8 Organic Commits)

**Commit sequence:**
```
1. "core: backend module structure and base agent framework"
2. "feat: langgraph orchestrator with parallel agent fan-out"
3. "feat: tiger cloud data spine — vector, events, rollups"
4. "feat: four specialist agents — security, quality, tests, docs"
5. "feat: hitl gate, approval queue, and escalation logic"
6. "feat: observability, cost tracking, and budget guard"
7. "infra: railway deployment, docker, and ci configuration"
8. "docs: readme, adr decisions, and architecture documentation"
```

**How:** Use `git add -p` to stage specific chunks into each logical commit. No squashing needed — just write the history as if you built it this way.

---

### TASK 3.4 — Set GitHub Actions Secret

**Why:** The eval-gate CI job makes real Gemini API calls before deploying. Without this secret, CI will fail on every push.

**Steps:**
1. Go to `github.com/async-ar15/mira` → Settings → Secrets and variables → Actions
2. New repository secret → Name: `GOOGLE_API_KEY` → Value: your Gemini API key
3. Verify: push a commit → watch the Actions tab → eval-gate should pass

---

### TASK 3.3 — Add to Portfolio/Resume

**Resume line:**
> *MIRA — Multi-agent Intelligent Review Agent | Python, LangGraph, FastAPI, Google Gemini, Tiger Cloud | [GitHub] [Live URL]*  
> Built a production-grade system with 4 parallel AI agents reviewing GitHub PRs with confidence-weighted HITL approval, vector RAG, cost tracking, and real-time observability. Deployed on Railway with Tiger Cloud (pgvectorscale DiskANN + hypertables) as the data spine.

**✅ Phase 0 Done when:** Resume updated, repo public, live URL working.

---

## ═══════════════════════════════════════
## PHASE 1 — Days 4-7: Compliance + Dashboard + Story
## ═══════════════════════════════════════

---

## DAY 4 — Phase 15 Approach A: Quick Compliance

> **Goal:** Enterprise-aware compliance basics. ~5-6 hours total.

---

### TASK 4.1 — ARQ Nightly Purge Cron Job

**What to build:** An ARQ scheduled task that runs every night and deletes `agent_events` rows older than `RETENTION_DAYS` (default: 90 days).

**Where:** `backend/job_queue/worker.py` or a new `backend/job_queue/tasks/purge.py`

```python
async def purge_old_events(ctx):
    retention_days = settings.retention_days  # add to settings.py
    await db.execute(
        "DELETE FROM agent_events WHERE ts < NOW() - INTERVAL '$1 days'", retention_days
    )


# Register as cron in WorkerSettings:
cron_jobs = [cron(purge_old_events, hour=2, minute=0)]  # runs at 2am daily
```

**Add to `.env.example` and `settings.py`:** `RETENTION_DAYS=90`

---

### TASK 4.2 — Basic Audit Log Shipper

**What to build:** A thin async function that ships every `agent_events` write to a second destination.

**Dev (local):** Write JSON to `logs/audit/YYYY-MM-DD/` directory  
**Prod (Railway):** Ship to AWS S3 bucket

```python
# backend/observability/log_shipper.py


async def ship_audit_event(event: dict):
    if settings.app_env == "production" and settings.aws_s3_bucket:
        await ship_to_s3(event)
    else:
        await ship_to_local_file(event)


async def ship_to_local_file(event: dict):
    path = Path("logs/audit") / datetime.now().strftime("%Y-%m-%d")
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{uuid4()}.json").write_text(json.dumps(event))


async def ship_to_s3(event: dict):
    # boto3 async via aioboto3
    async with session.client("s3") as s3:
        await s3.put_object(
            Bucket=settings.aws_s3_bucket,
            Key=f"audit/{datetime.now().date()}/{uuid4()}.json",
            Body=json.dumps(event),
        )
```

**Call from:** `backend/observability/events.py` — wherever `agent_events` rows are currently written

**New dependency:** Add `aioboto3>=13.0.0` to `pyproject.toml` under dependencies. Run `pip install -e ".[dev]"` and regenerate `requirements.txt`.

**New env vars:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET` (optional — if not set, falls back to local files)

---

### TASK 4.3 — MinIO for Local Dev

> [!NOTE]
> Check if `docker-compose.dev.yml` already exists in the project root. If it doesn't, create it from scratch. It should extend the main `docker-compose.yml` but only start Redis locally (no local TimescaleDB — you're connecting directly to Tiger Cloud).

**Add to `docker-compose.dev.yml`:**
```yaml
minio:
  image: minio/minio
  command: server /data --console-address ":9001"
  ports:
    - "9000:9000"
    - "9001:9001"
  environment:
    MINIO_ROOT_USER: mira
    MINIO_ROOT_PASSWORD: miralocal123
```

**For local dev:** Set `AWS_S3_BUCKET=mira-audit` and point the boto3 endpoint to `http://localhost:9000`. Code doesn't change — same S3 API.

---

## DAYS 5-6 — Phase 17 Approach B: Quick UX Wins

> **Goal:** Dashboard feels useful and polished. Time-box each feature to 3 hours max.

---

### TASK 5.1 — Findings Filter (Severity + Agent)

**Frontend:** `frontend/src/app/reviews/[id]/page.tsx` or wherever findings are rendered

**What to add:**
- A filter bar above the findings list with two dropdowns:
  - Severity: `ALL | CRITICAL | HIGH | MEDIUM | LOW | INFO`
  - Agent: `ALL | security | quality | test | docs`
- Filter is client-side (no new API endpoint needed) — filter the already-fetched findings array with JS

**Backend (optional but cleaner):** Add query params to the existing findings endpoint:
```
GET /api/v1/reviews/{id}/findings?severity=CRITICAL&agent=security
```

---

### TASK 5.2 — Dark Mode Toggle

**Why easy:** Tailwind `dark:` classes are already in the codebase (mentioned in FUTURE_WORK.md).

**What to add:**
- A `ThemeContext` in React with `useState('light' | 'dark')`
- Toggle button in the nav bar (sun/moon icon)
- `document.documentElement.classList.toggle('dark')` on click
- Persist to `localStorage` so it remembers across sessions

---

### TASK 5.3 — Copy-as-Markdown Button

**What it does:** Renders the full PR review summary as a Markdown string and copies it to clipboard.

**Format:**
```markdown
## MIRA Review — PR #42

### 🔴 Security (Confidence: 0.92)
- **[CRITICAL]** `auth/login.py:45` — Hardcoded secret detected...

### 🟡 Quality (Confidence: 0.78)
- **[HIGH]** `utils/parser.py:12` — Function exceeds 50 lines...
```

**Where:** Add a "Copy as Markdown" button on the review detail page. One `navigator.clipboard.writeText()` call.

---

## DAY 7 — Polish and Story

> **Goal:** Architecture blog post drafted. Demo video recorded. README final pass.

---

### TASK 7.1 — Architecture Blog Post (dev.to or Hashnode)

**Outline (aim for 1000-1500 words):**
1. **The Problem** — Why AI PR review fails when it's just "prompt + diff"
2. **The Architecture** — 4 specialist agents, LangGraph fan-out, HITL gate
3. **The Data Spine** — Why one Tiger Cloud instance replaces Qdrant + Postgres + a time-series DB
4. **The LLM Stack** — Why Gemini 3.1 Pro Preview for security, 3.7 Flash for the rest
5. **What I'd Do Differently** — Honest reflection (this is what recruiters love)
6. **Links** — GitHub, live URL, demo video

---

### TASK 7.2 — Polished Demo Video (5-7 minutes)

**Script:**
- Open the README and explain the architecture diagram (1 min)
- Show the live Railway URL + health endpoint (30s)
- Open a PR on mira-test-repo (30s)
- Switch to Railway logs — narrate what's happening as agents run (1 min)
- Show the review comment MIRA posted on GitHub (30s)
- Open Tiger Cloud SQL editor — run the events query, show cost breakdown (1 min)
- Open the dashboard — show the review detail, findings filter, dark mode toggle (1 min)
- Wrap up with the GitHub repo (30s)

---

### TASK 7.3 — README Final Pass

- Add architecture diagram (generate with Mermaid or Excalidraw)
- Add blog post link
- Add demo video link
- Add a "Why MIRA is different from a simple GPT wrapper" section

**✅ Phase 1 Done when:** Blog post published, video recorded, README has all links.

---

## ═══════════════════════════════════════
## PHASE 2 — Days 8-14: Smart Routing + Full Compliance + Product
## ═══════════════════════════════════════

---

## DAYS 8-9 — Phase 20 Approach A: Feature-Flagged Auto Model Routing

> **Goal:** MIRA learns which agents can use cheaper models. One env var controls it.

---

### TASK 8.1 — Add `AUTO_MODEL_ROUTING` Feature Flag

**In `settings.py`:**
```python
auto_model_routing: bool = False  # Set AUTO_MODEL_ROUTING=true in env to enable
```

**In `.env.example`:**
```env
# When true, routing_advisor.py recommendations are acted on, not just logged
AUTO_MODEL_ROUTING=false
```

---

### TASK 8.2 — Wire `routing_advisor.py` to Actually Route

**Current state:** `routing_advisor.py::recommend_model()` logs a recommendation every call but never acts on it.

**What to change in `base_agent.py`:**
```python
from backend.economics.routing_advisor import recommend_model


async def _get_model_config(self, agent_type: AgentType) -> ModelConfig:
    base_config = get_routing_table()[agent_type]

    if settings.auto_model_routing:
        recommendation = await recommend_model(agent_type, recent_verdicts)
        if recommendation.route_to_cheaper:
            return base_config.with_model(recommendation.cheaper_model)

    return base_config
```

**What `recommend_model()` needs to return:**
```python
@dataclass
class RoutingRecommendation:
    route_to_cheaper: bool
    cheaper_model: str | None
    reason: str
```

**Logic for routing to cheaper model:**
- If the last 10 HITL verdicts for this agent_type had >80% agreement with the agent → the model is doing fine → could try a cheaper one
- If the last 10 verdicts had <60% agreement → don't change anything, the model needs to be accurate

---

### TASK 9.1 — Test the Feature Flag

- Set `AUTO_MODEL_ROUTING=false` → confirm routing behaves as before (quality/test/docs use Flash, security uses Pro Preview)
- Set `AUTO_MODEL_ROUTING=true` → confirm the routing advisor's recommendations are now applied
- Check Railway logs — should see which model was actually used per agent per review

---

## DAYS 10-11 — Phase 20 Approach B: Feedback Visibility

> **Goal:** Surface the intelligence MIRA has accumulated. Visible on the dashboard.

---

### TASK 10.1 — Nightly Feedback Aggregation ARQ Job

**What it computes:** For each agent type, the agreement rate between `agent_verdict` and `human_verdict` over the last 30 days.

```python
# backend/job_queue/tasks/feedback_aggregation.py


async def aggregate_feedback(ctx):
    results = await db.fetch("""
        SELECT 
            agent,
            COUNT(*) as total_decisions,
            SUM(CASE WHEN agent_verdict = human_verdict THEN 1 ELSE 0 END) as agreements,
            ROUND(AVG(confidence), 3) as avg_confidence
        FROM agent_events
        WHERE human_verdict IS NOT NULL
          AND ts > NOW() - INTERVAL '30 days'
        GROUP BY agent
    """)

    # Store results in a summary table or Redis for fast dashboard reads
    await store_calibration_summary(results)
```

**Add to WorkerSettings cron:** Runs at 3am daily.

---

### TASK 10.2 — Expose via `/api/v1/calibration` Endpoint

```python
# GET /api/v1/calibration
# Returns per-agent agreement rates

{
    "security": {"agreement_rate": 0.87, "total_decisions": 42, "avg_confidence": 0.91},
    "quality": {"agreement_rate": 0.73, "total_decisions": 38, "avg_confidence": 0.78},
    "test": {"agreement_rate": 0.81, "total_decisions": 35, "avg_confidence": 0.83},
    "docs": {"agreement_rate": 0.69, "total_decisions": 29, "avg_confidence": 0.75},
}
```

---

### TASK 11.1 — Add Calibration Page to Dashboard

**New page:** `frontend/src/app/calibration/page.tsx`

**What it shows:**
- A table with one row per agent: agreement rate, total decisions, avg confidence
- Color coding: green (>80%), yellow (60-80%), red (<60%)
- A short explanation: "Agreement rate = how often MIRA's verdict matches the human reviewer's verdict"
- Update frequency note: "Recomputed nightly"

---

## DAYS 12-13 — Phase 15 Approach B: Full Compliance

> **Goal:** JWT auth, signed export endpoint, real S3. Production-grade security.

---

### TASK 12.1 — Replace Single API Key with JWT Auth

**What to build:**

1. **`backend/auth/jwt.py`** — JWT encode/decode using `python-jose`
2. **`backend/auth/models.py`** — User model with roles: `admin`, `reviewer`, `viewer`
3. **A simple `users` table** in Tiger:
   ```sql
   CREATE TABLE users (
     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
     email TEXT UNIQUE NOT NULL,
     hashed_password TEXT NOT NULL,
     role TEXT NOT NULL DEFAULT 'viewer',
     created_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```
4. **`POST /auth/login`** endpoint — takes email/password, returns a signed JWT
5. **`GET /auth/me`** endpoint — returns current user info from JWT

**Gate endpoints by role:**
- `reviewer` and above → can read reviews, trigger reviews
- `admin` only → can access `/economics`, `/calibration`, `/export`

---

### TASK 12.2 — `/api/v1/export` Endpoint

**What it does:** Given a PR ID or date range, generates a signed ZIP bundle containing all agent findings, HITL decisions, cost records, and audit events for that scope.

```python
# GET /api/v1/export?pr_id=123&scope=full
# Returns: { "download_url": "https://s3.../export-abc123.zip?X-Amz-Expires=3600" }
```

**Internals:**
1. Query Tiger for all relevant events + findings for the scope
2. Serialize to JSON
3. ZIP the JSON files
4. Upload ZIP to S3
5. Generate a pre-signed S3 URL (expires in 1 hour)
6. Return the URL

---

### TASK 13.1 — Real S3 Setup with Object Lock

**Steps:**
1. Create AWS account (or use existing)
2. Create S3 bucket: `mira-audit-logs-prod`
3. Enable versioning (required for object lock)
4. Enable Object Lock → Compliance mode → 7-year retention
5. Add lifecycle rule: transition to Glacier after 90 days
6. Create IAM user with write-only policy on this bucket
7. Add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET` to Railway env vars

---

## DAY 14 — Story and Final Presentation

> **Goal:** MIRA is a product, not just a codebase.

---

### TASK 14.1 — Technical Write-Up (Medium / Personal Site)

**Title:** *"I built a self-improving multi-agent code review system — here's the architecture"*

**Deeper than the blog post from Day 7 — include:**
- The LangGraph graph structure (with code snippet)
- How the HITL confidence gate works (with decision tree diagram)
- The Tiger Cloud choice — why one DB for vectors + events + rollups
- The Gemini routing strategy (Pro Preview for security, Flash for structural)
- The feedback loop — how human verdicts feed back into model selection
- Lessons learned and what you'd do differently

---

### TASK 14.2 — Architecture Diagram (Proper)

**Tool:** Excalidraw (free, exports as PNG/SVG)

**What to show:**
```
GitHub PR Opened
      ↓
Webhook Receiver (FastAPI)
      ↓
ARQ Job Queue (Redis)
      ↓
LangGraph Orchestrator
    ↙  ↓  ↓  ↘
Security Quality Test  Docs   ← (Gemini 3.1 Pro / 3.7 Flash)
    ↘  ↓  ↓  ↙
   Aggregator Agent
      ↓
  HITL Gate
  ↙        ↘
Auto-Post  Human Queue
    ↓           ↓
GitHub Review  Slack Alert
      ↓
Tiger Cloud
├── code_chunks (DiskANN vector search)
├── agent_events (hypertable observability)
└── continuous aggregates (cost dashboard)
```

---

### TASK 14.3 — README as a Product Page

**Final README structure:**
```markdown
# MIRA

[Hero image — architecture diagram]
[Badges: deployed on Railway, Python 3.11, License MIT]

## What it does (2 sentences)
## Live Demo (URL + Video link)
## Why it's different from a GPT wrapper (bullet points)
## Architecture (embedded diagram)
## Stack table
## Quick Start (local setup)
## Deployment (Railway guide link)
## ADRs (link to docs/adr/)
## Blog post / Write-up link
## Author
```

---

## ═══════════════════════════════════════
## MASTER PROGRESS TRACKER
## ═══════════════════════════════════════

### Phase 0 — Core Deployment (Days 1-3)
- [ ] Swap Qdrant → Tiger in `context_retriever.py`
- [ ] Run Tiger migration SQL + verify 4 queries pass
- [ ] Create `.env` with all values filled
- [ ] Test locally: `docker compose up` → health returns OK
- [ ] Railway: create project, `mira-web` + `mira-worker` services
- [ ] Railway: add Redis plugin
- [ ] Railway: set all env vars in both services
- [ ] Push to GitHub → Railway deploys → live URL returns OK
- [ ] Create `mira-test-repo` on GitHub
- [ ] Set up webhook on `mira-test-repo`
- [ ] Wire `masking.py` into `base_agent.py`
- [ ] Open real test PR → MIRA posts review ✅
- [ ] Record 2-minute Loom video
- [ ] Write README (tight version)
- [ ] Clean git history (8 commits)
- [ ] Push to `async-ar15/mira`
- [ ] Add to resume + portfolio

### Phase 1 — Compliance + Dashboard + Story (Days 4-7)
- [ ] ARQ nightly purge cron job for `agent_events`
- [ ] Audit log shipper (local files in dev)
- [ ] MinIO added to `docker-compose.dev.yml`
- [ ] S3 log shipper wired in for production
- [ ] Findings filter (severity + agent) on dashboard
- [ ] Dark mode toggle
- [ ] Copy-as-markdown button
- [ ] Architecture blog post published
- [ ] 5-7 minute demo video recorded
- [ ] README final pass (architecture diagram, blog link, video link)

### Phase 2 — Smart Routing + Full Compliance + Product (Days 8-14)
- [ ] `AUTO_MODEL_ROUTING` feature flag in settings + `.env.example`
- [ ] `routing_advisor.py` acts on recommendations when flag is on
- [ ] Test feature flag: off → normal routing, on → advisor routing
- [ ] Nightly feedback aggregation ARQ job
- [ ] `/api/v1/calibration` endpoint
- [ ] Calibration page on dashboard (per-agent agreement rates)
- [ ] JWT auth replacing single API key
- [ ] `users` table migration
- [ ] `POST /auth/login` + `GET /auth/me` endpoints
- [ ] Role-gated endpoints (`admin`, `reviewer`, `viewer`)
- [ ] `/api/v1/export` endpoint with signed S3 URL
- [ ] Real S3 bucket with object-lock (Compliance mode, 7-year retention)
- [ ] Railway env vars: AWS keys + S3 bucket
- [ ] Technical write-up published (Medium or personal site)
- [ ] Architecture diagram (Excalidraw)
- [ ] README as product page (final version)

**✅ Phase 2 Done when:** Auto model routing works with feature flag, calibration page shows live agreement rates, JWT auth gates all endpoints, export endpoint returns signed S3 URL, technical write-up is published, README looks like a product page.

---

## RISK LOG

| Risk | Likelihood | Mitigation |
|---|---|---|
| Tiger Cloud setup takes longer than expected | Medium | Budget extra 2-3 hours on Day 1 |
| `context_retriever.py` swap breaks the RAG pipeline | Medium | Test with a real embed + retrieve before deploying |
| Railway deployment has env var issues | High | Check Railway logs carefully, one var at a time |
| Dashboard work runs over time | High | Hard time-box: 3 hours max per feature, ship as-is |
| JWT auth scope creep | Medium | Implement only `admin` + `viewer` roles, skip `reviewer` if tight |

---

## COST ESTIMATE (Monthly, Production)

| Service | Plan | Cost |
|---|---|---|
| Tiger Cloud | Free ($1,000 credits) | $0 for months |
| Railway (web) | Hobby | ~$5/month |
| Railway (worker) | Hobby | ~$5/month |
| Railway (Redis) | Included | $0 |
| AWS S3 (audit logs) | Pay per use | <$1/month |
| Google Gemini API | Free tier | $0 (generous free limits) |
| **Total** | | **~$10-11/month** |

---

*Plan prepared for Aman Rajput (`async-ar15`) — MIRA 2-Week Completion Sprint*  
*Start date: August 28, 2026 | Target: September 11, 2026*
