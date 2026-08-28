# backend/evaluation/__init__.py
#
# Phase 9: Evaluation Systems
#
# Exports the three core evaluation components so callers can do:
#   from backend.evaluation import GoldenPR, PRReviewJudge, RegressionGate
#
# Design: evaluation is a parallel system to the agent system.
# Wiki (Evaluation-Frameworks.md): "Your evaluation is a parallel system.
# They should look similar."  The three layers here mirror:
#   golden_dataset  <->  Input Processing
#   judge           <->  Agent Reasoning
#   regression_gate <->  Output / Metrics

from backend.evaluation.golden_dataset import GoldenPR, get_slice, load_golden_dataset
from backend.evaluation.judge import JudgeScore, PRReviewJudge
from backend.evaluation.regression_gate import EvalResult, RegressionGate, SliceMetrics

__all__ = [
    "EvalResult",
    "GoldenPR",
    "JudgeScore",
    "PRReviewJudge",
    "RegressionGate",
    "SliceMetrics",
    "get_slice",
    "load_golden_dataset",
]
