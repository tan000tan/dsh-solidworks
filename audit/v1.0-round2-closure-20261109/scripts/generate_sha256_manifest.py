import os
import hashlib
from pathlib import Path

plugin_root = Path(r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin")
output_manifest = plugin_root / "audit" / "v1.0-round2-closure-20261109" / "SHA256_MANIFEST.txt"

def get_sha256(filepath):
    p = Path(filepath)
    if not p.is_absolute():
        p = plugin_root / p
    if not p.exists():
        return None, 0
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), p.stat().st_size

files_to_hash = [
    # 核心元数据与配置
    "package.json",
    "cordis.patch.yml",
    "dsh-plugin.json",
    "LICENSE",
    "NOTICE",
    "PROVENANCE.md",
    "README.md",
    "README.zh.md",
    "CHANGELOG.md",
    "requirements.txt",
    "requirements-optional.txt",

    # CLI 与入口
    "bin/dsh-solidworks.js",
    "lib/index.js",
    "lib/policy.js",
    "lib/mcp.js",
    "lib/discover.js",
    "lib/schema.js",

    # MCP 适配器与核心服务端
    "mcp-server-solidworks-main/adapters/dsh/server.py",
    "mcp-server-solidworks-main/adapters/claude/server.py",
    "vendor/solidworks-automation-skill/mcp-server/server.py",
    "vendor/solidworks-automation-skill/scripts/sw_export.py",
    "vendor/solidworks-automation-skill/scripts/sw_connect.py",
    "vendor/solidworks-automation-skill/scripts/sw_assembly.py",
    "vendor/solidworks-automation-skill/scripts/sw_drawing.py",
    "vendor/solidworks-automation-skill/scripts/sw_part.py",
    "vendor/solidworks-automation-skill/scripts/sw_pattern.py",
    "vendor/solidworks-automation-skill/scripts/cad_task_context.py",

    # 关键测试脚本
    "tests/real_cad/run_v10_rework_e2e.py",
    "tests/policy.test.js",
    "tests/package.test.js",
    "tests/mcp.test.js",

    # 实机物理交付模型产物 (cad_e2e_sandbox)
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_stepped_shaft.SLDPRT",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_stepped_shaft.STL",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_base.SLDPRT",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_gear.SLDPRT",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_assembly.SLDASM",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_assembly.step",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_drawing.SLDDRW",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_drawing.pdf",
    "audit/v1.0-final-release/cad_e2e_sandbox/v10_rework_e2e_summary.json",

    # 第二轮闭环审计证据物证
    "audit/v1.0-round2-closure-20261109/GIT_HEAD.txt",
    "audit/v1.0-round2-closure-20261109/FULL_WORKING_DIFF.patch",
    "audit/v1.0-round2-closure-20261109/PID_LIFECYCLE_AUDIT.json",
    "audit/v1.0-round2-closure-20261109/RESTORE_VERIFICATION_REPORT.txt",
    "audit/v1.0-round2-closure-20261109/HISTORICAL_REQUIREMENTS_FULL_AUDIT.md",
    "audit/v1.0-round2-closure-20261109/ALL_70_TESTS_EXECUTION_MATRIX.md",
    "audit/v1.0-round2-closure-20261109/logs/e2e_solidworks_raw_round2.log",

    # 发布安装包
    "dsh-solidworks-0.2.0.tgz"
]

lines = [
    "# dsh-solidworks v1.0 全量关键资产不可篡改 SHA-256 指纹清单",
    f"# 生成时间: {os.popen('date /t').read().strip() if os.name == 'nt' else ''}",
    "# 基线 Commit: 7d70bc090d5cef146ac3946bb062667ae30a4cc9",
    "# --------------------------------------------------------------------------------",
    "# SHA256 校验哈希                                                   大小(字节)   相对路径",
    "# --------------------------------------------------------------------------------"
]

for rel_path in files_to_hash:
    sha, size = get_sha256(rel_path)
    if sha:
        lines.append(f"{sha}  {size:10d}  {rel_path}")
    else:
        lines.append(f"MISSING                                                           0  {rel_path}")

with open(output_manifest, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Generated manifest with {len(lines)-6} assets at {output_manifest}")
