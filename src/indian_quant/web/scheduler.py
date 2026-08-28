"""APScheduler background service for daily signal cache refresh.

Runs inside the FastAPI process:
    - 18:00 IST daily: full cache rebuild (PostgreSQL + Redis)
    - Every 15 min: warm Redis from PostgreSQL (fast)

Usage:
    - Automatically started when web app starts
    - Manual trigger: POST /admin/refresh-cache (protected)
"""

from __future__ import annotations

import logging
import subprocess
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("quant.scheduler")

_scheduler: BackgroundScheduler | None = None


def _full_cache_rebuild() -> None:
    """Run cache_signals.py to rebuild PostgreSQL + Redis cache."""
    logger.info("Starting full cache rebuild...")
    try:
        result = subprocess.run(
            [sys.executable, "scripts/cache_signals.py"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            logger.info(f"Cache rebuild done: {result.stdout.strip()}")
        else:
            logger.error(f"Cache rebuild failed: {result.stderr[:500]}")
    except Exception as e:
        logger.error(f"Cache rebuild error: {e}")


def _warm_redis() -> None:
    """Quick Redis warm from PostgreSQL (no parquet scan)."""
    try:
        import json

        import pandas as pd

        from indian_quant.web.prod_config import get_pg_engine, get_redis_client

        engine = get_pg_engine()
        r = get_redis_client()

        df = pd.read_sql("SELECT * FROM cached_signals", engine)
        if df.empty:
            return

        signals = df.to_dict(orient="records")
        pipe = r.pipeline()
        pipe.delete("signals:all", "signals:buys", "signals:avoids")
        buys = [s for s in signals if s.get("signal_type") == "dz_hi_up"]
        avoids = [s for s in signals if s.get("signal_type") == "dz_hi_dn"]
        pipe.set("signals:all", json.dumps(signals, default=str), ex=3600)
        pipe.set("signals:buys", json.dumps(buys, default=str), ex=3600)
        pipe.set("signals:avoids", json.dumps(avoids, default=str), ex=3600)
        pipe.set("signals:date", signals[0]["signal_date"] if signals else "", ex=3600)
        pipe.set("signals:count", str(len(signals)), ex=3600)
        for s in signals:
            pipe.hset("signals:by_symbol", s["symbol"], json.dumps(s, default=str))
        pipe.expire("signals:by_symbol", 3600)
        pipe.execute()
        logger.info(f"Redis warmed: {len(signals)} signals")
    except Exception as e:
        logger.warning(f"Redis warm failed: {e}")


def start_scheduler() -> BackgroundScheduler:
    """Start the background scheduler. Call once at app startup."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Full rebuild daily at 18:00 IST (after market close)
    _scheduler.add_job(
        _full_cache_rebuild,
        CronTrigger(hour=18, minute=0, timezone="Asia/Kolkata"),
        id="daily_cache_rebuild",
        name="Daily cache rebuild (18:00 IST)",
        replace_existing=True,
    )

    # Warm Redis every 15 minutes
    _scheduler.add_job(
        _warm_redis,
        IntervalTrigger(minutes=15),
        id="redis_warm",
        name="Redis warm (every 15m)",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started: daily rebuild @ 18:00 IST, Redis warm every 15m")
    return _scheduler


def stop_scheduler() -> None:
    """Stop the scheduler. Call at app shutdown."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    """Return scheduler status for admin endpoint."""
    if not _scheduler:
        return {"running": False}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })
    return {"running": True, "jobs": jobs}
