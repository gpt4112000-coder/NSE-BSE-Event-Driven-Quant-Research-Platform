"""Event-type keyword classifier tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from indian_quant.research.event_types import EVENT_TYPES, classify, classify_frame


class TestClassify:
    def test_results(self):
        assert classify("Financial Results for Q2 FY27") == "RESULTS"
        assert classify("Audited results June 30") == "RESULTS"

    def test_dividend(self):
        assert classify("Interim Dividend of Rs 5 per share") == "DIVIDEND"

    def test_ma(self):
        assert classify("Acquisition of stake in subsidiary") == "M_A"
        assert classify("Merger with ABC Ltd") == "M_A"

    def test_board_meeting(self):
        assert classify("Board Meeting Intimation") == "BOARD_MEETING"

    def test_buyback(self):
        assert classify("Buyback of equity shares") == "BUYBACK"

    def test_split_bonus(self):
        assert classify("Stock Split / Sub-division of shares") == "SPLIT_BONUS"
        assert classify("Bonus issue 1:1") == "SPLIT_BONUS"

    def test_credit_rating(self):
        assert classify("Credit Rating assigned by CRISIL") == "CREDIT_RATING"

    def test_investor_meet(self):
        assert classify("Institutional Investor Meeting intimation") == "INVESTOR_MEET"

    def test_other_fallback(self):
        assert classify("Certificate under SEBI regulations") == "OTHER"
        assert classify("") == "OTHER"
        assert classify(None) == "OTHER"

    def test_taxonomy_complete(self):
        for t in ("RESULTS", "DIVIDEND", "M_A", "BUYBACK"):
            assert t in EVENT_TYPES

    def test_classify_frame(self):
        import pandas as pd

        df = pd.DataFrame({"headline": ["Board Meeting on Monday", "Random note"]})
        out = classify_frame(df)
        assert list(out["event_type"]) == ["BOARD_MEETING", "OTHER"]
