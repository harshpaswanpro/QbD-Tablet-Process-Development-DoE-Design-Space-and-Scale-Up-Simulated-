"""
Step 7: Scale-up plan: batch size, raw material requirement, equipment train, scale-up
parameters, capacity check and control strategy for the exhibit batches.

Reads : outputs/step5_results.json (operating point + NOR), outputs/cb_results.csv (Step 6 gate)
Writes: outputs/raw_material_requirement.csv, outputs/equipment_train.csv, outputs/scaleup_parameters.csv,
        outputs/control_strategy.csv, outputs/step7_summary.json, outputs/process_flow_scaleup.png

EVERY number in the ASSUMPTIONS block is an illustrative assumption (generic equipment sizes, bulk
densities, demand, ...). Replace them with the real site data and justify them in the report.
"""
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

OUT = Path("outputs")

# ================================================================== ASSUMPTIONS (edit & justify)
LABEL_CLAIM_MG = 100.0
CORE_WT_MG = 250.0
API_ASSAY_DRIED = 0.995        # fraction, on dried basis
API_LOD = 0.005                # fraction water in API as received
LUBRICANT_PCT = 1.0            # % w/w (fixed in the DoE)
GRAN_FLUID_PCT = 30.0          # granulating water, % w/w of intragranular dry mass (endpoint by power/consistency)
COAT_GAIN_PCT = 3.0            # film-coat weight gain, % of core weight
COAT_SOLIDS_FRAC = 0.15        # solids in coating dispersion
COAT_OVERAGE = 0.10            # preparation overage on coating material
BD_DRYMIX, BD_BLEND = 0.50, 0.55   # bulk densities, kg/L
DEMAND_TABLETS_PER_YEAR = 60e6     # assumed commercial demand
LAB_BATCH_KG = 1.0
EXHIBIT_MIN_FRACTION, EXHIBIT_MIN_UNITS = 0.10, 100_000   # commonly cited minimum (verify against the applicable guidance)

# equipment lists (generic sizes) and allowed fill ranges
RMG_L, RMG_FILL = [5, 25, 75, 150, 300, 600], (0.30, 0.50)      # bowl volume, L
FBD_KG, FBD_FILL = [2, 60, 300], (0.25, 0.90)                    # wet-load capacity, kg
BLEND_L, BLEND_FILL = [5, 100, 300, 600], (0.30, 0.60)           # bin volume, L
PAN_KG, PAN_FILL = [2, 30, 150], (0.40, 0.90)                    # core capacity, kg
SITE_LARGEST = {"RMG": 600, "FBD": 300, "Blender": 600, "Coating pan": 150}   # largest units available at the target site
PRESS = {  # stations, pitch-circle diameter (mm), operating speed (rpm)
    "Lab": (8, 150, 20), "Exhibit": (27, 250, 15), "Commercial": (45, 400, 12)}

# lab reference for scale-up rules
RMG_REF = dict(bowl_L=5, impeller_D_m=0.15, rpm=500)
BLEND_REF = dict(rpm=25, minutes=3.0)
BLEND_RPM = {"Lab": 25, "Exhibit": 15, "Commercial": 10}

# ================================================================== gate: Step 6 must be accepted
cb = pd.read_csv(OUT / "cb_results.csv")
if not cb["Meets_spec"].all():
    sys.exit("Step 6 gate FAILED: a confirmatory batch missed specification. Fix the operating point first.")
print("Gate passed: confirmatory batches (Step 6) met specification. Proceeding to scale-up.")

s5 = json.loads((OUT / "step5_results.json").read_text())
rp, nor = s5["robust_point"], s5["NOR"]
BINDER, DISINT, FORCE = rp["Binder_pct"], rp["Disintegrant_pct"], rp["Compression_kN"]

# ================================================================== composition per tablet
potency = API_ASSAY_DRIED * (1 - API_LOD)
mg = {"API (potency-adjusted)": LABEL_CLAIM_MG / potency,
      "Binder (e.g., povidone)": CORE_WT_MG * BINDER / 100,
      "Superdisintegrant (e.g., croscarmellose sodium)": CORE_WT_MG * DISINT / 100,
      "Lubricant (e.g., magnesium stearate)": CORE_WT_MG * LUBRICANT_PCT / 100}
mg["Diluent (e.g., microcrystalline cellulose), q.s."] = CORE_WT_MG - sum(mg.values())
assert mg["Diluent (e.g., microcrystalline cellulose), q.s."] > 0
assert abs(sum(mg.values()) - CORE_WT_MG) < 1e-9
INTRA_FRAC = 1 - LUBRICANT_PCT / 100
WET_FACTOR = INTRA_FRAC * (1 + GRAN_FLUID_PCT / 100)       # wet-granule mass per kg of core

