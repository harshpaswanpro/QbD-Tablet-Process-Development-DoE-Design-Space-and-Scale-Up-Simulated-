"""
Step 6: Confirmatory batches (CB) at the proposed operating point.

Idea: the DoE models are only useful if they predict NEW batches. We "manufacture" 3 independent
lab-scale confirmatory batches at the robust point from Step 5, then check
    (a) every CQA meets its specification, and
    (b) every observed value falls inside the model's 95% PREDICTION interval
        (computed at the factor values actually achieved in that batch).

Reads : outputs/doe_results.csv, outputs/models.json, outputs/step5_results.json
Writes: outputs/cb_results.csv, outputs/cb_confirmation.png

IMPORTANT: the "lab" is the same documented simulator as Step 3 (new random seed, so new noise).
These are SIMULATED confirmation results, not real experiments.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

OUT = Path("outputs")
SEED = 99
N_CB = 3
ALPHA = 0.05
CENTRE = {"A": 4.0, "B": 4.0, "C": 12.0}
HALF = {"A": 2.0, "B": 2.0, "C": 4.0}
PROC_SD_REAL = {"A": 0.15, "B": 0.15, "C": 0.40}   # same assumption as Step 5
SPEC = {"Hardness_kp": (5.0, 10.0), "Friability_pct": (None, 1.0),
        "DT_min": (None, 15.0), "Dissolution_Q30": (80.0, None)}
rng = np.random.default_rng(SEED)

# ------------------------------------------------------------------ operating point from Step 5
rp = json.loads((OUT / "step5_results.json").read_text())["robust_point"]
setpoint = {"A": rp["Binder_pct"], "B": rp["Disintegrant_pct"], "C": rp["Compression_kN"]}
print(f"Confirmatory batches at: binder {setpoint['A']:.1f}% | disintegrant {setpoint['B']:.1f}% | "
      f"force {setpoint['C']:.1f} kN  ({N_CB} batches)")

# ------------------------------------------------------------------ refit models (for prediction intervals)
d = pd.read_csv(OUT / "doe_results.csv")
saved = json.loads((OUT / "models.json").read_text())
Xc = pd.DataFrame({"A": d["Binder_pct_coded"], "B": d["Disintegrant_pct_coded"], "C": d["Compression_kN_coded"]})
for t in ["AB", "AC", "BC"]:
    Xc[t] = Xc[t[0]] * Xc[t[1]]
for t in ["A2", "B2", "C2"]:
    Xc[t] = Xc[t[0]] ** 2

FITS = {}
for name, spec in saved.items():
    y = d[name].astype(float)
    y = np.log(y) if spec["transform"] == "ln" else y
    fit = sm.OLS(y, sm.add_constant(Xc[spec["terms"]])).fit()
    saved_beta = np.array([spec["coef"][t] for t in ["const"] + spec["terms"]])
    assert np.allclose(fit.params.values, saved_beta, atol=1e-6), f"{name}: refit differs from models.json"
    FITS[name] = (fit, spec)


def terms_row(a, b, c, terms):
    vals = {"A": a, "B": b, "C": c, "AB": a * b, "AC": a * c, "BC": b * c, "A2": a * a, "B2": b * b, "C2": c * c}
    return [1.0] + [vals[t] for t in terms]


# ------------------------------------------------------------------ the simulated lab (same relationships as Step 3)
def lab_batch(a, b, c):
    hard = 7.0 + 1.6 * a - 0.3 * b + 2.2 * c + 0.4 * a * c - 0.5 * c**2 + rng.normal(0, 0.30)
    friab = 0.55 * np.exp(-0.30 * (hard - 7.0)) * np.exp(rng.normal(0, 0.10))
    dt = np.exp(np.log(6.0) + 0.25 * a - 0.45 * b + 0.30 * c + 0.10 * b**2 + rng.normal(0, 0.05))
    q30 = min(100.0, 88.0 - 14.0 * np.log(dt / 6.0) - 1.5 * a + rng.normal(0, 1.5))
    return {"Hardness_kp": hard, "Friability_pct": friab, "DT_min": dt, "Dissolution_Q30": q30}


rows = []
for i in range(1, N_CB + 1):
    # factors actually achieved in the batch (set-point + process variability), recorded in coded units
    act = {k: (setpoint[k] - CENTRE[k]) / HALF[k] + rng.normal(0, PROC_SD_REAL[k] / HALF[k]) for k in "ABC"}
    obs = lab_batch(act["A"], act["B"], act["C"])
    for name, (fit, spec) in FITS.items():
        x0 = np.array([terms_row(act["A"], act["B"], act["C"], spec["terms"])])
        sf = fit.get_prediction(x0).summary_frame(alpha=ALPHA)
        pred, lo, hi = sf["mean"].iloc[0], sf["obs_ci_lower"].iloc[0], sf["obs_ci_upper"].iloc[0]
        if spec["transform"] == "ln":
            pred, lo, hi = np.exp(pred), np.exp(lo), np.exp(hi)
        o = obs[name]
        slo, shi = SPEC[name]
        spec_ok = (slo is None or o >= slo) and (shi is None or o <= shi)
        rows.append(dict(Batch=f"CB{i}", Binder_pct=CENTRE["A"] + HALF["A"] * act["A"],
                         Disintegrant_pct=CENTRE["B"] + HALF["B"] * act["B"],
                         Compression_kN=CENTRE["C"] + HALF["C"] * act["C"],
                         Response=name, Observed=o, Predicted=pred, PI_low=lo, PI_high=hi,
                         Error_pct=100 * (o - pred) / pred, In_PI=bool(lo <= o <= hi), Meets_spec=bool(spec_ok)))

res = pd.DataFrame(rows)
res.round(3).to_csv(OUT / "cb_results.csv", index=False)

# ------------------------------------------------------------------ report
print("\nAchieved factor values per batch:")
print(res.groupby("Batch")[["Binder_pct", "Disintegrant_pct", "Compression_kN"]].first().round(2).to_string())
print("\nConfirmation results (95% prediction intervals):")
show = res[["Batch", "Response", "Observed", "Predicted", "PI_low", "PI_high", "Error_pct", "In_PI", "Meets_spec"]].copy()
print(show.round(2).to_string(index=False))

n = len(res)
print(f"\nMeets specification: {int(res['Meets_spec'].sum())} of {n} results")
print(f"Inside 95% prediction interval: {int(res['In_PI'].sum())} of {n} results")
print(f"Mean absolute prediction error by response (%):")
print(res.groupby("Response")["Error_pct"].apply(lambda s: s.abs().mean()).round(2).to_string())

all_spec = bool(res["Meets_spec"].all())
n_out = int((~res["In_PI"]).sum())
if all_spec and n_out == 0:
    verdict = "ACCEPT: all CBs meet specification and the model predicted every result."
elif all_spec:
    verdict = (f"ACCEPT WITH NOTE: all CBs meet specification, but {n_out} result(s) fell outside the 95% PI "
               "(expected by chance about 5%); document and monitor in the exhibit batches.")
else:
    verdict = "REJECT / INVESTIGATE: at least one CQA failed specification. Re-evaluate the operating point."
print(f"\nDecision: {verdict}")

# ------------------------------------------------------------------ plot
fig, axes = plt.subplots(1, 4, figsize=(16, 4))
for ax, name in zip(axes, SPEC):
    r = res[res["Response"] == name].reset_index(drop=True)
    x = np.arange(len(r))
    ax.errorbar(x, r["Predicted"], yerr=[r["Predicted"] - r["PI_low"], r["PI_high"] - r["Predicted"]],
                fmt="o", color="#0B7285", capsize=6, label="Predicted +/- 95% PI")
    ax.scatter(x, r["Observed"], color="#F28C28", marker="s", s=70, zorder=5, label="Observed (CB)")
    for lim in SPEC[name]:
        if lim is not None:
            ax.axhline(lim, ls="--", color="grey", lw=1)
    ax.set_xticks(x); ax.set_xticklabels(r["Batch"]); ax.set_title(name)
axes[0].legend(fontsize=8)
fig.suptitle("Confirmatory batches vs model prediction (dashed = specification)")
plt.tight_layout()
plt.savefig(OUT / "cb_confirmation.png", dpi=150)
print("\nSaved cb_results.csv and cb_confirmation.png")
