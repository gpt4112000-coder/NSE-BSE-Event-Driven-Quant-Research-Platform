# Pre-Live Verification Sprint — Verdict

**Status: PAPER-VALIDATION PHASE ACTIVE · Go-live gate PENDING (0/20 settled)**

---

## Gate 1 — Cluster portfolio backtest ✅ executed, ❌ base config fails

Realistic simulation (8 slots · ₹250 risk/trade · 30% capital cap · 107bps
round trip · cluster-first entries) over Sep 2024 – Aug 2026:

| Variant | n | NET bps/trade | win | maxDD | verdict |
|---|---|---|---|---|---|
| dz_hi_up price<100 stop7% | 339 | **−151.8** | 36% | 4.4% | stops destroy edge |
| dz_hi_up price<100 no-stop | 309 | −90.3 | 40% | — | still negative |
| dz_hi_up price<200 no-stop | 354 | **+19.5** | 40% | <15% | **passes Gate 1** |

**Key discovery:** the 7% stop was itself the largest loss driver —
10-day delivery-drift trades recover from temporary drawdowns; hard stops
crystallize them.

## Gate 2 — Deflation check ✅ executed

45 hypotheses corrected via Bonferroni + BH(FDR 10%):

- **dz_hi_up signal family SURVIVES** at 1d/3d/5d (p≈0.0) — the delivery
  information edge is genuine, not selection luck.
- Negative signals (dz_hi_dn / dz_lo_up) also survive → avoidance rules robust.
- The specific price<100@10d variant does NOT survive (discovered in-sample).
- price<200 portfolio variant likewise needs forward validation.

## Gate 3 — Paper ledger 🟢 LIVE

`paper_track.py snapshot/settle/report` wired to metadata store.
First snapshot (Aug 22 close): APOLLOTYRE · AROGRANITE · GOKUL · PRAVEG
opened as paper positions. Gate: ≥20 settled sessions with realized net
≥ +25bps avg.

---

## Verdict & path

1. Signal family validated; specific live configuration NOT yet approved.
2. `price<200 no-stop` variant promoted to **forward paper testing** —
   flagged as in-sample discovery requiring out-of-sample confirmation.
3. Nightly cron (when enabled): snapshot new candidates → settle matured
   papers → report progress toward 20-settlement gate.
4. On PASS: generate `docs/operations/golive.md` checklist (manual-assist
   routine, position rules, kill-switch cadence). On FAIL: honest kill
   documented, research continues.

*Reproduce: `make cluster-backtest`, `python scripts/deflation_check.py`,
`python scripts/paper_track.py report`*
