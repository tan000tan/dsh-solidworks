# -*- coding: utf-8 -*-
import csv
import os

AUDIT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit_round2_final")
LOGS_DIR = os.path.join(AUDIT_DIR, "RAW_TEST_LOGS")
fails_csv = os.path.join(AUDIT_DIR, "FINAL_18_FAILURES_ASSESSMENT.csv")

with open(fails_csv, "r", encoding="utf-8-sig") as f:
    fails = list(csv.DictReader(f))

def safe_print(msg):
    clean = str(msg).encode("ascii", errors="backslashreplace").decode("ascii")
    print(clean)

safe_print(f"=== DETAILED AUDIT OF 18 FAILS (Total: {len(fails)}) ===")
for r in fails:
    fid = r["FailureID"]
    path = r["TestPath"]
    cls = r["Classification"]
    # find corresponding log file
    log_name = path.replace("/", "_").replace("\\", "_") + ".log"
    log_path = os.path.join(LOGS_DIR, log_name)
    err_snippet = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
            lines = lf.readlines()
            err_lines = [l.strip() for l in lines if any(w in l for w in ["Error:", "Exception:", "FAIL:", "FAILED", "AssertionError", "SecurityPolicyError", "CADWriteAuthorizationError"])]
            err_snippet = "; ".join(err_lines[-3:]) if err_lines else lines[-1].strip()
    else:
        err_snippet = f"Log file missing: {log_name}"
    safe_print(f"\n[{fid}] {path} -> {cls}")
    safe_print(f"   RawError: {r['RawError'][:90]}")
    safe_print(f"   LogSnippet: {err_snippet[:100]}")
