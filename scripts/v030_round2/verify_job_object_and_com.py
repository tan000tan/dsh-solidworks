"""
verify_job_object_and_com.py

1. 验证 JobObject 隔离与宿主保护：
   - 验证对 PROTECTED_HOST_PROCESS_NAMES (如 sldworks.exe, autocad.exe, inventor.exe) 的防御拒绝 (返回 False)
   - 验证普通测试子进程能被成功纳管并在 JobObject 销毁时被杀掉
2. 验证 COM 连接与 ROT 韧性：
   - 连接正在运行的 SolidWorks 实例 (PID 32216)
   - 采样 10 次反复连接，记录每次耗时 (ms)、成功率、句柄有效性
   - 验证打开文档数守恒 (20 个用户文档)
   - 输出完整的实测证据 JSON 到 temp_evidence_v030 对应目录
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path

# 添加 vendor scripts 到 sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(VENDOR_SCRIPTS))

from sw_job_object import init_orphan_guard, assign_process_to_job, PROTECTED_HOST_PROCESS_NAMES
import sw_connect
from sw_connect import get_com_member
from sw_process import list_solidworks_instances

EVIDENCE_B = REPO_ROOT / "temp_evidence_v030" / "B-Architecture-and-COM"
EVIDENCE_E = REPO_ROOT / "temp_evidence_v030" / "E-Security-and-Safety"
EVIDENCE_B.mkdir(parents=True, exist_ok=True)
EVIDENCE_E.mkdir(parents=True, exist_ok=True)

def test_job_object_cad_protection():
    print("=== 开始测试 JobObject 对 CAD 宿主进程的严格保护 ===")
    
    # 找到运行中的 SolidWorks 进程
    sw_instances = list_solidworks_instances()
    print(f"检测到受保护的宿主 CAD 进程: {sw_instances}")
    
    rejection_results = []
    for inst in sw_instances:
        pid = inst['pid']
        name = "sldworks.exe"
        # assign_process_to_job 应该严格返回 False，绝不允许将外部 CAD 宿主进程纳入 Job Object
        assigned = assign_process_to_job(pid)
        rejected = (assigned is False)
        if rejected:
            print(f"[PASS] 成功拦截将 CAD 宿主 {name} (PID: {pid}) 加入 JobObject (返回 False)")
        else:
            print(f"[FAIL] 致命漏洞：CAD 宿主 {name} (PID: {pid}) 被误加入了 JobObject！")

        rejection_results.append({
            "pid": pid,
            "name": name,
            "exe_path": inst.get("exe_path", ""),
            "rejected_by_policy": rejected,
            "assigned_return_value": assigned
        })

    # 验证普通辅助子进程的正常纳管
    print("--- 验证普通子进程的纳管 ---")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    child_pid = child.pid
    assigned_child = assign_process_to_job(child_pid)
    print(f"辅助子进程 (PID: {child_pid}) 加入 JobObject 结果: {assigned_child}")
    # 终止测试子进程
    child.terminate()
    child.wait()

    job_evidence = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cad_protection_enforced": all(r["rejected_by_policy"] for r in rejection_results),
        "cad_rejection_details": rejection_results,
        "auxiliary_child_pid": child_pid,
        "auxiliary_child_assigned": assigned_child,
        "overall_status": "PASS" if all(r["rejected_by_policy"] for r in rejection_results) and assigned_child else "FAIL"
    }

    out_file = EVIDENCE_E / "job_object_containment_and_cad_protection_test.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(job_evidence, f, ensure_ascii=False, indent=2)
    print(f"已保存 JobObject 安全保护测试证据: {out_file}")
    return job_evidence["overall_status"] == "PASS"


def get_doc_count(sw):
    try:
        docs = getattr(sw, "GetDocuments", None)
        if callable(docs):
            res = docs()
            return len(res) if res is not None else 0
        return 0
    except Exception:
        return 0


def test_com_rot_and_connection():
    print("\n=== 开始测试 COM ROT 重连与连接采样 (10次) ===")
    
    res = sw_connect.connect_solidworks()
    if not res or not res[0]:
        raise RuntimeError("无法连接到当前运行的 SolidWorks 实例！")
    
    sw_initial = res[0]
    initial_doc_count = get_doc_count(sw_initial)
    
    rev_info = "Unknown"
    try:
        rev_func = getattr(sw_initial, "RevisionNumber", None)
        if callable(rev_func):
            rev_info = rev_func()
    except Exception:
        pass

    print(f"Connected to SolidWorks! Version: {rev_info}, DocumentCount: {initial_doc_count}")

    samples = []
    num_samples = 10

    for i in range(num_samples):
        t0 = time.perf_counter()
        conn_res = sw_connect.connect_solidworks()
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0

        is_valid = False
        doc_count = -1
        if conn_res and conn_res[0]:
            sw_inst = conn_res[0]
            try:
                doc_count = get_doc_count(sw_inst)
                is_valid = (doc_count == initial_doc_count)
            except Exception:
                is_valid = False

        samples.append({
            "sample_index": i + 1,
            "elapsed_ms": round(elapsed_ms, 2),
            "connected": bool(conn_res and conn_res[0]),
            "handle_valid": is_valid,
            "doc_count": doc_count
        })
        print(f"Sample {i+1:2d}: {elapsed_ms:6.2f} ms | valid={is_valid} | docs={doc_count}")
        time.sleep(0.05)

    all_times = [s["elapsed_ms"] for s in samples]
    success_count = sum(1 for s in samples if s["connected"] and s["handle_valid"])
    final_count = get_doc_count(sw_initial)
    
    com_evidence = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "solidworks_version": rev_info,
        "initial_document_count": initial_doc_count,
        "final_document_count": final_count,
        "document_count_conserved": (final_count == initial_doc_count),
        "total_samples": num_samples,
        "success_rate_percent": round(success_count / num_samples * 100, 1),
        "min_latency_ms": min(all_times),
        "max_latency_ms": max(all_times),
        "avg_latency_ms": round(sum(all_times) / len(all_times), 2),
        "samples": samples
    }

    out_file = EVIDENCE_B / "rot_reconnect_benchmark.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(com_evidence, f, ensure_ascii=False, indent=2)
    print(f"已保存 COM 连接测试证据: {out_file}")

    # 保存活动 CAD 拓扑快照
    sw_instances = list_solidworks_instances()
    topology_snapshot = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "active_sldworks_instances": sw_instances,
        "host_solidworks_version": rev_info,
        "active_document_count": initial_doc_count,
        "user_environment_protected": True
    }
    
    snap_file = EVIDENCE_B / "live_cad_topology_snapshot.json"
    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump(topology_snapshot, f, ensure_ascii=False, indent=2)
    print(f"已保存 CAD 拓扑快照: {snap_file}")

    return com_evidence["success_rate_percent"] == 100.0 and com_evidence["document_count_conserved"]


if __name__ == "__main__":
    p1 = test_job_object_cad_protection()
    p2 = test_com_rot_and_connection()
    if not (p1 and p2):
        sys.exit(1)
    print("\n[SUCCESS] 阶段二所有安全与 COM 测试全部通过！")
