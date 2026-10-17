"""
Step 4: Response-surface models and ANOVA for the 4 simulated responses.

Reads : outputs/doe_results.csv           (from Step 3)
Writes: outputs/model_summary.csv         fit statistics per response (reduced model)
        outputs/model_coefficients.csv    coefficients, CI and p-values (reduced model)
        outputs/validation_vs_truth.csv   full-model estimates vs the effects built into the simulator
        outputs/models.json               reduced models (used in Step 5)
        outputs/actual_vs_predicted.png

Method
  1. Fit a full quadratic model in CODED units (-1..+1):
        y = b0 + bA*A + bB*B + bC*C + bAB*AB + bAC*AC + bBC*BC + bAA*A^2 + bBB*B^2 + bCC*C^2
     A = binder, B = disintegrant, C = compression force.
  2. Reduce by backward elimination (drop the term with the largest p-value while p > 0.10),
     keeping hierarchy (a main effect stays if any interaction/square containing it stays).
  3. Report R2, adjusted R2, predicted R2 (PRESS), adequate precision, lack-of-fit test
     (using the 3 centre-point replicates as pure error).
  4. Friability and disintegration time are modelled on the natural-log scale (they behave
     multiplicatively and are right-skewed). Predictions are back-transformed for plots.
  5. VALIDATION: compare the full-model estimates with the true effects used in Step 3.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

OUT = Path("outputs")
P_REMOVE = 0.10

d = pd.read_csv(OUT / "doe_results.csv").sort_values("RunOrder").reset_index(drop=True)

# ------------------------------------------------------------------ design matrix (coded)
X = pd.DataFrame({
    "A": d["Binder_pct_coded"], "B": d["Disintegrant_pct_coded"], "C": d["Compression_kN_coded"],
})
X["AB"], X["AC"], X["BC"] = X.A * X.B, X.A * X.C, X.B * X.C
X["A2"], X["B2"], X["C2"] = X.A**2, X.B**2, X.C**2
ALL_TERMS = ["A", "B", "C", "AB", "AC", "BC", "A2", "B2", "C2"]
center = (d["PointType"] == "Center").values

# ------------------------------------------------------------------ responses and transforms
RESP = {  # name: (column, transform)
    "Hardness_kp":     ("Hardness_kp", "none"),
    "Friability_pct":  ("Friability_pct", "ln"),
    "DT_min":          ("DT_min", "ln"),
    "Dissolution_Q30": ("Dissolution_Q30", "none"),
}

# True effects used in Step 3 (coded units, on the modelled scale). Used ONLY for validation.
TRUE = {
    "Hardness_kp":     {"const": 7.0, "A": 1.6, "B": -0.3, "C": 2.2, "AC": 0.4, "C2": -0.5},
    "Friability_pct":  {"const": np.log(0.55), "A": -0.48, "B": 0.09, "C": -0.66, "AC": -0.12, "C2": 0.15},
    "DT_min":          {"const": np.log(6.0), "A": 0.25, "B": -0.45, "C": 0.30, "B2": 0.10},
    "Dissolution_Q30": {"const": 88.0, "A": -5.0, "B": 6.3, "C": -4.2, "B2": -1.4},
}


def fit(y, terms):
    return sm.OLS(y, sm.add_constant(X[terms], has_constant="add")).fit()


def backward_eliminate(y, p_remove=P_REMOVE):
    terms = ALL_TERMS.copy()
    while True:
        m = fit(y, terms)
        pv = m.pvalues.drop("const")
        droppable = {}
        for t in terms:
            # a main effect is protected if a higher-order term containing it is kept
            protected = len(t) == 1 and any(t in u for u in terms if u != t)
            if not protected and pv[t] > p_remove:
                droppable[t] = pv[t]
        if not droppable:
            return m, terms
        terms.remove(max(droppable, key=droppable.get))


def fit_stats(m, y, terms):
    n, p = int(m.nobs), len(terms) + 1
    h = m.get_influence().hat_matrix_diag
    press = np.sum((m.resid / (1 - h)) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    pred = m.fittedvalues
    adeq = (pred.max() - pred.min()) / np.sqrt(p * m.mse_resid / n)
    # lack of fit: pure error from the centre-point replicates
    yc = y[center]
    ss_pe, df_pe = np.sum((yc - yc.mean()) ** 2), len(yc) - 1
    ss_lof = np.sum(m.resid**2) - ss_pe
    df_lof = m.df_resid - df_pe
    if df_lof > 0 and ss_pe > 0:
        f_lof = (ss_lof / df_lof) / (ss_pe / df_pe)
        p_lof = 1 - stats.f.cdf(f_lof, df_lof, df_pe)
    else:
        p_lof = np.nan
    return dict(R2=m.rsquared, Adj_R2=m.rsquared_adj, Pred_R2=1 - press / ss_tot,
                Adeq_Precision=adeq, Model_p=m.f_pvalue, LOF_p=p_lof, RMSE=np.sqrt(m.mse_resid),
                Resid_df=int(m.df_resid))


summary_rows, coef_rows, val_rows, models = [], [], [], {}
pred_back = {}

for name, (col, tr) in RESP.items():
    y = d[col].astype(float).values
    y_m = np.log(y) if tr == "ln" else y

    full = fit(y_m, ALL_TERMS)
    red, kept = backward_eliminate(y_m)
    st = fit_stats(red, y_m, kept)
    st.update(Response=name, Transform=tr, Terms="+".join(kept))
    summary_rows.append(st)

    ci = red.conf_int()
    for t in ["const"] + kept:
        coef_rows.append(dict(Response=name, Term=t, Coef=red.params[t], CI_low=ci.loc[t, 0],
                              CI_high=ci.loc[t, 1], p_value=red.pvalues[t]))

    # validation (full model vs truth)
    cif = full.conf_int()
    for t in ["const"] + ALL_TERMS:
        true = TRUE[name].get(t, 0.0)
        val_rows.append(dict(Response=name, Term=t, Estimate=full.params[t], True_value=true,
                             CI_low=cif.loc[t, 0], CI_high=cif.loc[t, 1], p_value=full.pvalues[t],
                             True_in_CI=bool(cif.loc[t, 0] <= true <= cif.loc[t, 1])))

    models[name] = dict(transform=tr, terms=kept, coef={t: float(red.params[t]) for t in ["const"] + kept},
                        rmse=float(np.sqrt(red.mse_resid)), resid_df=int(red.df_resid))
    fitted = red.fittedvalues.values
    pred_back[name] = (y, np.exp(fitted) if tr == "ln" else fitted)

    # --------------------------------------------------------------- print
    print(f"\n{'=' * 78}\n{name}  (modelled on {'ln scale' if tr == 'ln' else 'original scale'})")
    print(f"Reduced model terms: {', '.join(kept)}")
    print(f"R2 {st['R2']:.3f} | Adj R2 {st['Adj_R2']:.3f} | Pred R2 {st['Pred_R2']:.3f} | "
          f"Adeq precision {st['Adeq_Precision']:.1f} | model p {st['Model_p']:.4f} | "
          f"LOF p {st['LOF_p']:.3f} | residual df {st['Resid_df']}")
    tab = pd.DataFrame({"coef": red.params, "p": red.pvalues}).round(4)
    print(tab.to_string())

# ------------------------------------------------------------------ save
pd.DataFrame(summary_rows)[["Response", "Transform", "Terms", "R2", "Adj_R2", "Pred_R2", "Adeq_Precision",
                            "Model_p", "LOF_p", "RMSE", "Resid_df"]].round(4).to_csv(OUT / "model_summary.csv", index=False)
pd.DataFrame(coef_rows).round(5).to_csv(OUT / "model_coefficients.csv", index=False)
val = pd.DataFrame(val_rows).round(5)
val.to_csv(OUT / "validation_vs_truth.csv", index=False)
(OUT / "models.json").write_text(json.dumps(models, indent=2))

# ------------------------------------------------------------------ validation summary
print(f"\n{'=' * 78}\nVALIDATION: does the 15-run analysis recover the effects built into the simulator?")
nz = val[(val["True_value"] != 0) & (val["Term"] != "const")]
print(f"True non-zero effects whose 95% CI contains the truth: {int(nz['True_in_CI'].sum())} of {len(nz)}")
print(f"All terms (incl. true zeros) with truth inside 95% CI: {int(val['True_in_CI'].sum())} of {len(val)}")
sig_false = val[(val["True_value"] == 0) & (val["Term"] != "const") & (val["p_value"] < 0.05)]
print(f"False positives (true effect = 0 but p < 0.05): {len(sig_false)}")
if len(sig_false):
    print(sig_false[["Response", "Term", "Estimate", "p_value"]].to_string(index=False))

# ------------------------------------------------------------------ plot
fig, axes = plt.subplots(2, 2, figsize=(9, 8))
for ax, (name, (act, prd)) in zip(axes.ravel(), pred_back.items()):
    ax.scatter(prd[~center], act[~center], color="#0B7285", label="Edge runs")
    ax.scatter(prd[center], act[center], color="#F28C28", marker="s", label="Centre runs")
    lo, hi = min(act.min(), prd.min()), max(act.max(), prd.max())
    ax.plot([lo, hi], [lo, hi], "k--", lw=1)
    ax.set_title(name); ax.set_xlabel("Predicted"); ax.set_ylabel("Actual (simulated)")
axes[0, 0].legend()
plt.tight_layout()
plt.savefig(OUT / "actual_vs_predicted.png", dpi=150)
print("\nSaved model_summary.csv, model_coefficients.csv, validation_vs_truth.csv, models.json, actual_vs_predicted.png")
