"""
Step 3: Simulate the experimental responses for the 15 DoE runs.

IMPORTANT: these are SIMULATED data, not lab measurements. The relationships below
encode directional formulation knowledge, and the coefficients are ASSUMED values chosen
for teaching/demonstration. Say "simulated" in the README and on the resume.

Reads : outputs/doe_design.csv   (from Step 2)
Writes: outputs/doe_results.csv, outputs/response_main_effects.png

Coded factors: x1 = binder, x2 = disintegrant, x3 = compression force   (each -1 .. +1)

Assumed cause-and-effect (directional knowledge):
  Hardness      rises strongly with compression force, rises with binder; more disintegrant
                makes tablets slightly softer; diminishing returns at high force (x3^2 < 0).
  Friability    falls as hardness rises (harder tablets lose less mass).
  Disintegration time (DT)  rises with binder and with compression force (denser, stronger
                tablets); falls with disintegrant, with diminishing returns at high levels.
  Dissolution Q30 (BCS II, dissolution-limited)  falls as DT lengthens; binder adds a small
                extra penalty (stronger granules). Capped at 100%.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path("outputs")
SEED = 2026
rng = np.random.default_rng(SEED)

# ------------------------------------------------------------------ assumed model (edit & justify!)
COEF = {
    "hardness": dict(b0=7.0, x1=1.6, x2=-0.3, x3=2.2, x1x3=0.4, x3sq=-0.5, sd=0.30),       # kp
    "friab":    dict(h_ref=7.0, f_ref=0.55, k=0.30, sd_log=0.10),                          # %
    "dt":       dict(b0=np.log(6.0), x1=0.25, x2=-0.45, x3=0.30, x2sq=0.10, sd_log=0.05),   # min (log scale)
    "q30":      dict(b0=88.0, k_dt=-14.0, x1=-1.5, sd=1.5),                                 # %
}

# ------------------------------------------------------------------ acceptance criteria (from Step 1)
SPEC = {
    "Hardness_kp":     (5.0, 10.0),
    "Friability_pct":  (None, 1.0),
    "DT_min":          (None, 15.0),
    "Dissolution_Q30": (80.0, None),
}

d = pd.read_csv(OUT / "doe_design.csv").sort_values("RunOrder").reset_index(drop=True)
x1, x2, x3 = d["Binder_pct_coded"], d["Disintegrant_pct_coded"], d["Compression_kN_coded"]
n = len(d)

# ------------------------------------------------------------------ simulate
h = COEF["hardness"]
d["Hardness_kp"] = (h["b0"] + h["x1"] * x1 + h["x2"] * x2 + h["x3"] * x3
                    + h["x1x3"] * x1 * x3 + h["x3sq"] * x3**2 + rng.normal(0, h["sd"], n))

f = COEF["friab"]
d["Friability_pct"] = (f["f_ref"] * np.exp(-f["k"] * (d["Hardness_kp"] - f["h_ref"]))
                       * np.exp(rng.normal(0, f["sd_log"], n)))

t = COEF["dt"]
d["DT_min"] = np.exp(t["b0"] + t["x1"] * x1 + t["x2"] * x2 + t["x3"] * x3
                     + t["x2sq"] * x2**2 + rng.normal(0, t["sd_log"], n))

q = COEF["q30"]
d["Dissolution_Q30"] = (q["b0"] + q["k_dt"] * np.log(d["DT_min"] / 6.0) + q["x1"] * x1
                        + rng.normal(0, q["sd"], n)).clip(upper=100.0)

resp = list(SPEC)
d[resp] = d[resp].round(2)

# ------------------------------------------------------------------ pass / fail vs acceptance criteria
def ok(series, lo, hi):
    m = pd.Series(True, index=series.index)
    if lo is not None: m &= series >= lo
    if hi is not None: m &= series <= hi
    return m

d["All_CQAs_Pass"] = np.logical_and.reduce([ok(d[c], *SPEC[c]) for c in resp])
d["Data_Type"] = "Simulated"

cols = ["RunOrder", "Binder_pct", "Disintegrant_pct", "Compression_kN"] + resp + ["All_CQAs_Pass"]
print("\nSimulated DoE results:\n")
print(d[cols].to_string(index=False))
print(f"\nRuns meeting ALL CQAs: {int(d['All_CQAs_Pass'].sum())} of {n}")
print("\nResponse ranges:")
print(d[resp].agg(["min", "max"]).T.to_string())

d.to_csv(OUT / "doe_results.csv", index=False)

# ------------------------------------------------------------------ main-effects style plot
fig, axes = plt.subplots(4, 3, figsize=(11, 11), sharey="row")
for r, y in enumerate(resp):
    for c, xname in enumerate(["Binder_pct", "Disintegrant_pct", "Compression_kN"]):
        ax = axes[r, c]
        ax.scatter(d[xname], d[y], color="#0B7285", alpha=0.8)
        lo, hi = SPEC[y]
        for lim in (lo, hi):
            if lim is not None:
                ax.axhline(lim, ls="--", color="#F28C28", lw=1)
        if c == 0: ax.set_ylabel(y)
        if r == 3: ax.set_xlabel(xname)
fig.suptitle("Simulated responses vs factors (orange = acceptance limits)")
plt.tight_layout()
plt.savefig(OUT / "response_main_effects.png", dpi=150)
print("\nSaved outputs/doe_results.csv and outputs/response_main_effects.png")
