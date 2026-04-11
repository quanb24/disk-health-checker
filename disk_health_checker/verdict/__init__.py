"""Global verdict engine — aggregates per-check results into one assessment."""

from .types import GlobalVerdict, OverallHealth, Urgency, RecommendedUsage
from .engine import compute_global_verdict

__all__ = [
    "GlobalVerdict",
    "OverallHealth",
    "Urgency",
    "RecommendedUsage",
    "compute_global_verdict",
]
