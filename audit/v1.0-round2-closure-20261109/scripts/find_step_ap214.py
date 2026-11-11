import os

repo = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
matches = []
for root, dirs, files in os.walk(repo):
    if any(x in root for x in ['.git', 'node_modules', '.venv', 'audit']):
        continue
    for f in files:
        if f.endswith(('.py', '.js', '.mjs', '.md')):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='replace') as fp:
                c = fp.read()
                if 'swStepAP' in c or 'StepAP' in c or 'AP214' in c:
                    for l in c.splitlines():
                        if any(k in l for k in ['swStepAP', 'StepAP', 'AP214', '214']):
                            matches.append((os.path.relpath(p, repo), l.strip()))

out_p = os.path.join(repo, 'audit', 'v1.0-round2-closure-20261109', 'step_ap214_audit.txt')
with open(out_p, 'w', encoding='utf-8') as out:
    for m in matches:
        out.write(f"{m[0]}: {m[1]}\n")

print(f"Total STEP AP214 occurrences: {len(matches)}. Written to {out_p}")
