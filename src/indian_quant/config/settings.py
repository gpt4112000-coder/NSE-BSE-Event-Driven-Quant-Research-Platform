"""Configuration loading for the indian-quant platform."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PathsConfig(BaseModel):
    data_root: Path = Path("data")


class McpConfig(BaseModel):
    base_url: str = "http://localhost:3000/mcp"
    transport: str = "http"
    timeout_seconds: float = 60.0
    max_retries: int = 3


class StorageConfig(BaseModel):
    raw_layout: str = "source/tool/date"
    parquet_compression: str = "zstd"
    duckdb_path: Path = Path("data/research.duckdb")
    metadata_dsn: str = "sqlite:///data/metadata.db"


class QualityConfig(BaseModel):
    max_gap_days: int = 10
    price_tolerance_pct: float = 0.5
    fail_on_error: bool = False


class UpstoxConfig(BaseModel):
    enabled: bool = False
    sandbox: bool = True
    api_key_env: str = "UPSTOX_API_KEY"
    access_token_env: str = "UPSTOX_ACCESS_TOKEN"
    ws_url: str = "wss://api.upstox.com/v3/feed/market-data-feed"
    instrument_master_url: str = (
        "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz"
    )

    def resolve_token(self) -> str | None:
        """Token resolution order: env var -> upstox_tokens.json (BseIndiaApi
        convention, searched from CWD upward) -> None."""
        token = os.environ.get(self.access_token_env)
        if token:
            return token
        for candidate in [Path.cwd(), *Path.cwd().parents]:
            token_file = candidate / "upstox_tokens.json"
            if token_file.exists():
                try:
                    import json

                    data = json.loads(token_file.read_text())
                    value = str(data.get("access_token") or "")
                    if value:
                        return value
                except (OSError, ValueError):
                    continue
        return None

    def resolve_api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class BacktestConfig(BaseModel):
    venue: str = "NSE"
    account_type: str = "CASH"
    starting_balance_inr: float = 1_000_000
    catalog_path: Path = Path("data/catalog")
    fill_prob: float = 1.0
    slippage_ticks: int = 0
    brokerage_bps: float = 3.0
    stt_sell_bps: float = 100.0
    stamp_buy_bps: float = 1.5
    flat_fee_per_order: float = 0.0


class Settings(BaseModel):
    defaults: str = "development"
    paths: PathsConfig = Field(default_factory=PathsConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    upstox: UpstoxConfig = Field(default_factory=UpstoxConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    @property
    def data_root(self) -> Path:
        return self.paths.data_root

    def raw_dir(self, source: str) -> Path:
        return self.data_root / "raw" / source

    @property
    def normalized_dir(self) -> Path:
        return self.data_root / "normalized"

    @property
    def validated_dir(self) -> Path:
        return self.data_root / "validated"

    @property
    def catalog_dir(self) -> Path:
        return self.backtest.catalog_path


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file, resolving ``defaults`` chains.

    Resolution order (lowest to highest): built-in defaults -> defaults chain
    files -> the named file itself.
    """
    if config_path is None:
        candidates = [Path("configs/development.yaml"), Path("../configs/development.yaml")]
        config_path = next((c for c in candidates if c.exists()), None)
        if config_path is None:
            return Settings()
        return Settings.model_validate(yaml.safe_load(config_path.read_text()) or {})

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    payload: dict[str, Any] = yaml.safe_load(path.read_text()) or {}

    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor: str | None = payload.get("defaults")
    while cursor and cursor not in seen:
        seen.add(cursor)
        dep = path.parent / f"{cursor}.yaml"
        if not dep.exists():
            break
        dep_payload: dict[str, Any] = yaml.safe_load(dep.read_text()) or {}
        chain.append(dep_payload)
        cursor = dep_payload.get("defaults")

    merged: dict[str, Any] = {}
    for layer in reversed(chain):
        merged = _deep_merge(merged, layer)
    merged = _deep_merge(merged, {k: v for k, v in payload.items() if k != "defaults"})
    return Settings.model_validate(merged)
