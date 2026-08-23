"""Census-drift guard tests: the SM/ST delivery-drop bug class."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from indian_quant.quality import QualityReport, detect_census_drift  # noqa: E402


class TestCensusDrift:
    def test_missing_bucket_raises_error(self):
        """Raw has SME rows but lake zero -> exactly the historical SM/ST bug."""
        report = QualityReport(dataset="t")
        detect_census_drift(
            {"EQ": 2400, "BE": 300, "SM": 292, "ST": 143},
            {"EQ": 2700, "BE": 300},
            report,
            label="delivery:2026-08-18",
        )
        drifts = [i for i in report.issues if i.code == "CENSUS_DRIFT"]
        assert len(drifts) == 2
        assert all(i.severity == "error" for i in drifts)
        assert any("SM" in i.detail for i in drifts)

    def test_matching_census_passes_with_bucket_map(self):
        report = QualityReport(dataset="t")
        detect_census_drift(
            {"EQ": 100, "SM": 50}, {"EQ": 100, "SME": 50}, report,
            bucket_map={"SM": "SME", "ST": "SME"},
        )
        assert report.passed

    def test_missing_bucket_without_map_still_fires(self):
        report = QualityReport(dataset="t")
        detect_census_drift({"EQ": 100, "SM": 50}, {"EQ": 100, "SME": 50}, report)
        drifts = [i for i in report.issues if i.code == "CENSUS_DRIFT"]
        assert len(drifts) == 1 and "SM" in drifts[0].detail

    def test_total_ratio_drop_raises(self):
        report = QualityReport(dataset="t")
        detect_census_drift({"EQ": 1000}, {"EQ": 400}, report, min_ratio=0.95)
        codes = {i.code for i in report.issues}
        assert "CENSUS_DROP" in codes

    def test_within_ratio_passes(self):
        report = QualityReport(dataset="t")
        # small legit differences (holidays filtering etc.)
        detect_census_drift({"EQ": 1000}, {"EQ": 980}, report, min_ratio=0.95)
        assert not any(i.code == "CENSUS_DROP" for i in report.issues)

    def test_zero_raw_buckets_ignored(self):
        report = QualityReport(dataset="t")
        detect_census_drift({"EQ": 100, "ST": 0}, {"EQ": 100}, report)
        assert report.passed

    def test_empty_raw_no_op(self):
        report = QualityReport(dataset="t")
        detect_census_drift({}, {"EQ": 5}, report)
        assert report.passed
