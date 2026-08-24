"""Deflation check tests: Bonferroni + Benjamini-Hochberg selection math."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import deflation_check as dc  # noqa: E402


class TestPFromT:
    def test_large_t_small_p(self):
        p = dc.p_from_t(4.0)
        assert 0 < p < 0.001

    def test_zero_t_unit_p(self):
        assert dc.p_from_t(0.0) == 1.0

    def test_nan_t_unit_p(self):
        assert dc.p_from_t(float("nan")) == 1.0


class TestCorrections:
    def _hyps(self, ps):
        return [{"source": "s", "name": f"h{i}", "t_stat": 5.0,
                 "n": 100, "p": p, "mean_bps": 10}
                for i, p in enumerate(ps)]

    def test_bonferroni_threshold_scales_with_family(self):
        # single hypothesis: p=0.03 significant
        one = dc.bonferroni(self._hyps([0.03]))
        # fifty hypotheses: same p NOT significant
        fifty = dc.bonferroni(self._hyps([0.03] * 49 + [0.9]))
        assert len(one) == 1
        assert len(fifty) == 0

    def test_bh_selects_rank_prefix(self):
        hyps = self._hyps([0.001, 0.002, 0.003, 0.5, 0.9])
        rej = dc.benjamini_hochberg(hyps, q=0.10)
        # m=5: thresholds 0.02,0.04,0.06,... -> first three qualify
        assert rej == {0, 1, 2}

    def test_bh_no_rejections_when_all_large(self):
        hyps = self._hyps([0.5, 0.6, 0.7])
        assert dc.benjamini_hochberg(hyps, q=0.10) == set()


class TestCollect:
    def test_collect_reads_generated_jsons(self, tmp_path):
        gen = tmp_path / "generated"
        gen.mkdir()
        (gen / "delivery_sweep.json").write_text(json.dumps({
            "full": {"dz_hi_up": {"3d": {"n": 6000, "t_stat": 8.6,
                                          "mean_bps": 63.7}}}}))
        (gen / "delivery_r2b.json").write_text(json.dumps({
            "dz_hi_up price<100": {"10d": {"n": 1541, "t_stat": 3.14,
                                            "mean_bps": 104.8}}}))
        hyps = dc.collect_hypotheses(gen)
        names = [h["name"] for h in hyps]
        assert any(n == "dz_hi_up|3d" for n in names)
        assert any(n == "dz_hi_up price<100|10d" for n in names)

