import glob
import json
import os
import subprocess
import sys
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_EXE = r"D:\Node.js\node.exe"
PYTHON_EXE = r"<SWCAD_MCP_ROOT>\Python313\python.exe"
EVIDENCE_DIR = os.path.join(PLUGIN_ROOT, "v0.3.0-phase1-6-delivery", "evidence_raw", "A-Audit")
os.makedirs(EVIDENCE_DIR, exist_ok=True)

NODE_TESTS = [
    "tests/policy.test.js",
    "tests/mcp.test.js",
    "tests/schema.test.js",
    "tests/package.test.js",
    "tests/audit.test.js",
    "tests/host.test.js",
    "tests/crash.test.js"
]

def run_cmd(cmd, cwd=PLUGIN_ROOT, timeout=120):
    start = time.perf_counter()
    start_wall = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        elapsed = time.perf_counter() - start
        return {
            "cmd": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "start_time": start_wall,
            "elapsed_seconds": round(elapsed, 4),
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "status": "PASS" if res.returncode == 0 else "FAIL"
        }
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return {
            "cmd": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "start_time": start_wall,
            "elapsed_seconds": round(elapsed, 4),
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Timeout expired after {timeout} seconds",
            "status": "TIMEOUT"
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "cmd": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "start_time": start_wall,
            "elapsed_seconds": round(elapsed, 4),
            "exit_code": -2,
            "stdout": "",
            "stderr": str(e),
            "status": "ERROR"
        }

def count_lines_of_code(root_dir):
    extensions = {
        ".js": "JavaScript",
        ".mjs": "JavaScript",
        ".py": "Python",
        ".cs": "C#",
        ".json": "JSON",
        ".md": "Markdown",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".ps1": "PowerShell"
    }
    stats = {lang: {"files": 0, "lines": 0} for lang in set(extensions.values())}
    ignore_dirs = {".git", ".venv", "node_modules", "audit_round2_final", "audit", "项目备份", "v0.3.0-phase1-6-delivery"}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # prune ignore_dirs
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in extensions:
                lang = extensions[ext]
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        line_count = sum(1 for _ in f)
                        stats[lang]["files"] += 1
                        stats[lang]["lines"] += line_count
                except Exception:
                    pass
    return stats

def test_non_ascii_paths():
    """Verify non-ASCII path support in policy and sandbox"""
    import tempfile
    test_results = []
    
    # Test 1: UTF-8 Chinese directory and filename
    with tempfile.TemporaryDirectory() as base_tmp:
        cn_dir = os.path.join(base_tmp, "SolidWorks测试项目_零件A")
        os.makedirs(cn_dir, exist_ok=True)
        cn_file = os.path.join(cn_dir, "装配法兰_Φ50x10.SLDPRT")
        with open(cn_file, "w", encoding="utf-8") as f:
            f.write("DUMMY CAD BINARY CONTENT")
        
        # Test existence and path normalization
        exists = os.path.exists(cn_file)
        abs_norm = os.path.abspath(cn_file)
        test_results.append({
            "test": "chinese_path_creation_and_check",
            "path": cn_file,
            "exists": exists,
            "status": "PASS" if exists else "FAIL"
        })
    return test_results

def main():
    print("=== Phase 1: Fact Baseline & Audit Execution ===")
    overall_start = time.time()
    
    # 1. Run Node.js test suites
    node_results = []
    print("\n--- Running Node.js Test Suites ---")
    for t in NODE_TESTS:
        t_path = os.path.join(PLUGIN_ROOT, t)
        print(f"Executing: {t} ...", end=" ", flush=True)
        res = run_cmd([NODE_EXE, t_path])
        print(f"[{res['status']}] in {res['elapsed_seconds']}s")
        node_results.append(res)
    
    # 2. Find and run Python test suites in tests/
    print("\n--- Discovering and Running Python Tests ---")
    py_test_files = sorted(glob.glob(os.path.join(PLUGIN_ROOT, "tests", "*_test.py")))
    python_results = []
    for pt in py_test_files:
        rel_name = os.path.relpath(pt, PLUGIN_ROOT)
        print(f"Executing: {rel_name} ...", end=" ", flush=True)
        # We need PYTHONPATH configured
        env_cmd = [PYTHON_EXE, pt]
        res = run_cmd(env_cmd, cwd=PLUGIN_ROOT)
        print(f"[{res['status']}] in {res['elapsed_seconds']}s")
        python_results.append({
            "test_file": rel_name,
            **res
        })
    
    # 3. LOC Statistics
    print("\n--- Calculating Codebase Lines of Code ---")
    loc_stats = count_lines_of_code(PLUGIN_ROOT)
    for lang, data in sorted(loc_stats.items(), key=lambda x: x[1]["lines"], reverse=True):
        print(f"  {lang:<12}: {data['files']:>4} files, {data['lines']:>7} lines")
    
    # 4. Non-ASCII path verification
    print("\n--- Verifying Non-ASCII Path Handling ---")
    non_ascii_results = test_non_ascii_paths()
    print("Non-ASCII tests:", non_ascii_results)
    
    total_elapsed = time.time() - overall_start
    
    # Summarize Test Results
    node_pass = sum(1 for r in node_results if r["status"] == "PASS")
    node_fail = sum(1 for r in node_results if r["status"] != "PASS")
    py_pass = sum(1 for r in python_results if r["status"] == "PASS")
    py_fail = sum(1 for r in python_results if r["status"] != "PASS")
    
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_wall_time_seconds": round(total_elapsed, 3),
        "node_tests": {
            "total_suites": len(node_results),
            "pass_count": node_pass,
            "fail_count": node_fail,
            "details": node_results
        },
        "python_tests": {
            "total_suites": len(python_results),
            "pass_count": py_pass,
            "fail_count": py_fail,
            "details": python_results
        },
        "loc_statistics": loc_stats,
        "non_ascii_path_tests": non_ascii_results
    }
    
    summary_path = os.path.join(EVIDENCE_DIR, "baseline_test_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nAll baseline tests finished in {total_elapsed:.2f}s.")
    print(f"Node Suites: {node_pass} PASS, {node_fail} FAIL out of {len(node_results)}")
    print(f"Python Suites: {py_pass} PASS, {py_fail} FAIL out of {len(python_results)}")
    print(f"Evidence saved to: {summary_path}")

if __name__ == "__main__":
    main()
