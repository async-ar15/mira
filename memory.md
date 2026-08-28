# MIRA Project Memory & Technical Changelog

> **Purpose:** This document tracks the ongoing architectural evolution of the original AI PR Review Agent to MIRA (Multi-agent Intelligent Review Agent). It serves as a deep-dive technical ledger for all refactoring, migrations, and structural engineering decisions made throughout the project's lifecycle.

---

## 1. Identity, Namespace & Branding Migration (Completed)
**Goal:** Complete eradication of legacy author namespaces and hardcoded paths to align the repository with the `async-ar15` identity.

*   **Test Fixtures & Path Resolution:** 
    *   Scrubbed hardcoded absolute paths (e.g., `/Users/ayushsingh/Desktop/ai-pr-review-agent`) across the codebase, specifically refactoring `tests/test_phase5.py` and `scripts/migrations/2026-05-bigint-github-review-id.py` to utilize relative path resolution.
*   **Object Mocking & Test Data:** 
    *   Replaced repository test strings (`ayush/test-repo` → `async-ar15/test-repo`) and mocked payloads in `tests/test_phase6.py` and `tests/test_phase19.py`.
*   **Schema Comments:** 
    *   Updated Pydantic model examples and inline documentation within `backend/models/webhook.py` and `backend/models/review.py` to reflect the new namespace.
*   **Documentation Matrix:** 
    *   Executed project-wide grep searches to purge remaining `ayush488-glitch` references across `testing-pr-review.md`, `railway-worker-fix.md`, `railway-deployment-status.md`, and all ADRs.

## 2. Framework Alignment: Synaptic Transmission (Completed)
**Goal:** Sever the conceptual and operational dependency on the external `genesis-kit-main` framework and map development workflows to the locally embedded engine within `synaptic-transmission`.

*   **Runtime Context:** 
    *   Transitioned the build environment variables from `AGENTIC_SWE_KIT_ROOT` to `SYNAPTIC_ROOT`.
    *   Mapped `AGENTIC_SWE_WIKI_ROOT` to `$SYNAPTIC_ROOT/engine/wiki`, reflecting the shift from an external clone architecture to an embedded engine.
*   **Development Rituals:** 
    *   Updated internal documentation (`KICKOFF.md`, `LOOPS.md`) to pull templates from `.synaptic/` instead of `.genesis/` and execute skills via `skills/synaptic/SKILL.md`.

## 3. LLM Provider Migration: Google Gemini (Completed)
**Goal:** Architect a complete pivot away from the OpenAI/Anthropic hybrid stack, transitioning all LLM generation and vector embedding infrastructure to Google Gemini APIs via Google AI Studio.

*   **Dependency Injection (`pyproject.toml`):** 
    *   Purged `"openai>=1.30.0"` and `"anthropic>=0.28.0"`. 
    *   Injected `"google-generativeai>=0.8.0"` as the sole LLM driver, retaining `qdrant-client` strictly for vector retrieval ops.
*   **Core Client Refactoring (`backend/tools/llm_client.py`):** 
    *   Obliterated the `call_openai()` and `call_anthropic()` methods. 
    *   Engineered a unified `call_gemini()` pipeline utilizing `genai.GenerativeModel.generate_content_async`.
    *   **JSON Mode Shift:** Capitalized on Gemini's native structured JSON capabilities by explicitly passing `response_mime_type="application/json"`. This eliminated the brittle prompt-hacking and XML-prefill workarounds previously required for Anthropic's Claude.
    *   **Cost Tracking:** Updated the token economy logic to utilize Gemini's exact usage metadata (`prompt_token_count`, `candidates_token_count`) and mapped internal cost dictionaries to Google's 3.1 Pro Preview and 3.7 Flash pricing tiers.
*   **Model Routing Engine (`backend/tools/model_router.py` & `backend/agents/base_agent.py`):** 
    *   Modified `_ROUTING_TABLE` configurations. 
    *   **Security Agent:** Upgraded to `gemini-3.1-pro-preview` to handle complex AST and logical flow reasoning.
    *   **Quality/Test/Docs Agents:** Routed to `gemini-3.7-flash` for high-throughput, structural AST evaluations.
    *   Streamlined the polymorphic dispatch logic in `BaseAgent` to exclusively validate and route via `config.provider == "gemini"`.
