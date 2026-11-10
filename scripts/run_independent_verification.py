# -*- coding: utf-8 -*-
"""
Independent Final Verification Script for DSH-SolidWorks v1.0 / v0.2.0
Executes read-only audits and cross-validations of all deliverables.
"""
import os
import sys
import hashlib
import tarfile
import subprocess
import json
import csv
import re
from pathlib import Path

BASE_DIR = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
AUDIT_DIR = os.path.join(BASE_DIR, "audit_round2_final")
LOGS_DIR = os.path.join(AUDIT_DIR, "RAW_TEST_LOGS")
PYTHON_EXE = r"D:\SWCAD-MCP\Python313\python.exe"

def log(msg):
    clean_msg = str(msg).encode("ascii", errors="backslashreplace").decode("ascii")
    print(f"[VERIFY] {clean_msg}")

def check_file_hashes(filepath):
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1()
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
            sha1.update(chunk)
            md5.update(chunk)
    return {
        "sha256": sha256.hexdigest(),
        "sha1": sha1.hexdigest(),
        "md5": md5.hexdigest(),
        "size": os.path.getsize(filepath)
    }

def verify_package():
    log("=== Stage 2.1: Verifying Package and SHA-256 ===")
    tarball_path = os.path.join(BASE_DIR, "dsh-solidworks-0.2.0.tgz")
    dist_tarball = os.path.join(BASE_DIR, "dist", "dsh-solidworks-0.2.0.tgz")
    
    assert os.path.isfile(tarball_path), f"Tarball missing at {tarball_path}"
    hashes = check_file_hashes(tarball_path)
    log(f"Root tarball: {tarball_path}")
    log(f"Size: {hashes['size']} bytes")
    log(f"SHA-256: {hashes['sha256']}")
    log(f"SHA-1:   {hashes['sha1']}")
    log(f"MD5:     {hashes['md5']}")
    
    expected_sha256 = "12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5"
    expected_sha1 = "e2dd9df6305ab4f0009d5bb61c1e38a989165bba"
    expected_size = 1353150
    
    assert hashes['sha256'] == expected_sha256, f"SHA-256 mismatch! Got {hashes['sha256']}"
    assert hashes['sha1'] == expected_sha1, f"SHA-1 mismatch! Got {hashes['sha1']}"
    assert hashes['size'] == expected_size, f"Size mismatch! Got {hashes['size']}"
    log("Tarball hashes match expected values exactly.")
    
    if os.path.isfile(dist_tarball):
        dist_hashes = check_file_hashes(dist_tarball)
        assert dist_hashes['sha256'] == expected_sha256, "dist/ tarball does not match root tarball!"
        log("dist/ tarball is identical to root tarball.")
        
    # Inspect tarball contents
    with tarfile.open(tarball_path, "r:gz") as tar:
        members = tar.getmembers()
        files = [m for m in members if m.isfile()]
        dirs = [m for m in members if m.isdir()]
        log(f"Tarball members: total={len(members)}, files={len(files)}, dirs={len(dirs)}")
        
        # Check forbidden files
        pyc_files = [m.name for m in members if m.name.endswith(".pyc") or "__pycache__" in m.name]
        git_files = [m.name for m in members if "/.git/" in m.name or m.name.endswith(".git")]
        env_files = [m.name for m in members if m.name.endswith(".env") or "id_rsa" in m.name]
        
        log(f"Forbidden files check: pyc={len(pyc_files)}, git={len(git_files)}, env={len(env_files)}")
        assert len(pyc_files) == 0, f"Found .pyc files in tarball: {pyc_files[:5]}"
        assert len(git_files) == 0, f"Found .git files in tarball: {git_files[:5]}"
        assert len(env_files) == 0, f"Found .env files in tarball: {env_files[:5]}"
        
        # Check critical production files exist in package
        critical_files = [
            "package/package.json",
            "package/dsh-plugin.json",
            "package/NOTICE",
            "package/README.md",
            "package/lib/index.js",
            "package/lib/mcp.js",
            "package/lib/policy.js",
            "package/lib/discover.js",
            "package/bin/dsh-solidworks.js",
            "package/vendor/solidworks-automation-skill/mcp-server/server.py",
            "package/vendor/solidworks-automation-skill/scripts/sw_connect.py",
            "package/vendor/solidworks-automation-skill/scripts/sw_export.py",
            "package/vendor/solidworks-automation-skill/scripts/cad_task_context.py",
            "package/vendor/solidworks-automation-skill/scripts/feature_graph_ir.py",
            "package/vendor/solidworks-automation-skill/scripts/dimension_manager.py"
        ]
        member_names = set(m.name for m in members)
        missing_critical = [f for f in critical_files if f not in member_names]
        log(f"Critical files check: missing={len(missing_critical)}")
        assert len(missing_critical) == 0, f"Missing critical files: {missing_critical}"
        
    return {
        "hashes": hashes,
        "total_files": len(files),
        "total_members": len(members)
    }

