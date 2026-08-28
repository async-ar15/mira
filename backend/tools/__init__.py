# backend/tools/__init__.py
# Allowed dependencies: core, models, config

from backend.tools.capability_scope import (
    CAPABILITY_MAP,
    CapabilityScope,
    CapabilityViolationError,
    check_capability,
    get_allowed_tools,
    raise_if_not_allowed,
)
from backend.tools.llm_client import LLMClient, LLMResponse, llm_client
from backend.tools.model_router import ModelConfig, get_all_configs, get_model_config
from backend.tools.sandbox import (
    Sandbox,
    SandboxConfig,
    SandboxResult,
    SandboxViolationError,
)
from backend.tools.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    ToolSchema,
    tool_registry,
)

__all__ = [
    # LLM client
    "LLMClient",
    "LLMResponse",
    "llm_client",
    # Model router
    "ModelConfig",
    "get_model_config",
    "get_all_configs",
    # Tool registry (Phase 7)
    "ToolRegistry",
    "ToolSchema",
    "ToolDefinition",
    "tool_registry",
    # Sandbox (Phase 7)
    "Sandbox",
    "SandboxConfig",
    "SandboxResult",
    "SandboxViolationError",
    # Capability scope (Phase 7)
    "CapabilityScope",
    "CapabilityViolationError",
    "CAPABILITY_MAP",
    "get_allowed_tools",
    "check_capability",
    "raise_if_not_allowed",
]
