# -*- coding: utf-8 -*-
import os, sys, csv
from pathlib import Path

repo = Path(r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin")
rem_csv = repo / "audit" / "remediation-2026-11-06" / "05_FINAL_TEST_RESULTS.csv"

with open(rem_csv, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Total rows in 05_FINAL_TEST_RESULTS.csv: {len(rows)}")

# Analyze each test case
categories = {}
execution_types = {}
for r in rows:
    c = r["category"]
    et = r["execution_type"]
    categories[c] = categories.get(c, 0) + 1
    execution_types[et] = execution_types.get(et, 0) + 1

print("\nCategories breakdown:")
for k, v in categories.items():
    print(f"  {k}: {v}")

print("\nExecution types breakdown:")
for k, v in execution_types.items():
    print(f"  {k}: {v}")

# Classify each of the 184 tests:
# Real COM physical tests:
# - TS-CAD-E2E-01 to 12 (12 tests)
# Node.js Protocol & Security (real Node execution, mock COM):
# - TS-NODE-* (68 tests)
# Python Algorithmic / DAG / Inspector Unit (pure python computation):
# - TS-PY-S5-* (30 tests)
# - TS-REM-INSP-* (8 tests)
# Remediation User & Stress (STA queue, parameter parsing, path defense, mock):
# - TS-REM-USER-* (10 tests)
# - TS-REM-STRESS-* (38 tests)
# Environment probe / static check:
# - TS-REM-COMPAT-* (18 tests)

real_com_count = 12
node_unit_security_count = 68
python_algo_unit_count = 30 + 8
mock_or_local_parameter_count = 10 + 38
env_probe_static_count = 18

print(f"\nIndependent Classification of 184 claimed tests:")
print(f"1. Real Physical SolidWorks COM Tests: {real_com_count} (6.5%)")
print(f"2. Node.js Security Policy & Protocol Tests: {node_unit_security_count} (37.0%)")
print(f"3. Python Algorithmic & Quality Unit Tests: {python_algo_unit_count} (20.7%)")
print(f"4. Local Parameter, Exception & STA Queue Tests: {mock_or_local_parameter_count} (26.1%)")
print(f"5. Host Environment Probing & File Existence Checks: {env_probe_static_count} (9.8%)")