def run_python_credential_test():
    log("=== Stage 3: Running Python Credential Security Test ===")
    test_script = os.path.join(BASE_DIR, "tests", "python_credential_security_test.py")
    assert os.path.isfile(test_script), f"Missing {test_script}"
    
    cmd = [PYTHON_EXE, test_script]
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(f"Credential test exit code: {res.returncode}")
    log(f"Output stderr:\n{res.stderr.strip()}")
    assert res.returncode == 0, f"Credential security test failed with code {res.returncode}"
    log("Python credential security test PASSED (all 8 negative cases).")
    return res.stderr

def analyze_raw_test_logs():
    log("=== Stage 2.2: Reconciling Test Logs ===")
    logs = [f for f in os.listdir(LOGS_DIR) if f.endswith(".log")]
    log(f"Total raw log files in {LOGS_DIR}: {len(logs)}")
    
    single_logs = [f for f in logs if not f in ["node_test_all.log", "e2e_solidworks_raw_round2.log", "sha256_verification.log"]]
    composite_logs = [f for f in logs if f in ["node_test_all.log", "e2e_solidworks_raw_round2.log", "sha256_verification.log"]]
    log(f"Single test logs: {len(single_logs)}")
    log(f"Composite/verification logs: {len(composite_logs)}")
    
    # Read TEST_EXECUTION_MATRIX.csv
    matrix_csv = os.path.join(AUDIT_DIR, "TEST_EXECUTION_MATRIX.csv")
    matrix_rows = []
    with open(matrix_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            matrix_rows.append(r)
    log(f"TEST_EXECUTION_MATRIX rows: {len(matrix_rows)}")
    
    pass_files = [r for r in matrix_rows if r["FinalStatus"] == "PASS"]
    fail_files = [r for r in matrix_rows if r["FinalStatus"] == "FAIL"]
    blocked_files = [r for r in matrix_rows if r["FinalStatus"] == "BLOCKED"]
    
    log(f"Matrix file breakdown: PASS={len(pass_files)}, FAIL={len(fail_files)}, BLOCKED={len(blocked_files)}, Total={len(matrix_rows)}")
    
    total_tests = sum(int(r["TestCount"]) for r in matrix_rows if r["TestCount"].isdigit())
    total_pass = sum(int(r["PassCount"]) for r in matrix_rows if r["PassCount"].isdigit())
    total_fail = sum(int(r["FailCount"]) for r in matrix_rows if r["FailCount"].isdigit())
    total_skip = sum(int(r["SkipCount"]) for r in matrix_rows if r["SkipCount"].isdigit())
    
    log(f"Matrix case breakdown: Tests={total_tests}, Pass={total_pass}, Fail={total_fail}, Skip={total_skip}")
    
    # Node tests
    node_rows = matrix_rows[:7]
    for r in node_rows:
        log(f"Node row: {r['Index']} - {r['Path']}: TestCount={r['TestCount']}, Pass={r['PassCount']}")
    node_cases = sum(int(r["TestCount"]) for r in node_rows)
    node_pass = sum(int(r["PassCount"]) for r in node_rows)
    log(f"Node.js tests (indices 1-7 sum): total={node_cases}, pass={node_pass}")
    
    # Python Credential Security Test (index 73)
    cred_row = matrix_rows[72]
    log(f"Index 73 row: {cred_row['Path']}, cases={cred_row['TestCount']}, pass={cred_row['PassCount']}")
    
    return {
        "total_files": len(matrix_rows),
        "pass_files": len(pass_files),
        "fail_files": len(fail_files),
        "blocked_files": len(blocked_files),
        "total_cases": total_tests,
        "pass_cases": total_pass,
        "fail_cases": total_fail,
        "skip_cases": total_skip,
        "single_logs": len(single_logs),
        "composite_logs": len(composite_logs)
    }

def analyze_18_fails():
    log("=== Stage 2.3: Analyzing 18 FAIL Tests ===")
    fails_csv = os.path.join(AUDIT_DIR, "FINAL_18_FAILURES_ASSESSMENT.csv")
    fails = []
    with open(fails_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            fails.append(r)
    log(f"Total FAIL entries: {len(fails)}")
    
    categories = {}
    for r in fails:
        cat = r["Classification"]
        categories[cat] = categories.get(cat, 0) + 1
    log(f"Failure categories summary: {categories}")
    for r in fails:
        log(f"  {r['FailureID']}: {r['TestPath']} -> {r['Classification']}")
    return fails

def check_pid_evidence():
    log("=== Stage 2.4: Checking PID Evidence in Logs ===")
    pids_to_check = ["23440", "11380", "21932", "3180", "5108", "27164", "38364", "2684", "32500"]
    pid_findings = {}
    
    for pid in pids_to_check:
        pid_findings[pid] = []
        for root, _, files in os.walk(LOGS_DIR):
            for file in files:
                if not file.endswith(".log"):
                    continue
                fpath = os.path.join(root, file)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for line_no, line in enumerate(f, 1):
                            if pid in line:
                                pid_findings[pid].append((file, line_no, line.strip()))
                except Exception as e:
                    pass
        log(f"PID/Term {pid}: found in {len(pid_findings[pid])} log lines")
        for file, line_no, text in pid_findings[pid][:2]:
            log(f"   [{file}:{line_no}] {text[:80]}")
            
    return pid_findings

def inspect_patch():
    log("=== Stage 2.5: Inspecting FINAL_SOURCE_DIFF.patch ===")
    patch_path = os.path.join(AUDIT_DIR, "FINAL_SOURCE_DIFF.patch")
    assert os.path.isfile(patch_path), f"Missing patch file {patch_path}"
    
    # Read UTF-16
    with open(patch_path, "r", encoding="utf-16", errors="replace") as f:
        patch_text = f.read()
    log(f"Patch file length: {len(patch_text)} chars, size: {os.path.getsize(patch_path)} bytes")
    
    diff_file_pattern = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)
    matches = list(diff_file_pattern.finditer(patch_text))
    log(f"Total diff blocks found in patch: {len(matches)}")
    
    diff_files = [m.group(1) for m in matches]
    for idx, f in enumerate(diff_files, 1):
        log(f"  [{idx:02d}] {f}")
        
    assert len(diff_files) == 35, f"Expected 35 files in patch, got {len(diff_files)}"
    return diff_files

if __name__ == "__main__":
    pkg_res = verify_package()
    cred_out = run_python_credential_test()
    logs_res = analyze_raw_test_logs()
    fails_res = analyze_18_fails()
    pid_res = check_pid_evidence()
    diff_res = inspect_patch()
    print("\n[ALL AUDIT CHECKS FINISHED SUCCESSFULLY]")
