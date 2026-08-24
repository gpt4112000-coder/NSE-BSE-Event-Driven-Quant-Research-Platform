"""Paper ledger tests: record/open/settle/summary roundtrips."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from indian_quant.storage import MetadataStore  # noqa: E402


@pytest.fixture
def md(tmp_path):
    return MetadataStore(f"sqlite:///{tmp_path}/meta.db")


class TestPaperLedger:
    def test_record_and_open(self, md):
        pid = md.record_paper_signal(symbol="GOKUL", close_at_signal=42.55,
                                     qty=83, horizon_days=10, stop_pct=0.07,
                                     segment="EQ", note="z=4.2")
        papers = md.open_papers()
        assert len(papers) == 1
        assert papers[0]["symbol"] == "GOKUL"
        assert papers[0]["status"] == "OPEN"
        _ = pid

    def test_settle_computes_net_bps(self, md):
        pid = md.record_paper_signal(symbol="TEST", close_at_signal=100.0,
                                     qty=10, horizon_days=10, stop_pct=0.07)
        result = md.settle_paper_signal(pid, exit_date="2026-08-24",
                                        exit_close=102.0, cost_bps=107.0)
        # gross = +200bps, net = 200 - 107 = 93
        assert result["realized_net_bps"] == pytest.approx(93.0)

    def test_settle_short_side_sign_flip(self, md):
        # side SELL profits when price falls; sign flip honored via side column
        pid = md.record_paper_signal(symbol="X", close_at_signal=100.0,
                                     qty=5, horizon_days=5, stop_pct=0.05,
                                     side="SELL")
        result = md.settle_paper_signal(pid, exit_date="d",
                                        exit_close=98.0, cost_bps=50.0)
        assert result["realized_net_bps"] == pytest.approx(150.0)

    def test_papers_summary_counts(self, md):
        a = md.record_paper_signal(symbol="A", close_at_signal=10.0, qty=1,
                                   horizon_days=5, stop_pct=0.05)
        b = md.record_paper_signal(symbol="B", close_at_signal=20.0, qty=1,
                                   horizon_days=5, stop_pct=0.05)
        md.settle_paper_signal(a, exit_date="d", exit_close=11.0, cost_bps=107.0)
        s = md.papers_summary()
        assert s["open"] == 1 and s["settled"] == 1
        _ = b

    def test_settle_missing_id_raises(self, md):
        with pytest.raises(ValueError):
            md.settle_paper_signal(999, exit_date="d", exit_close=1.0)
