# -*- coding: utf-8 -*-
import csv
import os

AUDIT_DIR = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit_round2_final"
matrix_csv = os.path.join(AUDIT_DIR, "TEST_EXECUTION_MATRIX.csv")

with open(matrix_csv, "r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

print(f"Total rows: {len(rows)}")
for r in rows:
    cnt = int(r["TestCount"]) if r["TestCount"].isdigit() else 0
    if cnt > 15:
        print(f"Row {r['Index']:>2}: {r['Path']:<50} | Count={cnt:>3} | Pass={r['PassCount']:>3} | Fail={r['FailCount']:>3}")

total_tests = sum(int(r["TestCount"]) for r in rows if r["TestCount"].isdigit())
total_pass = sum(int(r["PassCount"]) for r in rows if r["PassCount"].isdigit())
total_fail = sum(int(r["FailCount"]) for r in rows if r["FailCount"].isdigit())
total_skip = sum(int(r["SkipCount"]) for r in rows if r["SkipCount"].isdigit())
print(f"Sum TestCount: {total_tests}, Pass: {total_pass}, Fail: {total_fail}, Skip: {total_skip}")
