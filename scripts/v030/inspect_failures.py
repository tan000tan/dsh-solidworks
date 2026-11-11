import json

path = r"<PROJECT_ROOT>\v0.3.0-phase1-6-delivery\evidence_raw\A-Audit\baseline_test_results.json"
with open(path, "r", encoding="utf-8") as f:
    d = json.load(f)

print("=== Node Failures ===")
for r in d["node_tests"]["details"]:
    if r["status"] != "PASS":
        print(f"Command: {r['cmd']}")
        print(f"Exit code: {r['exit_code']}, Elapsed: {r['elapsed_seconds']}s")
        print(f"Stdout:\n{r['stdout']}")
        print(f"Stderr:\n{r['stderr']}")
        print("="*50)

print("\n=== Python Failures ===")
for r in d["python_tests"]["details"]:
    if r["status"] != "PASS":
        print(f"File: {r['test_file']}")
        print(f"Exit code: {r['exit_code']}, Elapsed: {r['elapsed_seconds']}s")
        print(f"Stdout:\n{r['stdout']}")
        print(f"Stderr:\n{r['stderr']}")
        print("="*50)
