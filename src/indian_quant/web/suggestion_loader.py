"""Load suggestion data for web dashboard views."""

from __future__ import annotations

from typing import Any

from indian_quant.web import data_loader as dl


def get_suggestion_summary() -> dict[str, Any]:
    settings = dl._settings()
    from indian_quant.storage import MetadataStore
    md = MetadataStore(settings.storage.metadata_dsn)
    s = md.suggestions_summary()
    md.close()
    return dl._sanitize(s)


def get_suggestion_loader():
    """Return the MetadataStore-based suggestion functions."""
    settings = dl._settings()
    from indian_quant.storage import MetadataStore
    return MetadataStore(settings.storage.metadata_dsn)
