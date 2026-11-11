"""
scripts/v030_round2/sanitize_build_machine_paths.py

清理待发布文件中的构建机特定物理绝对路径：
将包含 D:\\Agent工作区, C:\\Users\\Khalil, D:\\SWCAD-MCP 等开发机绝对路径
泛化为相对路径或标准占位符，消除机器路径泄露并使 package.test.js 彻底通过。
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 扫描目标目录
TARGET_DIRS = ["scripts", "tests", "docs", "lib", "bin"]
ROOT_FILES = [
    "README.md", "README.zh.md", "CHANGELOG.md", "PROVENANCE.md",
    "package.json", "dsh-plugin.json", "cordis.patch.yml",
    "requirements.txt", "requirements-optional.txt", "NOTICE"
]

NEEDLES = [
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<PROJECT_ROOT>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<PROJECT_ROOT>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<WORKSPACE_ROOT>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<WORKSPACE_ROOT>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<USER_HOME>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<USER_HOME>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<SWCAD_MCP_ROOT>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<SWCAD_MCP_ROOT>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<DSH_SW_TEST>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<DSH_SW_TEST>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<SOLIDWORKS_INSTALL_DIR>"),
    (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<SOLIDWORKS_INSTALL_DIR>"),
]

def sanitize_file(p: Path):
    # 跳过 temp_evidence_v030、audit_round2_final 等证据与交付物归档目录
    rel = p.relative_to(REPO_ROOT).as_posix()
    if any(rel.startswith(skip) for skip in ["temp_evidence_v030", "audit_round2_final", "v0.3.0", "vendor", ".git"]):
        return

    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return

    modified = False
    for needle, replacement in NEEDLES:
        if needle in content:
            # 针对 Python 脚本中的 BASE_DIR 或 AUDIT_DIR 专门做代码级优雅替换
            if p.suffix == ".py":
                if f'r"{needle}' in content:
                    content = content.replace(f'r"{needle}\\audit_round2_final"', 'os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit_round2_final")')
                    content = content.replace(f'r"{needle}"', 'os.path.dirname(os.path.dirname(os.path.abspath(__file__)))')
                    content = content.replace(f'"{needle}"', 'os.path.dirname(os.path.dirname(os.path.abspath(__file__)))')
            content = content.replace(needle, replacement)
            modified = True

    if modified:
        p.write_text(content, encoding="utf-8")
        print(f"[Sanitized] {rel}")

def main():
    for rf in ROOT_FILES:
        fp = REPO_ROOT / rf
        if fp.is_file():
            sanitize_file(fp)

    for d in TARGET_DIRS:
        dp = REPO_ROOT / d
        if dp.is_dir():
            for root, _, files in os.walk(dp):
                for f in files:
                    sanitize_file(Path(root) / f)

if __name__ == "__main__":
    main()
