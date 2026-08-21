"""Experiment registry: every research result is reproducible or it doesn't count."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from indian_quant.storage.metadata import MetadataStore


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:16]


class ExperimentTracker:
    def __init__(self, metadata: MetadataStore) -> None:
        self.metadata = metadata

    def record(
        self,
        *,
        kind: str,
        config: dict[str, Any],
        dataset_hash: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        run_id = f"{kind}-{config_hash(config)}-{uuid.uuid4().hex[:8]}"
        self.metadata.record_run(
            run_id,
            kind=kind,
            config_hash=config_hash(config),
            dataset_hash=dataset_hash,
            metrics=metrics,
        )
        return run_id
