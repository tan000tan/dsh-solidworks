import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGING_DIR = os.path.join(ROOT, "temp_evidence_v030")
DELIVERY_DIR = os.path.join(ROOT, "v0.3.0-final-verification-delivery")

CATEGORIES = [
    "A-Git-and-Code-Audit",
    "B-Architecture-and-COM",
    "C-Installation-and-Environment",
    "D-CAD-Real-Verification",
    "E-Security-and-Safety",
    "F-Performance-and-UX",
    "G-Multi-Version-Compatibility",
    "H-Regression-and-Failure-History"
]

os.makedirs(DELIVERY_DIR, exist_ok=True)
for cat in CATEGORIES:
    p = os.path.join(STAGING_DIR, cat)
    os.makedirs(p, exist_ok=True)
    print(f"Created category dir: {p}")

print("Evidence staging structure ready.")
