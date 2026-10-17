"""
Step 1: QTPP, CQAs and initial risk assessment (FMEA) for a simulated
immediate-release (IR) tablet made by wet granulation.

Outputs (written to ./outputs):
    qtpp_cqa.csv   - target product profile and CQA acceptance criteria
    fmea.csv       - risk table with RPN = Severity x Occurrence x Detectability
    fmea_pareto.png

NOTE: The product is a hypothetical model drug (BCS Class II). All scores below
are DRAFT. Review each one and be ready to justify it (ICH Q9 risk assessment).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

OUT = Path("outputs")
OUT.mkdir(exist_ok=True)

# ------------------------------------------------------------------ 1. QTPP / CQAs
qtpp = pd.DataFrame(
    [
        # attribute, target, is_CQA, why it matters, acceptance criterion
        ("Dosage form", "Immediate-release film-coated tablet", "No", "Defines product design", "n/a"),
        ("Strength", "100 mg (model BCS Class II API)", "No", "Dose accuracy", "n/a"),
        ("Assay", "95.0-105.0% of label claim", "Yes", "Efficacy and safety", "95.0-105.0%"),
        ("Content uniformity", "Uniform dose per tablet", "Yes", "Dose consistency", "Acceptance Value <= 15 (USP <905>)"),
        ("Dissolution", "Rapid release", "Yes", "Bioavailability (BCS II is dissolution-limited)", "Q30 >= 80% (assumed)"),
        ("Hardness", "Robust for handling and coating", "Yes", "Handling, packaging, dissolution", "5-10 kp (assumed)"),
        ("Friability", "Low mass loss", "Yes", "Handling, coating", "<= 1.0% (USP <1216>)"),
        ("Disintegration time", "Fast breakup", "Yes", "Drives dissolution", "<= 15 min (assumed)"),
        ("Weight variation", "Consistent tablet weight", "Yes", "Dose consistency", "Per pharmacopoeial limits"),
    ],
    columns=["Attribute", "Target", "CQA", "Justification", "Acceptance criterion"],
)
qtpp.to_csv(OUT / "qtpp_cqa.csv", index=False)

# ------------------------------------------------------------------ 2. FMEA (DRAFT scores, 1-10)
rows = [
    # parameter, unit operation, failure mode, CQAs affected, S, O, D
    ("Binder concentration (% w/w)", "Wet granulation", "Weak or over-hard granules", "Hardness, friability, dissolution", 7, 7, 5),
    ("Compression force (kN)", "Compression", "Low: friable tablets. High: slow disintegration", "Hardness, friability, dissolution", 8, 7, 4),
    ("Granulation endpoint (water / wet mass)", "Wet granulation", "Over- or under-granulation", "Dissolution, content uniformity", 7, 5, 6),
    ("Disintegrant level (% w/w)", "Blending", "Slow disintegration", "Disintegration, dissolution", 8, 6, 4),
    ("Lubricant blending time", "Lubrication", "Over-lubrication slows release, lowers hardness", "Dissolution, hardness", 6, 5, 5),
    ("Blend uniformity / blending time", "Blending", "Segregation or poor mixing", "Content uniformity, assay", 9, 3, 5),
    ("Mill screen size / speed", "Milling", "Particle size distribution shifts", "Flow, content uniformity", 6, 4, 5),
    ("API particle size (CMA)", "Raw material", "Coarse API reduces dissolution", "Dissolution, content uniformity", 9, 4, 3),
    ("Press speed (dwell time)", "Compression", "Weight variation, capping", "Weight variation, hardness", 6, 5, 3),
    ("Drying end-point (LOD)", "Drying", "Moisture out of range", "Assay, hardness, stability", 6, 4, 3),
]
fmea = pd.DataFrame(rows, columns=["Parameter", "Unit operation", "Failure mode", "CQAs affected", "S", "O", "D"])
fmea["RPN"] = fmea["S"] * fmea["O"] * fmea["D"]
fmea = fmea.sort_values("RPN", ascending=False).reset_index(drop=True)
fmea["Cum_%"] = (fmea["RPN"].cumsum() / fmea["RPN"].sum() * 100).round(1)
fmea.to_csv(OUT / "fmea.csv", index=False)

print("\nTop risks (RPN):")
print(fmea[["Parameter", "S", "O", "D", "RPN", "Cum_%"]].to_string(index=False))

# ------------------------------------------------------------------ 3. Pareto chart
fig, ax1 = plt.subplots(figsize=(10, 5))
x = range(len(fmea))
ax1.bar(x, fmea["RPN"], color="#0B7285")
ax1.set_xticks(list(x))
ax1.set_xticklabels(fmea["Parameter"], rotation=45, ha="right", fontsize=8)
ax1.set_ylabel("RPN")
ax2 = ax1.twinx()
ax2.plot(list(x), fmea["Cum_%"], color="#F28C28", marker="o")
ax2.set_ylim(0, 105)
ax2.set_ylabel("Cumulative %")
plt.title("FMEA Pareto: risk ranking of process parameters")
plt.tight_layout()
plt.savefig(OUT / "fmea_pareto.png", dpi=150)
print("\nSaved outputs/qtpp_cqa.csv, outputs/fmea.csv, outputs/fmea_pareto.png")
