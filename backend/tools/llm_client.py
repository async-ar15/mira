# backend/tools/llm_client.py
#
# LLM API client — the ONLY place that calls Gemini directly.
#
# WHY A WRAPPER?
# The same reason redis_client.py exists. Without this:
#   - SecurityAgent imports google.generativeai directly -> tightly coupled
#   - Rate limit handling is duplicated across 4 agents
#   - Token counting happens inconsistently
#
# With this wrapper:
#   - Agents call: await llm_client.call_gemini(model="gemini-3.7-flash", messages=[...])
#   - They never import genai directly
#   - Rate limit + retry logic lives in ONE place
#   - Token counting is automatic and centralized
#
# PROVIDERS SUPPORTED:
#   Google Gemini -> gemini-3.7-flash, gemini-3.1-pro-preview
#
# STRUCTURED OUTPUT:
# Gemini supports structured output (JSON mode) natively.
# JSON mode: uses response_mime_type="application/json"
#
# RETRY STRATEGY (from Stability Patterns wiki):
# "Every external call is a potential stab-in-the-back."
# We retry on:
#   - Rate limits / API errors -> exponential backoff, up to 3 retries
#
# TOKEN COUNTING:
# Every call returns a LLMResponse with input_tokens and output_tokens.
# The model router uses this for cost attribution per agent (Phase 10 full tracing).

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from backend.core.exceptions import AgentError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 16 — fire-and-forget cost log writer.
#
# Called after each successful LLM call. Reads the active workflow context
# (set by base_agent.analyze) so we never have to thread a workflow_id arg
# through every retry path. Failures here are swallowed inside
# record_llm_call so a DB hiccup cannot break the review pipeline.
# ---------------------------------------------------------------------------
async def _persist_call_log(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_seconds: float,
    is_valid_json: bool,
) -> None:
    try:
        from backend.economics import record_llm_call
        from backend.observability.workflow_context import get_workflow_context

        ctx = get_workflow_context()
        await record_llm_call(
            workflow_id=ctx.workflow_id,
            agent_type=ctx.agent_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_seconds * 1000.0,
            is_valid_json=is_valid_json,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("llm_call_log_helper_failed | error=%s", exc)


# ---------------------------------------------------------------------------
# Token cost table (USD per 1000 tokens)
# ---------------------------------------------------------------------------
_TOKEN_COSTS: dict[str, dict[str, float]] = {
    # Gemini models (Google AI Studio pricing)
    "gemini-3.7-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-3.1-pro-preview": {"input": 0.00125, "output": 0.005},
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2.5-pro": {"input": 0.00125, "output": 0.005},
}


@dataclass
class LLMResponse:
    """
    The structured response from one LLM API call.
    """

    content: dict | str
    input_tokens: int
    output_tokens: int
    model_used: str
    latency_seconds: float
    estimated_cost_usd: float = 0.0
    is_valid_json: bool = True


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estimates the cost of one LLM API call in USD.
    """
    costs = _TOKEN_COSTS.get(model, {})
    if not costs:
        return 0.0
    input_cost = (input_tokens / 1000) * costs.get("input", 0.0)
    output_cost = (output_tokens / 1000) * costs.get("output", 0.0)
    return round(input_cost + output_cost, 8)


class LLMClient:
    """
    Async LLM client supporting Google Gemini.

    LIFECYCLE:
    This client is stateless.
    No shared state between calls (thread-safe, safe to use concurrently).
    The API keys are read from Settings at call time.

    USAGE:
    From an agent:
      response = await llm_client.call_gemini(
          model="gemini-3.7-flash",
          messages=[{"role": "user", "content": "..."}],
          system_prompt="You are a code quality reviewer...",
      )
      findings = response.content  # already parsed dict
    """

    MAX_RETRIES = 3
    BASE_RETRY_DELAY = 1.0

    async def call_gemini(
        self,
        model: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        json_mode: bool = True,
        max_tokens: int = 2048,
        api_key: str | None = None,
    ) -> LLMResponse:
        """
        Makes one call to the Google Gemini API.

        Uses google.generativeai SDK.
        JSON mode: uses response_mime_type="application/json"
        """
        from backend.config import get_settings

        cfg = get_settings()
        key = api_key or cfg.google_api_key

        genai.configure(api_key=key)

        generation_config = genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.1,
        )
        if json_mode:
            generation_config.response_mime_type = "application/json"

        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system_prompt,
            generation_config=generation_config,
        )

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            gemini_messages.append({"role": role, "parts": [msg["content"]]})

        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                response = await gemini_model.generate_content_async(gemini_messages)

                latency = time.monotonic() - start
                raw_content = response.text or "{}"

                try:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                except AttributeError:
                    input_tokens = 0
                    output_tokens = 0

                # Parse JSON
                is_valid_json = True
                try:
                    parsed = json.loads(raw_content)
                except json.JSONDecodeError:
                    logger.warning(
                        "gemini_json_parse_failed | model=%s attempt=%d | "
                        "trying partial extraction",
                        model,
                        attempt,
                    )
                    parsed = _try_extract_json(raw_content)
                    is_valid_json = bool(parsed)

                cost = _compute_cost(model, input_tokens, output_tokens)
                logger.info(
                    "gemini_call | model=%s input_tokens=%d output_tokens=%d "
                    "latency=%.2fs cost=$%.6f",
                    model,
                    input_tokens,
                    output_tokens,
                    latency,
                    cost,
                )

                await _persist_call_log(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_seconds=latency,
                    is_valid_json=is_valid_json,
                )

                return LLMResponse(
                    content=parsed,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model,
                    latency_seconds=round(latency, 3),
                    estimated_cost_usd=cost,
                    is_valid_json=is_valid_json,
                )

            except google_exceptions.ResourceExhausted as e:
                last_error = e
                delay = self.BASE_RETRY_DELAY * (2**attempt)
                logger.warning(
                    "gemini_rate_limit | model=%s attempt=%d/%d | waiting %.1fs",
                    model,
                    attempt + 1,
                    self.MAX_RETRIES,
                    delay,
                )
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)

            except google_exceptions.GoogleAPIError as e:
                last_error = e
                # Usually we want to retry on API errors
                delay = self.BASE_RETRY_DELAY * (2**attempt)
                logger.warning(
                    "gemini_server_error | model=%s attempt=%d/%d | waiting %.1fs",
                    model,
                    attempt + 1,
                    self.MAX_RETRIES,
                    delay,
                )
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)

            except Exception as e:
                last_error = e
                delay = self.BASE_RETRY_DELAY * (2**attempt)
                logger.warning(
                    "gemini_unexpected_error | model=%s attempt=%d/%d error=%s",
                    model,
                    attempt + 1,
                    self.MAX_RETRIES,
                    str(e),
                )
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)

        raise AgentError(
            f"Gemini call failed after {self.MAX_RETRIES + 1} attempts: {last_error}",
            agent_name=model,
        ) from last_error


def _try_extract_json(text: str) -> dict | list:
    """
    Output guardrail: tries to extract valid JSON from partially malformed LLM output.
    """
    if not text:
        return {}

    cleaned = text.strip()
    for fence in ["```json", "```JSON", "```"]:
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence) :]
            break
    cleaned = cleaned.removesuffix("```")
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = cleaned.find(start_char)
        if start == -1:
            continue
        end = cleaned.rfind(end_char)
        if end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    logger.error("json_extraction_failed | could not extract JSON from LLM output")
    return {}


llm_client = LLMClient()