# ================================================================== batch size from equipment capacity
def max_core_kg(unit, size):
    if unit == "RMG":         return size * RMG_FILL[1] * BD_DRYMIX / INTRA_FRAC
    if unit == "FBD":         return size * FBD_FILL[1] / WET_FACTOR
    if unit == "Blender":     return size * BLEND_FILL[1] * BD_BLEND
    if unit == "Coating pan": return size * PAN_FILL[1]

limits = {"RMG": max_core_kg("RMG", SITE_LARGEST["RMG"]), "FBD": max_core_kg("FBD", SITE_LARGEST["FBD"]),
          "Blender": max_core_kg("Blender", SITE_LARGEST["Blender"]), "Coating pan": max_core_kg("Coating pan", SITE_LARGEST["Coating pan"])}
limiting = min(limits, key=limits.get)
COMM_KG = math.floor(limits[limiting] / 5) * 5                      # round down to a 5 kg multiple
EXH_KG = max(EXHIBIT_MIN_FRACTION * COMM_KG, EXHIBIT_MIN_UNITS * CORE_WT_MG / 1e6)
BATCH = {"Lab": LAB_BATCH_KG, "Exhibit": EXH_KG, "Commercial": float(COMM_KG)}
TABS = {k: v * 1e6 / CORE_WT_MG for k, v in BATCH.items()}

print("\nBatch-size finalisation (largest core batch each commercial unit can take):")
for u, v in limits.items():
    print(f"  {u:12s} {SITE_LARGEST[u]:>4} {'L' if u in ('RMG','Blender') else 'kg'} -> {v:6.1f} kg" + ("   <-- limiting" if u == limiting else ""))
n_batches = math.ceil(DEMAND_TABLETS_PER_YEAR / TABS["Commercial"])
print(f"Commercial batch = {COMM_KG} kg ({TABS['Commercial']:,.0f} tablets); demand {DEMAND_TABLETS_PER_YEAR:,.0f}/yr -> {n_batches} batches/yr")
print(f"Exhibit batch    = {EXH_KG:.0f} kg ({TABS['Exhibit']:,.0f} tablets) "
      f"= max({EXHIBIT_MIN_FRACTION:.0%} of commercial, {EXHIBIT_MIN_UNITS:,} units)")
print(f"Lab batch        = {LAB_BATCH_KG:.0f} kg ({TABS['Lab']:,.0f} tablets)")

# ================================================================== raw material requirement
rm_rows = []
for name, m in mg.items():
    row = {"Material": name, "mg_per_tablet": round(m, 3), "pct_w/w": round(100 * m / CORE_WT_MG, 2)}
    for sc, kg in BATCH.items():
        row[f"{sc}_kg ({kg:.0f} kg batch)"] = round(m * TABS[sc] / 1e6, 3)
    rm_rows.append(row)
extra = {"Purified water (granulation; removed in drying)": lambda kg: kg * INTRA_FRAC * GRAN_FLUID_PCT / 100,
         f"Film-coat solids ({COAT_GAIN_PCT:.1f}% gain, incl. {COAT_OVERAGE:.0%} overage)": lambda kg: kg * COAT_GAIN_PCT / 100 * (1 + COAT_OVERAGE),
         "Purified water (coating dispersion)": lambda kg: kg * COAT_GAIN_PCT / 100 * (1 + COAT_OVERAGE) * (1 / COAT_SOLIDS_FRAC - 1)}
for name, f in extra.items():
    row = {"Material": name, "mg_per_tablet": None, "pct_w/w": None}
    for sc, kg in BATCH.items():
        row[f"{sc}_kg ({kg:.0f} kg batch)"] = round(f(kg), 3)
    rm_rows.append(row)
rm = pd.DataFrame(rm_rows)
rm.to_csv(OUT / "raw_material_requirement.csv", index=False)
print(f"\nRaw material requirement (core {CORE_WT_MG:.0f} mg; API potency factor {potency:.4f} -> {mg['API (potency-adjusted)']:.2f} mg API/tablet):")
print(rm.to_string(index=False))

# ================================================================== equipment train
def pick(sizes, load, lo, hi):
    for s in sizes:
        if lo - 1e-9 <= load / s <= hi + 1e-9:
            return s, load / s
    return None, None

