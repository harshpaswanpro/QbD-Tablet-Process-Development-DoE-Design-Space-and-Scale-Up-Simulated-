"""
Step 2: Box-Behnken design for the simulated IR tablet process.

Factors (chosen from the Step 1 FMEA, highest-RPN controllable parameters):
    A  Binder concentration   (% w/w)   2.0 - 6.0
    B  Disintegrant level     (% w/w)   2.0 - 6.0
    C  Compression force      (kN)      8.0 - 16.0
Fixed (controlled) conditions:
    granulation endpoint by wet-mass consistency, lubricant 1.0% w/w for 3 min,
    API d90 fixed, tablet weight 250 mg (100 mg API), 1 kg lab batch.

Design: 12 edge-midpoint runs + 3 centre points = 15 runs. Run order is randomized
(good DoE practice: protects against time-related drift).

Outputs (./outputs): doe_design.csv, doe_design_plot.png
No extra libraries needed beyond numpy, pandas, matplotlib.
"""
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path("outputs")
OUT.mkdir(exist_ok=True)

FACTORS = {
    "Binder_pct":      (2.0, 6.0),    # low, high
    "Disintegrant_pct": (2.0, 6.0),
    "Compression_kN":  (8.0, 16.0),
}
names = list(FACTORS)
N_CENTER = 3
SEED = 42

# ------------------------------------------------------------------ coded design (-1, 0, +1)
coded_rows = []
for i, j in combinations(range(len(names)), 2):       # each pair of factors at +/-1,
    for a in (-1, 1):                                  # the remaining factor at 0
        for b in (-1, 1):
            row = [0, 0, 0]
            row[i], row[j] = a, b
            coded_rows.append(row)
coded_rows += [[0, 0, 0]] * N_CENTER

coded = pd.DataFrame(coded_rows, columns=[f"{n}_coded" for n in names])
coded.insert(0, "StdOrder", range(1, len(coded) + 1))

# ------------------------------------------------------------------ convert to real units
design = coded.copy()
for n, (lo, hi) in FACTORS.items():
    mid, half = (hi + lo) / 2, (hi - lo) / 2
    design[n] = mid + coded[f"{n}_coded"] * half

# ------------------------------------------------------------------ randomize run order
rng = np.random.default_rng(SEED)
design["RunOrder"] = rng.permutation(len(design)) + 1
design = design.sort_values("RunOrder").reset_index(drop=True)
design["PointType"] = np.where((design[[f"{n}_coded" for n in names]] == 0).all(axis=1), "Center", "Edge")

# ------------------------------------------------------------------ checks
assert len(design) == 15
assert (design["PointType"] == "Center").sum() == N_CENTER
for n in names:  # balanced: each factor has 4 runs at -1, 4 at +1, 7 at 0
    counts = design[f"{n}_coded"].value_counts().to_dict()
    assert counts == {-1: 4, 1: 4, 0: 7}, (n, counts)

cols = ["RunOrder", "StdOrder", "PointType"] + names
print("\nBox-Behnken design (randomized run order):\n")
print(design[cols].to_string(index=False))
design.to_csv(OUT / "doe_design.csv", index=False)

# ------------------------------------------------------------------ plot: design space projections
fig, axes = plt.subplots(1, 3, figsize=(13, 4))
for ax, (x, y) in zip(axes, combinations(names, 2)):
    for t, c, m in (("Edge", "#0B7285", "o"), ("Center", "#F28C28", "s")):
        d = design[design["PointType"] == t]
        ax.scatter(d[x], d[y], c=c, marker=m, s=60, label=t, alpha=0.85)
    ax.set_xlabel(x); ax.set_ylabel(y)
axes[0].legend()
fig.suptitle("Box-Behnken design: 15 runs (3 factors, 3 centre points)")
plt.tight_layout()
plt.savefig(OUT / "doe_design_plot.png", dpi=150)
print("\nSaved outputs/doe_design.csv and outputs/doe_design_plot.png")
