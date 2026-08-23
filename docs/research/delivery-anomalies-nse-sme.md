# Delivery-Percentage Anomalies in NSE Cash & SME Stocks

**Research note 001 · indian-quant platform · generated sweep `signal_sweep_delivery-7bbdff348fc43976-bf4f9365`**

*Author: POLA KONDAIAH · Data: NSE sec_bhavdata_full delivery files, Sep 2024 – Aug 2026 (485 sessions)*
*Universe: 3,389 usable instruments (EQ + SME) · 1,383,292 symbol-days*

---

## Hypothesis

DELIV_PER (share of traded quantity actually delivered) separates genuine
position-taking from intraday square-offs. Predictions:

| Pattern | Interpretation | Prediction |
|---|---|---|
| High delivery + price **up** | real accumulation | continuation (**+**) |
| High delivery + price **down** | distribution by informed holders | continuation (**−**) |
| Low delivery + price **up** | short-covering / day-trader froth | fade (**−**) |

Signal: delivery % z-score vs trailing 30-session distribution (min 15 obs),
z ≥ ±2, move threshold ±0.5%.

## Results (gross, bps, forward after signal day)

| Signal | h=1d | h=3d | h=5d | h=10d | h=20d |
|---|---|---|---|---|---|
| **dz_hi_up** (n≈6.4k/h) | **+54.5** | **+63.7** | +59.7 | +51.4 | +56.1 |
| dz_hi_dn (n≈11k/h) | − | −103.8 @20d, t=−7.9 | | | |
| dz_lo_up (n≈21k/h) | − | −103.7 @20d, t=−10.5 | | | |

All three directional predictions confirmed with t-statistics 3.0–12.9.
Delivery data demonstrably carries information.

## The SME finding

| dz_hi_up | n | mean gross |
|---|---|---|
| EQ 3d | 6,024 | +60.4 bps |
| **SME 3d** | **379** | **+116.5 bps** |

SME accumulation moves deliver ~2× the EQ drift at 3 days — but decay fast
(SME 10d turns negative): thin liquidity reprices quickly. This is the
sharpest single number in the study and the primary target for conditional
refinement.

## Stability

streak3 20d: first-half +43.2 → second-half +69.9 bps (edge strengthening).
dz_hi_up 20d: +31.6 → +105.3 bps.

## Costs — the honest wall

Measured round trip (3bps brokerage + 100bps STT sell + stamp) = **107 bps**.
No unconditional firing clears this as a naive "trade every signal" system.
Three documented paths to viability:

1. **Cluster-aware entries** — streak signals fire consecutively; one entry
   per cluster amortises cost over the whole drift (effective cost/event ÷
   cluster length)
2. **Limit-order entry** — passive fills materially reduce the brokerage+
   impact component
3. **Filter stacking** — SME 3d (+116bps) is near-viable alone; adding
   announcement-proximity or liquidity conditions (R3) targets >200bps gross

## Asymmetric use today (no shorting needed)

The two negative signals are immediately valuable as *avoidance/exit rules*
for any long book: don't buy dips under distribution; exit holdings whose
pullback rides high delivery.

---

*Reproducible: `python scripts/signal_sweep.py` against
`data/normalized/delivery/NSE`; config + metrics registered in the
experiment store under the run_id above.*