eq_rows = []
for sc, kg in BATCH.items():
    intra = kg * INTRA_FRAC
    for unit, sizes, load, rng_, lab_unit in [
        ("RMG (high-shear granulator)", RMG_L, intra / BD_DRYMIX, RMG_FILL, "L bowl"),
        ("Fluid-bed dryer", FBD_KG, kg * WET_FACTOR, FBD_FILL, "kg wet load"),
        ("Bin blender", BLEND_L, kg / BD_BLEND, BLEND_FILL, "L bin"),
        ("Coating pan", PAN_KG, kg, PAN_FILL, "kg cores")]:
        s, f = pick(sizes, load, *rng_)
        eq_rows.append(dict(Scale=sc, Batch_kg=round(kg, 1), Unit_operation=unit,
                            Equipment_size=f"{s} {lab_unit}" if s else "NONE FITS", Fill_pct=round(100 * f, 0) if s else None,
                            Allowed_fill_pct=f"{rng_[0]:.0%}-{rng_[1]:.0%}"))
    st, pcd, rpm = PRESS[sc]
    tph = st * rpm * 60
    eq_rows.append(dict(Scale=sc, Batch_kg=round(kg, 1), Unit_operation="Rotary tablet press",
                        Equipment_size=f"{st} stations, PCD {pcd} mm, {rpm} rpm", Fill_pct=None,
                        Allowed_fill_pct=f"{tph:,.0f} tab/h -> {TABS[sc] / tph:.1f} h per batch"))
    eq_rows.append(dict(Scale=sc, Batch_kg=round(kg, 1), Unit_operation="Sifter / mill",
                        Equipment_size="vibro sifter, co-mill (screens set from exhibit data)", Fill_pct=None, Allowed_fill_pct="n/a"))
eq = pd.DataFrame(eq_rows)
assert not (eq["Equipment_size"] == "NONE FITS").any(), "no equipment size fits one of the scales; edit the size lists"
eq.to_csv(OUT / "equipment_train.csv", index=False)
print("\nEquipment train:")
print(eq.to_string(index=False))

# ================================================================== scale-up parameters
vol_ratio = {sc: float(eq[(eq.Scale == sc) & (eq.Unit_operation.str.startswith("RMG"))]["Equipment_size"].iloc[0].split()[0]) / RMG_REF["bowl_L"]
             for sc in BATCH}
sp_rows = []
for sc in BATCH:
    D = RMG_REF["impeller_D_m"] * vol_ratio[sc] ** (1 / 3)                       # geometric similarity
    N_tip = RMG_REF["rpm"] * RMG_REF["impeller_D_m"] / D                         # constant tip speed
    N_fr = RMG_REF["rpm"] * math.sqrt(RMG_REF["impeller_D_m"] / D)               # constant Froude number
    revs = BLEND_REF["rpm"] * BLEND_REF["minutes"]
    st, pcd, rpm = PRESS[sc]
    dwell_ratio = (PRESS["Lab"][1] * PRESS["Lab"][2]) / (pcd * rpm)
    sp_rows.append(dict(Scale=sc, RMG_impeller_D_m=round(D, 3), RMG_rpm_const_tip_speed=round(N_tip), RMG_rpm_const_Froude=round(N_fr),
                        Granulating_fluid_pct=GRAN_FLUID_PCT, Blender_rpm=BLEND_RPM[sc],
                        Lubrication_revolutions=revs, Lubrication_minutes=round(revs / BLEND_RPM[sc], 1),
                        Press_rpm=rpm, Press_dwell_vs_lab=round(dwell_ratio, 2), Compression_force_kN=FORCE,
                        Coat_weight_gain_pct=COAT_GAIN_PCT))
sp = pd.DataFrame(sp_rows)
sp.to_csv(OUT / "scaleup_parameters.csv", index=False)
print("\nScale-up parameters (starting points; confirm in the exhibit batches):")
print(sp.T.to_string(header=False))

# ================================================================== capacity check
press_h_batch = TABS["Commercial"] / (PRESS["Commercial"][0] * PRESS["Commercial"][2] * 60)
print(f"\nCapacity: {n_batches} batches/yr x {press_h_batch:.1f} h press time = {n_batches * press_h_batch:,.0f} press hours/yr")

