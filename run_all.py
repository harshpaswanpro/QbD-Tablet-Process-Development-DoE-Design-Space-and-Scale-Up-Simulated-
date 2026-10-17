"""Run the whole workflow (steps 1-7) in order. Outputs go to ./outputs."""
import subprocess
import sys

STEPS = ["step1_qtpp_fmea.py", "step2_doe_design.py", "step3_simulate_responses.py", "step4_rsm_anova.py",
         "step5_design_space.py", "step6_confirmatory_batches.py", "step7_scaleup_plan.py"]

for s in STEPS:
    print(f"\n=== Running {s} ===")
    if subprocess.run([sys.executable, s]).returncode != 0:
        sys.exit(f"{s} failed; stopping.")
print("\nAll steps finished. See the outputs/ folder.")
