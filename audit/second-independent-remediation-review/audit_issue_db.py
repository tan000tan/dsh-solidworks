# -*- coding: utf-8 -*-
import json
from pathlib import Path

p = Path(r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\remediation-2026-11-06\ISSUE_DATABASE_REMEDIATED.json")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)

print("Schema Version:", data.get("schema_version"))
print("Summary:", data.get("summary"))

real_defects = data.get("real_engineering_defects", [])
templates = data.get("templated_checklist_entries", [])

print(f"real_engineering_defects count: {len(real_defects)}")
print(f"templated_checklist_entries count: {len(templates)}")

total_items = real_defects + templates
print(f"Total combined count: {len(total_items)}")

ids = [item.get("id") or item.get("issue_id") for item in total_items]
unique_ids = set(ids)
print(f"Total IDs: {len(ids)}, Unique IDs: {len(unique_ids)}")

print("\n--- Real Engineering Defects ---")
for rd in real_defects:
    v_info = rd.get("verification", {})
    method = v_info.get("method") if isinstance(v_info, dict) else str(v_info)
    print(f"[{rd.get('id')}] Status={rd.get('status')}, Title={rd.get('title')}, Method={method}")
