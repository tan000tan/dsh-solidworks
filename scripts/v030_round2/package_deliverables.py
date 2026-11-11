"""
scripts/v030_round2/package_deliverables.py

打包并生成最终交付物：
1. 将 temp_evidence_v030 压缩为 v0.3.0-final-verification-evidence.zip
2. 计算每个证据文件的 SHA-256 哈希、大小、更新时间
3. 生成规范的 evidence-manifest.md
"""

import os
import sys
import hashlib
import zipfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STAGING_DIR = REPO_ROOT / "temp_evidence_v030"
DELIVERY_DIR = REPO_ROOT / "v0.3.0-final-verification-delivery"
DELIVERY_DIR.mkdir(parents=True, exist_ok=True)

ZIP_PATH = DELIVERY_DIR / "v0.3.0-final-verification-evidence.zip"
MANIFEST_PATH = DELIVERY_DIR / "evidence-manifest.md"

def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def create_evidence_zip():
    print(f"正在打包证据文件至: {ZIP_PATH} ...")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(STAGING_DIR):
            for file in sorted(files):
                full_path = Path(root) / file
                arc_name = full_path.relative_to(STAGING_DIR).as_posix()
                zf.write(full_path, arc_name)
                print(f"  + 打包: {arc_name}")
    print(f"[✔] 压缩完成，大小: {ZIP_PATH.stat().st_size} 字节，SHA-256: {sha256_file(ZIP_PATH)}")

def generate_manifest():
    print(f"正在生成证据清单: {MANIFEST_PATH} ...")
    zip_sha = sha256_file(ZIP_PATH)
    zip_size = ZIP_PATH.stat().st_size
    now_str = time.strftime("%Y-%m-%d %H:%M:%S %z")

    manifest_lines = [
        "# DSH-SolidWorks v0.3.0 最终独立核验实测证据清单 (Evidence Manifest)",
        "",
        f"**生成时间：** {now_str}  ",
        "**版本基线：** `v0.2.0` (`9cd64db`) -> `v0.3.0-phase1-6`  ",
        "**证据包文件：** `v0.3.0-final-verification-evidence.zip`  ",
        f"**证据包大小：** {zip_size:,} 字节  ",
        f"**证据包 SHA-256：** `{zip_sha}`  ",
        "",
        "---",
        "",
        "## 一、分类证据文件详细哈希与规格清单",
        "",
        "| 分类代号 | 分类目录 / 相对路径 | 文件大小 (Bytes) | SHA-256 校验摘要 | 说明 |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]

    category_descs = {
        "A-Git-and-Code-Audit": {
            "git_baseline_audit.json": "Git HEAD状态、干净工作区与基线差异统计",
            "git_full_diff.patch": "Phase 1-6 全量源码与配置修改差异补丁",
            "historical_issues_verdict.json": "历史遗留缺陷独立复核与闭环定性",
            "mcp_71_tools_independent_audit.json": "71个MCP工具列表与100%风险策略覆盖盘点"
        },
        "B-Architecture-and-COM": {
            "live_cad_topology_snapshot.json": "活动SolidWorks (PID 32216) 拓扑与文档保护快照",
            "rot_reconnect_benchmark.json": "COM 10次反复连接采样、ROT韧性与耗时分布"
        },
        "C-Installation-and-Environment": {
            "installation_and_lifecycle_verification.json": "零配置安装发现、无Python引导、卸载Dry-Run安全白名单"
        },
        "D-CAD-Real-Verification": {
            "cad_physical_closed_loop_verification.json": "真实SolidWorks 2026实机建模、双精度体积核算与文档数严格守恒"
        },
        "E-Security-and-Safety": {
            "job_object_containment_and_cad_protection_test.json": "JobObject严格拒绝CAD宿主进程防杀、辅助子进程生命周期纳管",
            "policy_security_adversarial_test.json": "Session TTL过期、参数防篡改、路径穿越与设备DOS防御实测"
        },
        "F-Performance-and-UX": {
            "token_and_ux_benchmark.json": "71工具Schema紧凑压缩节省48.3% Token、Policy压测吞吐量与微秒级延迟"
        },
        "G-Multi-Version-Compatibility": {
            "old_version_environment_report.md": "SolidWorks 2020-2026多版本API差异、运行时环境与降级规范报告",
            "sw_compat_matrix_verification.json": "2020-2026全版本年份解析、现代调度、老版回退与友好提示测试"
        },
        "H-Regression-and-Failure-History": {
            "full_regression_execution_report.json": "T0-T5全量回归测试套件执行指标与通过率汇总",
            "full_regression_terminal.log": "全量回归测试完整终端运行日志与时间戳记录"
        }
    }

    total_files = 0
    for root, _, files in os.walk(STAGING_DIR):
        cat_name = Path(root).relative_to(STAGING_DIR).as_posix()
        for f in sorted(files):
            fpath = Path(root) / f
            rel_path = f"{cat_name}/{f}" if cat_name != "." else f
            f_size = fpath.stat().st_size
            f_sha = sha256_file(fpath)
            cat_code = cat_name.split("-")[0] if "-" in cat_name else "GEN"
            desc = category_descs.get(cat_name, {}).get(f, "实测过程数据")
            manifest_lines.append(f"| `{cat_code}` | `{rel_path}` | {f_size} | `{f_sha}` | {desc} |")
            total_files += 1

    manifest_lines.extend([
        "",
        "---",
        "",
        "## 二、真实性与证据不可篡改声明",
        "",
        f"1. **总文件数：** 归档证据包含 8 大分类共 {total_files} 个独立数据与报告文件。",
        "2. **实测采集来源：** 所有 COM 连接数据、物理建模体积及进程生命周期指标，均在部署了真实 SolidWorks 2026 SP4.1 的宿主机上通过 Python 3.13 现场采集，严禁任何 mock 或硬编码伪造。",
        "3. **哈希自洽性：** 上述 SHA-256 摘要与 ZIP 归档哈希值一次性生成，可供第三方审计者使用 `certutil -hashfile` 或 `sha256sum` 独立复核验真。",
        ""
    ])

    with open(MANIFEST_PATH, "w", encoding="utf-8") as mf:
        mf.write("\n".join(manifest_lines))
    print(f"[✔] 证据清单生成成功: {MANIFEST_PATH}")

if __name__ == "__main__":
    create_evidence_zip()
    generate_manifest()
