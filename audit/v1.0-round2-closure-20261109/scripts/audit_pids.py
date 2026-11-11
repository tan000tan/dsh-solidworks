import os
import re
import json

repo = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
audit_root = os.path.join(repo, "audit")

target_pids = ["2684", "32500", "27164", "38364"]
findings = {pid: [] for pid in target_pids}

for root, dirs, files in os.walk(audit_root):
    for f in files:
        if f.endswith((".log", ".md", ".json", ".txt")):
            p = os.path.join(root, f)
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fp:
                    content = fp.read()
                    for pid in target_pids:
                        if pid in content:
                            matches = [l.strip() for l in content.splitlines() if pid in l]
                            rel = os.path.relpath(p, audit_root).replace("\\", "/")
                            findings[pid].append({
                                "file": rel,
                                "match_count": len(matches),
                                "sample": matches[:5]
                            })
            except Exception:
                pass

report_p = os.path.join(repo, "audit", "v1.0-round2-closure-20261109", "PID_LIFECYCLE_AUDIT.json")
with open(report_p, "w", encoding="utf-8") as out:
    json.dump(findings, out, ensure_ascii=False, indent=2)

print("PID audit complete!")
for pid in target_pids:
    print(f"PID {pid}: found in {len(findings[pid])} files")
