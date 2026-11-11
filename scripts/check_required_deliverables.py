# -*- coding: utf-8 -*-
import os

audit = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit_round2_final")
required = [
    "FINAL_ACCEPTANCE_REPORT.md",
    "FINAL_EVIDENCE_INDEX.md",
    "FINAL_TEST_RECONCILIATION.csv",
    "FINAL_FAIL_CLASSIFICATION.csv",
    "FINAL_PID_LIFECYCLE.md",
    "FINAL_PATCH_REVIEW.md",
    "FINAL_CREDENTIAL_SECURITY_REVIEW.md",
    "FINAL_RELEASE_MANIFEST.md",
    "FINAL_RELEASE_RECORD.md"
]
for r in required:
    p = os.path.join(audit, r)
    if os.path.isfile(p):
        print(f"{r:<40}: EXISTS ({os.path.getsize(p)} bytes)")
    else:
        print(f"{r:<40}: MISSING")