*   **Vector Embedder Refactoring (`backend/memory/embedder.py`):** 
    *   Swapped from OpenAI's `text-embedding-3-small` to Google's `text-embedding-004`. 
    *   Rewrote `embed_text()` and `embed_batch()` leveraging `genai.embed_content()` with `task_type="retrieval_document"`.
*   **Data Schema Mutations (`scripts/migrations/2026-06-tiger-init.sql`):** 
    *   Altered the Tiger Cloud pgvectorscale DiskANN column definitions.
    *   Changed tensor bounds from `VECTOR(256)` (legacy OpenAI configuration) to `VECTOR(768)` to natively support the Google embedding shape output.
*   **Infrastructure & CI Configurations:** 
    *   **FastAPI & Tests:** Replaced `openai_api_key` and `anthropic_api_key` dependency injections with a unified `google_api_key` in `backend/config/settings.py`. Updated all HTTP test overrides (`test_phase3b.py`, `test_phase6.py`, etc.) to mock Google credentials.
    *   **Deployment:** Stripped legacy keys from `render.yaml`, `.env.example`, and `deploy.sh`. Standardized the injection of `GOOGLE_API_KEY`.
    *   **Evaluation Gate (`tests/test_eval_gate.py`):** Modified the hard skip guards that prevented the golden evaluation suite from running without API authentication, remapping the environment variable checks to Google API keys.

---

## 4. Qdrant to Tiger Migration & Verification Fixes (Completed)
**Goal:** Finalize the swap from Qdrant to Tiger Cloud DiskANN for RAG retrieval (`context_retriever.py`) and verify the end-to-end embedding pipeline via `scripts/verify_retriever.py`. During verification, several critical integration errors were encountered and permanently resolved:

*   **Virtual Environment Path Parsing (`requirements.txt`):** 
    *   *Error:* `ERROR: c:exworkcopymira is not a valid editable requirement` when running `pip install`.
    *   *Cause:* The `requirements.txt` file contained a hardcoded, mangled Windows absolute path (`-e c:\ex\work\copy\mira`) which broke Git Bash and standard Unix pip parsers.
    *   *Fix:* Replaced the hardcoded path with the standard relative editable flag (`-e .`) and normalized the file encoding to UTF-8.
*   **Google Embedding Model Deprecation (`404 NotFound`):** 
    *   *Error:* `models/text-embedding-004 is not found for API version v1beta, or is not supported for embedContent.`
    *   *Cause:* Google recently deprecated the `text-embedding-004` identifier for `v1beta` embedding generation.
    *   *Fix:* Overhauled `backend/config/settings.py`, `.env`, and `.env.example` to point to the new flagship model: `gemini-embedding-2`.
*   **Vector Dimensionality Mismatch (`DataError`):** 
    *   *Error:* `asyncpg.exceptions.DataError: expected 768 dimensions, not 3072` during `upsert_chunks`.
    *   *Cause:* The `gemini-embedding-2` model defaults to 3072 dimensions, but the Tiger Cloud database was initialized with `VECTOR(768)`.
    *   *Fix:* Instead of dropping and recreating the database tables, modified `backend/memory/embedder.py` to pass `output_dimensionality=EMBEDDING_DIMENSIONS` (768) to `genai.embed_content()`, forcing the API to utilize Matryoshka truncation and return the exact vector size the schema expects.
*   **pgvector Python Casting (`TypeError`):** 
    *   *Error:* `TypeError: 'Vector' object is not iterable` in `_row_to_chunk`.
    *   *Cause:* Recent updates to the `pgvector` Python package removed the `__iter__` method from the `Vector` class to prevent accidental casting bugs, breaking the standard `list(row["embedding"])` idiom.
    *   *Fix:* Updated `backend/memory/tiger_client.py` to defensively check for and execute `row["embedding"].to_list()` (and `.tolist()` for numpy fallbacks) instead of wrapping the object in `list()`.

---

## Current Architecture State

The system operates as a monolithic multi-agent FastAPI microservice orchestrated via LangGraph. The LLM infrastructure is completely homogenized under the Google Gemini provider layer. The embedding generation logic correctly outputs 768-dimensional float arrays formatted for DiskANN insertion.

## Next Technical Objectives

### 1. Tiger Data Integration (Pending)
- Construct the Tiger Cloud connection pooling logic within the backend.
- Initialize the hypertable schema for `agent_events` observability.
- Map the updated `VECTOR(768)` generation logic into the `code_chunks` vector store to enable RAG-based codebase traversal.
