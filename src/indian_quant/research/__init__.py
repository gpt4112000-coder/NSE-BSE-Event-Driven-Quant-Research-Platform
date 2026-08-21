"""Research engine: features, event studies, experiments."""

from indian_quant.research.event_studies import EventStudyResult, event_study
from indian_quant.research.experiments import ExperimentTracker, config_hash
from indian_quant.research.friction import compute_friction_metrics

__all__ = [
    "EventStudyResult",
    "ExperimentTracker",
    "compute_friction_metrics",
    "config_hash",
    "event_study",
]