# ================================================================== control strategy
cs = pd.DataFrame([
    ("Binder level", "CPP", f"Target {BINDER:.1f}% w/w; range {nor['Binder (% w/w)'][0]:.1f}-{nor['Binder (% w/w)'][1]:.1f}", "Hardness, friability, DT, dissolution", "DoE models + design space (Steps 4-5)"),
    ("Disintegrant level", "CPP", f"Target {DISINT:.1f}% w/w; range {nor['Disintegrant (% w/w)'][0]:.1f}-{nor['Disintegrant (% w/w)'][1]:.1f}", "DT, dissolution", "DoE models + design space; target sits at the practical upper limit"),
    ("Compression force", "CPP", f"Target {FORCE:.1f} kN; range {nor['Compression force (kN)'][0]:.1f}-{nor['Compression force (kN)'][1]:.1f}; automatic reject outside", "Hardness, friability, DT, dissolution", "DoE models + design space"),
    ("Granulation endpoint", "IPC", "Impeller power consumption / wet-mass consistency window", "Dissolution, content uniformity", "Fixed in the DoE, NOT studied: set the window from exhibit batches"),
    ("Drying endpoint", "IPC", "LOD limit at end of drying", "Assay, hardness, stability", "Not studied: set the limit from exhibit data"),
    ("Lubrication", "CPP (fixed)", f"{BLEND_REF['rpm'] * BLEND_REF['minutes']:.0f} revolutions (time = revolutions / rpm)", "Dissolution, hardness", "FMEA ranked this risk; held constant in the DoE"),
    ("API particle size", "CMA", "d90 limit on incoming API", "Dissolution, content uniformity", "Fixed in the DoE: set the limit from supplier data and studies"),
    ("Blend uniformity", "IPC", "Blend sampling plan and acceptance limits before compression", "Content uniformity, assay", "Highest-severity FMEA item"),
    ("Tablet weight, hardness, thickness, friability", "IPC", "Periodic checks during compression", "Weight variation, hardness, friability", "Specification limits from Step 1"),
    ("Finished-product CQAs", "Release", "Assay 95-105%; CU AV <= 15; Q30 >= 80%; DT <= 15 min; friability <= 1.0%", "All CQAs", "Step 1 acceptance criteria (assumed values)"),
], columns=["Item", "Type", "Proposed control", "Protects CQA", "Basis / status"])
cs.to_csv(OUT / "control_strategy.csv", index=False)
print("\nControl strategy (draft):")
print(cs[["Item", "Type", "Proposed control"]].to_string(index=False))

json.dump(dict(commercial_batch_kg=COMM_KG, exhibit_batch_kg=EXH_KG, lab_batch_kg=LAB_BATCH_KG, limiting_unit=limiting,
               batches_per_year=n_batches, press_hours_per_year=n_batches * press_h_batch,
               api_mg_per_tablet=mg["API (potency-adjusted)"]), open(OUT / "step7_summary.json", "w"), indent=2)

# ================================================================== process-flow figure
ops = [("Sifting", "Vibro sifter", None), ("Dry mix +\nwet granulation", "RMG", "RMG"), ("Drying", "FBD", "Fluid-bed dryer"),
       ("Milling", "Co-mill", None), ("Blending +\nlubrication", "Bin blender", "Bin blender"),
       ("Compression", "Rotary press", "Rotary tablet press"), ("Film coating", "Coating pan", "Coating pan")]
fig, ax = plt.subplots(figsize=(17, 4.2))
ax.set_xlim(0, 7 * 2.4); ax.set_ylim(0, 4); ax.axis("off")
for i, (title, short, key) in enumerate(ops):
    x = i * 2.4 + 0.1
    ax.add_patch(FancyBboxPatch((x, 0.2), 2.0, 3.4, boxstyle="round,pad=0.05", fc="#E6F4F1", ec="#0B7285"))
    ax.text(x + 1.0, 3.2, title, ha="center", va="center", fontweight="bold", fontsize=9)
    for j, sc in enumerate(BATCH):
        if key:
            r = eq[(eq.Scale == sc) & (eq.Unit_operation.str.contains(key, regex=False))].iloc[0]
            txt = r["Equipment_size"]
            if "stations" in txt:                       # shorten the press label to fit the box
                st_, _, rpm_ = PRESS[sc]
                txt = f"{st_} stations, {rpm_} rpm"
        else:
            txt = "same type"
        ax.text(x + 1.0, 2.5 - j * 0.85, f"{sc}:\n{txt}", ha="center", va="center", fontsize=7.5)
    if i < len(ops) - 1:
        ax.annotate("", xy=(x + 2.35, 1.9), xytext=(x + 2.1, 1.9), arrowprops=dict(arrowstyle="->", color="#0B7285", lw=2))
fig.suptitle(f"Process flow and equipment train: lab {BATCH['Lab']:.0f} kg, exhibit {BATCH['Exhibit']:.0f} kg, commercial {BATCH['Commercial']:.0f} kg", fontsize=11)
plt.savefig(OUT / "process_flow_scaleup.png", dpi=150, bbox_inches="tight")
print("\nSaved raw_material_requirement.csv, equipment_train.csv, scaleup_parameters.csv, control_strategy.csv, step7_summary.json, process_flow_scaleup.png")
