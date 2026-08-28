# backend/agents/__init__.py
# Allowed dependencies: core, models, config, tools

from backend.agents.base_agent import BaseAgent
from backend.agents.docs_agent import DocsAgent
from backend.agents.quality_agent import QualityAgent
from backend.agents.security_agent import SecurityAgent
from backend.agents.test_agent import TestAgent

__all__ = [
    "BaseAgent",
    "DocsAgent",
    "QualityAgent",
    "SecurityAgent",
    "TestAgent",
]
