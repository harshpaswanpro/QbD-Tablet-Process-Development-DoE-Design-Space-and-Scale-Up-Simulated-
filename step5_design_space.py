"""
Step 5: Optimization (desirability) and Monte Carlo design space.

Reads : outputs/doe_results.csv, outputs/models.json   (Steps 3-4)
Writes: outputs/design_space_grid.csv, outputs/step5_results.json, outputs/design_space.png

Ideas
  * Desirability: turn each response into a 0-1 score (Derringer-Suich) and combine them with a
    geometric mean D. The best grid point by D is the "desirability optimum".
  * Design space (ICH Q8 idea): the region where the probability of meeting ALL CQAs is high.
    Probability is estimated by Monte Carlo, combining three sources of variation:
        1. model parameter uncertainty (draws from the fitted coefficient covariance),
        2. residual (run-to-run) noise from the model RMSE,
        3. process variability: factors do not hit set-points exactly (ASSUMED SDs below).
  * Robust operating point: the grid point with the highest probability of success
    (ties broken by desirability). Normal operating range (NOR) = largest box around it that
    lies completely inside the design space.
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
SEED = 7
rng = np.random.default_rng(SEED)

# ------------------------------------------------------------------ settings (ASSUMPTIONS: edit & justify)
P_TARGET = 0.90            # design space = region with P(all CQAs pass) >= 90%
GRID_N = 21                # grid points per factor (coded step = 0.1)
K_GRID = 1000              # Monte Carlo draws per grid point
K_VERIFY = 10_000          # Monte Carlo draws for the final verification points
MAX_DISINTEGRANT_PCT = 5.0 # practical formulation limit (ASSUMED; check an excipient handbook). Set 6.0 to remove.
CENTRE = {"A": 4.0, "B": 4.0, "C": 12.0}
HALF = {"A": 2.0, "B": 2.0, "C": 4.0}
PROC_SD_REAL = {"A": 0.15, "B": 0.15, "C": 0.40}      # 1 SD of set-point variation (% w/w, % w/w, kN)
PROC_SD = {k: PROC_SD_REAL[k] / HALF[k] for k in CENTRE}   # in coded units
SPEC = {  # acceptance criteria from Step 1
    "Hardness_kp": (5.0, 10.0), "Friability_pct": (None, 1.0),
    "DT_min": (None, 15.0), "Dissolution_Q30": (80.0, None),
}

# ------------------------------------------------------------------ models (refit to get coefficient covariance)
d = pd.read_csv(OUT / "doe_results.csv")
saved = json.loads((OUT / "models.json").read_text())
Xc = pd.DataFrame({"A": d["Binder_pct_coded"], "B": d["Disintegrant_pct_coded"], "C": d["Compression_kN_coded"]})
for t in ["AB", "AC", "BC"]:
    Xc[t] = Xc[t[0]] * Xc[t[1]]
for t in ["A2", "B2", "C2"]:
    Xc[t] = Xc[t[0]] ** 2

MODELS = {}
for name, spec in saved.items():
    terms = spec["terms"]
    y = d[name].astype(float)
    y = np.log(y) if spec["transform"] == "ln" else y
    fit = sm.OLS(y, sm.add_constant(Xc[terms])).fit()
    beta_hat = fit.params.values
    saved_beta = np.array([spec["coef"][t] for t in ["const"] + terms])
    assert np.allclose(beta_hat, saved_beta, atol=1e-6), f"{name}: refit differs from models.json"
    MODELS[name] = dict(terms=terms, transform=spec["transform"], beta=beta_hat,
                        cov=fit.cov_params().values, rmse=spec["rmse"])


def term_value(t, A, B, C):
    return {"A": A, "B": B, "C": C, "AB": A * B, "AC": A * C, "BC": B * C,
            "A2": A**2, "B2": B**2, "C2": C**2}[t]


def mean_response(name, A, B, C):
    """Deterministic prediction (original scale) at coded factor values."""
    m = MODELS[name]
    y = m["beta"][0] + sum(m["beta"][j] * term_value(t, A, B, C) for j, t in enumerate(m["terms"], 1))
    return np.exp(y) if m["transform"] == "ln" else y


def draw_betas(K):
    return {n: rng.multivariate_normal(m["beta"], m["cov"], K) for n, m in MODELS.items()}


def simulate(a, b, c, betas, return_resp=False):
    """Monte Carlo at set-points a,b,c (coded arrays, length g). Returns pass matrix (g, K)."""
    g, K = len(a), next(iter(betas.values())).shape[0]
    A = a[:, None] + rng.normal(0, PROC_SD["A"], (g, K))
    B = b[:, None] + rng.normal(0, PROC_SD["B"], (g, K))
    C = c[:, None] + rng.normal(0, PROC_SD["C"], (g, K))
    ok, resp = np.ones((g, K), bool), {}
    for name, m in MODELS.items():
        be = betas[name]
        y = np.broadcast_to(be[:, 0], (g, K)).copy()
        for j, t in enumerate(m["terms"], 1):
            y += be[:, j][None, :] * term_value(t, A, B, C)
        y += rng.normal(0, m["rmse"], (g, K))
        y = np.exp(y) if m["transform"] == "ln" else y
        lo, hi = SPEC[name]
        if lo is not None: ok &= y >= lo
        if hi is not None: ok &= y <= hi
        resp[name] = y
    return (ok, resp) if return_resp else ok


# ------------------------------------------------------------------ desirability
def d_hardness(y):   # two-sided, target 7.5 kp
    return np.clip(np.minimum((y - 5.0) / 2.5, (10.0 - y) / 2.5), 0, 1)

def d_friab(y):      # smaller is better: 1 at <=0.3%, 0 at >=1.0%
    return np.clip((1.0 - y) / 0.7, 0, 1)

def d_dt(y):         # smaller is better: 1 at <=5 min, 0 at >=15 min
    return np.clip((15.0 - y) / 10.0, 0, 1)

def d_q30(y):        # larger is better: 0 at <=80%, 1 at >=95%
    return np.clip((y - 80.0) / 15.0, 0, 1)


def overall_D(A, B, C):
    ds = [d_hardness(mean_response("Hardness_kp", A, B, C)),
          d_friab(mean_response("Friability_pct", A, B, C)),
          d_dt(mean_response("DT_min", A, B, C)),
          d_q30(np.minimum(mean_response("Dissolution_Q30", A, B, C), 100.0))]
    return np.prod(ds, axis=0) ** (1 / len(ds))


# ------------------------------------------------------------------ grid evaluation
levels = np.linspace(-1, 1, GRID_N)
GA, GB, GC = np.meshgrid(levels, levels, levels, indexing="ij")
a, b, c = GA.ravel(), GB.ravel(), GC.ravel()
D = overall_D(a, b, c)

betas_grid = draw_betas(K_GRID)
P = np.empty(len(a))
CH = 500
for i in range(0, len(a), CH):
    P[i:i + CH] = simulate(a[i:i + CH], b[i:i + CH], c[i:i + CH], betas_grid).mean(axis=1)

real = lambda code, k: CENTRE[k] + HALF[k] * code
grid = pd.DataFrame({"Binder_pct": real(a, "A"), "Disintegrant_pct": real(b, "B"),
                     "Compression_kN": real(c, "C"), "Desirability": D, "P_all_CQAs": P})
grid.to_csv(OUT / "design_space_grid.csv", index=False)

# ------------------------------------------------------------------ candidate operating points
allowed = real(b, "B") <= MAX_DISINTEGRANT_PCT + 1e-9          # practical limit on the operating point
i_D = int(np.argmax(D))                                          # unconstrained desirability optimum
P_allowed = np.where(allowed, P, -1)
cand = np.where(P_allowed >= P_allowed.max() - 0.005)[0]
i_R = int(cand[np.argmax(D[cand])])                              # robust point within the practical limit


def describe(i, label):
    betas = draw_betas(K_VERIFY)
    ok, resp = simulate(a[i:i + 1], b[i:i + 1], c[i:i + 1], betas, return_resp=True)
    out = dict(label=label,
               Binder_pct=float(real(a[i], "A")), Disintegrant_pct=float(real(b[i], "B")),
               Compression_kN=float(real(c[i], "C")), Desirability=float(D[i]),
               P_all_CQAs_10k=float(ok.mean()),
               responses={n: dict(mean=float(np.mean(v)), p5=float(np.percentile(v, 5)),
                                  p95=float(np.percentile(v, 95))) for n, v in resp.items()})
    print(f"\n{label}: binder {out['Binder_pct']:.1f}% | disintegrant {out['Disintegrant_pct']:.1f}% | "
          f"force {out['Compression_kN']:.1f} kN")
    print(f"  Desirability D = {out['Desirability']:.3f} | P(all CQAs) from {K_VERIFY:,} MC runs = {out['P_all_CQAs_10k']:.1%}")
    for n, r in out["responses"].items():
        print(f"  {n:16s} mean {r['mean']:7.2f}   5th-95th pct: {r['p5']:7.2f} to {r['p95']:7.2f}")
    return out


res_D = describe(i_D, "Desirability optimum (unconstrained)")
res_R = describe(i_R, f"Robust operating point (disintegrant <= {MAX_DISINTEGRANT_PCT:.1f}%)")

# ------------------------------------------------------------------ design space & NOR
inside = (P >= P_TARGET).reshape(GA.shape)
share = inside.mean()
print(f"\nDesign space: {share:.1%} of the explored cube has P(all CQAs) >= {P_TARGET:.0%}")

ia, ib, ic = [int(np.where(np.isclose(levels, v))[0][0]) for v in (a[i_R], b[i_R], c[i_R])]
best_s = 0.0
for s in np.arange(0.1, 1.0001, 0.1):
    ma, mb, mc = (np.abs(GA - a[i_R]) <= s + 1e-9), (np.abs(GB - b[i_R]) <= s + 1e-9), (np.abs(GC - c[i_R]) <= s + 1e-9)
    box = ma & mb & mc
    box_allowed = box & allowed.reshape(GA.shape)       # points beyond the practical limit are not part of the NOR
    if inside[box_allowed].all():
        best_s = s
    else:
        break
nor = {}
for k, code in zip("ABC", (a[i_R], b[i_R], c[i_R])):
    lo, hi = max(-1, code - best_s), min(1, code + best_s)
    if k == "B":
        hi = min(hi, (MAX_DISINTEGRANT_PCT - CENTRE["B"]) / HALF["B"])
    nor[k] = (float(real(lo, k)), float(real(hi, k)))
names = {"A": "Binder (% w/w)", "B": "Disintegrant (% w/w)", "C": "Compression force (kN)"}
print(f"\nProposed normal operating range (box of +/-{best_s:.1f} coded units around the robust point, "
      f"fully inside the design space):")
for k in "ABC":
    print(f"  {names[k]:24s} {nor[k][0]:.1f} to {nor[k][1]:.1f}")

json.dump(dict(settings=dict(P_TARGET=P_TARGET, K_GRID=K_GRID, K_VERIFY=K_VERIFY, PROC_SD_REAL=PROC_SD_REAL, SEED=SEED),
               desirability_optimum=res_D, robust_point=res_R, design_space_share=float(share),
               NOR={names[k]: nor[k] for k in "ABC"}),
          open(OUT / "step5_results.json", "w"), indent=2)

# ------------------------------------------------------------------ plots: P(all CQAs) slices through the robust point
Pg = P.reshape(GA.shape)
panels = [("Binder_pct", "Compression_kN", Pg[:, ib, :], levels, levels, "A", "C", f"Disintegrant = {res_R['Disintegrant_pct']:.1f}%"),
          ("Binder_pct", "Disintegrant_pct", Pg[:, :, ic], levels, levels, "A", "B", f"Force = {res_R['Compression_kN']:.1f} kN"),
          ("Disintegrant_pct", "Compression_kN", Pg[ia, :, :], levels, levels, "B", "C", f"Binder = {res_R['Binder_pct']:.1f}%")]
fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
for ax, (xl, yl, Z, lx, ly, kx, ky, ttl) in zip(axes, panels):
    X, Y = np.meshgrid(real(lx, kx), real(ly, ky), indexing="ij")
    cs = ax.contourf(X, Y, Z, levels=np.linspace(0, 1, 11), cmap="viridis")
    ax.contour(X, Y, Z, levels=[P_TARGET], colors="white", linewidths=2)
    ax.scatter(res_R[xl], res_R[yl], marker="*", s=220, color="#F28C28", edgecolor="k", zorder=5, label="Robust point")
    ax.set_xlabel(xl); ax.set_ylabel(yl); ax.set_title(ttl)
axes[0].legend(loc="lower left")
fig.colorbar(cs, ax=axes, label="P(all CQAs pass)", shrink=0.9)
fig.suptitle(f"Monte Carlo design space (white line = P = {P_TARGET:.0%})")
plt.savefig(OUT / "design_space.png", dpi=150, bbox_inches="tight")
print("\nSaved design_space_grid.csv, step5_results.json, design_space.png")
