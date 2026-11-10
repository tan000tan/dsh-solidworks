import os
import sys
import subprocess
import time
from pathlib import Path

plugin_root = Path(__file__).resolve().parent.parent
tests_dir = plugin_root / "tests"

python_test_files = [
    "cad_graph_executor_test.py",
    "cad_task_context_test.py",
    "cad_task_planner_test.py",
    "com_worker_test.py",
    "dimension_dependency_graph_test.py",
    "dimension_manager_test.py",
    "dimension_system_test.py",
    "engine_reliability_test.py",
    "failure_injection_test.py",
    "feature_graph_test.py",
    "inspector_adversarial_attack_test.py",
    "ir_solidworks_end_to_end_test.py",
    "mcp_failure_cleanup_e2e_test.py",
    "mcp_mid_operation_failure_test.py",
    "model_quality_inspector_test.py",
    "param_extractor_test.py",
    "rem_compat_test.py",
    "rem_stress_test.py",
    "rem_user_test.py",
    "remediation_cad_quality_inspector_test.py",
    "security_regression_test.py",
    "shadow_backup_test.py",
    "stage5_advanced_aicad_integration_test.py",
    "stage5_assembly_planner_test.py",
    "stage5_auto_iteration_test.py",
    "stage5_cad_context_test.py",
    "stage5_feature_tree_optimizer_test.py",
    "stage5_multi_scheme_planner_test.py",
    "stage5_quality_inspector_test.py",
    "task_state_machine_test.py",
    "unified_dimension_migration_test.py",
    "window_recovery_test.py",
]

env = os.environ.copy()
env["PYTHONDONTWRITEBYTECODE"] = "1"
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
python_exe = os.environ.get("DSH_SOLIDWORKS_PYTHON", sys.executable)
env["DSH_SOLIDWORKS_PYTHON"] = python_exe

results = {}
total_pass = 0
total_fail = 0
total_skip = 0

print(f"=== EXECUTING ALL {len(python_test_files)} PYTHON TEST SUITES ===")

for tfile in python_test_files:
    tpath = tests_dir / tfile
    if not tpath.exists():
        print(f"  [MISSING] {tfile}")
        results[tfile] = {"status": "MISSING", "code": -1, "output": ""}
        continue
    
    t0 = time.time()
    cmd = [python_exe, "-B", str(tpath)]
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=str(plugin_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=450
        )
        duration = time.time() - t0
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode == 0:
            if "skipped=" in out or "OK (skipped=" in out or "s" in out.splitlines()[-1]:
                # 解析包含 skipped 的情况
                pass
            results[tfile] = {"status": "PASS", "code": 0, "duration": duration, "output": out}
            total_pass += 1
            print(f"  [PASS] {tfile} ({duration:.2f}s)")
        else:
            results[tfile] = {"status": "FAIL", "code": proc.returncode, "duration": duration, "output": out}
            total_fail += 1
            print(f"  [FAIL] {tfile} (exit {proc.returncode}, {duration:.2f}s)")
    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        results[tfile] = {"status": "TIMEOUT", "code": -1, "duration": duration, "output": "Timed out after 450s"}
        total_fail += 1
        print(f"  [TIMEOUT] {tfile} ({duration:.2f}s)")
    except Exception as e:
        results[tfile] = {"status": "ERROR", "code": -2, "duration": 0, "output": str(e)}
        total_fail += 1
        print(f"  [ERROR] {tfile}: {e}")

print(f"\n==========================================")
print(f"=== ALL TEST SUITES EXECUTION COMPLETED ===")
print(f"=== PASSED: {total_pass} / {len(python_test_files)}")
print(f"=== FAILED: {total_fail} / {len(python_test_files)}")
print(f"==========================================")

# 将明细保存为 JSON
import json
out_dir = plugin_root / "audit" / "v1.0-final-release"
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "python_tests_summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
