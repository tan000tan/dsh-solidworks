# -*- coding: utf-8 -*-
import os
import re
import csv

BASE_DIR = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
AUDIT_DIR = os.path.join(BASE_DIR, "audit_round2_final")
patch_path = os.path.join(AUDIT_DIR, "FINAL_SOURCE_DIFF.patch")

with open(patch_path, "r", encoding="utf-16", errors="replace") as f:
    patch_text = f.read()

# Split into per-file diffs
diff_blocks = re.split(r"(?=^diff --git )", patch_text, flags=re.MULTILINE)
diff_blocks = [b for b in diff_blocks if b.strip().startswith("diff --git")]

print(f"Total diff blocks in patch: {len(diff_blocks)}")

diff_summary = []
for block in diff_blocks:
    lines = block.splitlines()
    header = lines[0]
    m = re.match(r"^diff --git a/(.*?) b/(.*?)$", header)
    if not m:
        continue
    fpath = m.group(1)
    full_path = os.path.join(BASE_DIR, fpath)
    exists = os.path.exists(full_path)
    
    additions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    
    diff_summary.append({
        "path": fpath,
        "exists": exists,
        "additions": additions,
        "deletions": deletions,
        "lines_count": len(lines)
    })

for idx, d in enumerate(diff_summary, 1):
    status = "OK" if d["exists"] else "MISSING"
    print(f"[{idx:02d}] {d['path']:<55} | {status} | +{d['additions']:<4} -{d['deletions']:<4}")
