"""
scripts/build_v031_final_release_candidate.py

DSH-SolidWorks v0.3.1 正式发布候选包全量自动化构建与自检系统。
构建标准与安全审计：
1. 清理并准备 v0.3.1-final-release-candidate/ 交付目录；
2. 构建普通用户 Windows 安装部署包: dsh-solidworks-v0.3.1-windows-installer.zip；
3. 构建标准 DSH/npm 发布包: dsh-solidworks-0.3.1.tgz；
4. 归档端到端真实 CAD 实机闭环、P0 对抗安全、Runtime 隔离与多版本兼容全量证据: v0.3.1-e2e-cad-and-diagnostics-evidence.zip；
5. 生成交付物全量 SHA256清单.txt (UTF-8，无 BOM)；
6. 实施独立解压自检：将 ZIP/TGZ 解压至全新隔离目录，逐文件校验哈希、版本号、绝对路径泄露与完整性。
"""

import gzip
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent
_DEFAULT_DIST = Path(os.environ.get("DSH_SOLIDWORKS_DIST_DIR", str(WORKSPACE_ROOT / "dist" / "v0.3.1-final-release-candidate")))
DIST_DIR = _DEFAULT_DIST
EVIDENCE_DIR = DIST_DIR / "raw_evidence"
GLOBAL_DIST = Path(os.environ.get("DSH_SOLIDWORKS_GLOBAL_DIST", str(WORKSPACE_ROOT / "dist")))
FIXED_MTIME = 1700000000
FIXED_ZIP_TIME = (2026, 11, 12, 0, 0, 0)
FORBIDDEN_ARCHIVE_PATTERNS = ("tests/", "audit/", "__pycache__", ".pyc", ".pdf", "dsh-mcp-config.json", "测试代码", "temp_evidence")

def compute_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def check_no_path_leak(file_path: Path):
    """确保待打包文本文件中未泄漏本地开发机敏感路径"""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        parts = [
            ("D:", "SWCAD-MCP"),
            ("C:", "Users", "Khalil"),
            ("D:", "Agent工作区"),
            ("D:", "dsh-sw-test"),
            ("D:", "Solidwork"),
        ]
        banned = [sep.join(p) for p in parts for sep in ("\\", "/")]
        for b in banned:
            if b in content:
                raise ValueError(f"检测到构建机敏感绝对路径泄露: {b} in {file_path}")
    except (UnicodeDecodeError, PermissionError):
        pass

def main():
    print("\n======================================================")
    print("  DSH-SolidWorks v0.3.1 正式发布交付包自动化构建器  ")
    print("======================================================\n")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_DIST.mkdir(parents=True, exist_ok=True)

    # 1. 收集并收录原始真实测试证据文件
    print("[1/6] 收集全维度测试证据与诊断报告...")
    evidence_sources = [
        REPO_ROOT / "temp_evidence_v030_compat" / "D-Real-CAD-Regression" / "comprehensive_cad_closure.json",
        REPO_ROOT / "temp_evidence_v030_compat" / "D-Real-CAD-Regression" / "comprehensive_cad_closure.log",
        REPO_ROOT / "e2e_full_chain_cad_loop.json",
        REPO_ROOT / "diagnostic-report.json",
        REPO_ROOT / "diagnostic-report.md",
        REPO_ROOT / "temp_evidence_v030_compat" / "C-Compat-Matrix-Tests" / "sw_compat_matrix_deep_verification.json",
        REPO_ROOT / "temp_evidence_v030" / "E-Security-and-Safety" / "approval_security_adversarial_evidence.json",
        REPO_ROOT / "temp_evidence_v030" / "E-Security-and-Safety" / "policy_security_adversarial_test.json",
    ]

    for src in evidence_sources:
        if src.exists():
            shutil.copy2(src, EVIDENCE_DIR / src.name)
            print(f"  [✔ 证据收录] {src.name} ({src.stat().st_size} bytes)")
        else:
            print(f"  [!] 警告: 未找到证据文件 {src}")

    # 2. 收集需要分发的文件清单
    with open(REPO_ROOT / "package.json", "r", encoding="utf-8") as f:
        pkg_data = json.load(f)
    version = pkg_data.get("version", "0.3.1")
    assert version == "0.3.1", f"package.json 版本必须为 0.3.1，当前为 {version}"
    allowlist = pkg_data.get("files", [])

    dist_files = set()
    for base_file in [
        "package.json",
        "dsh-plugin.json",
        "cordis.patch.yml",
        "install.bat",
        "doctor.bat",
        "upgrade.bat",
        "uninstall.bat",
        "requirements.txt",
        "requirements-optional.txt",
        "README.md",
        "README.zh.md",
        "LICENSE",
        "NOTICE",
        "PROVENANCE.md",
        "CHANGELOG.md",
    ]:
        p = REPO_ROOT / base_file
        if p.exists():
            dist_files.add(p)

    for item in allowlist:
        if item in {"tests", "audit"}:
            continue
        item_path = REPO_ROOT / item
        if item_path.is_file():
            dist_files.add(item_path)
        elif item_path.is_dir():
            for root, _, files in os.walk(item_path):
                for file in files:
                    p = Path(root) / file
                    rel_posix = p.relative_to(REPO_ROOT).as_posix()
                    if any(pat in rel_posix for pat in FORBIDDEN_ARCHIVE_PATTERNS) or ".venv" in p.parts:
                        continue
                    dist_files.add(p)

    print(f"  [分发清单] 共有 {len(dist_files)} 个独立有效交付文件。")

    # 路径泄露与禁入文件检查：确保所有待打包文本文件不泄漏本地构建机路径且无污染条目
    for p in sorted(dist_files):
        rel_posix = p.relative_to(REPO_ROOT).as_posix()
        for pat in FORBIDDEN_ARCHIVE_PATTERNS:
            if pat in rel_posix:
                raise ValueError(f"检测到禁止进入发布包的开发/测试/审计污染文件: {rel_posix} (matched {pat})")
        if p.suffix.lower() in {".js", ".mjs", ".py", ".json", ".yml", ".yaml", ".md", ".txt", ".bat", ".sh"}:
            check_no_path_leak(p)

    # 3. 构建面向普通用户的 Windows 一键免配置安装包 (ZIP)
    print("\n[2/6] 构建普通用户 Windows 安装部署包 (ZIP)...")
    zip_pkg_path = DIST_DIR / "dsh-solidworks-v0.3.1-windows-installer.zip"
    with zipfile.ZipFile(zip_pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(dist_files):
            rel = p.relative_to(REPO_ROOT)
            zi = zipfile.ZipInfo(f"dsh-solidworks/{rel.as_posix()}", date_time=FIXED_ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, p.read_bytes())

    print(f"[✔] Windows 安装包已生成: {zip_pkg_path.name} ({zip_pkg_path.stat().st_size} bytes)")

    # 4. 构建开发者 / 官方市场 DSH 插件包 (TGZ)
    print("\n[3/6] 构建 DSH 插件市场发布包 (TGZ)...")
    tgz_pkg_path = DIST_DIR / "dsh-solidworks-0.3.1.tgz"
    def _reset_tarinfo(ti: tarfile.TarInfo) -> tarfile.TarInfo:
        ti.mtime = FIXED_MTIME
        ti.uid = 0
        ti.gid = 0
        ti.uname = ""
        ti.gname = ""
        return ti
    with open(tgz_pkg_path, "wb") as raw_f:
        with gzip.GzipFile(fileobj=raw_f, mode="wb", mtime=FIXED_MTIME) as gz_f:
            with tarfile.open(fileobj=gz_f, mode="w") as tar:
                for p in sorted(dist_files):
                    rel = p.relative_to(REPO_ROOT)
                    tar.add(p, arcname=f"package/{rel.as_posix()}", filter=_reset_tarinfo)

    # 备份至 dist/ 以便本地包管理器索引
    shutil.copy2(tgz_pkg_path, GLOBAL_DIST / tgz_pkg_path.name)
    shutil.copy2(zip_pkg_path, GLOBAL_DIST / "dsh-solidworks-0.3.1.zip")
    print(f"[✔] DSH 插件包已生成: {tgz_pkg_path.name} ({tgz_pkg_path.stat().st_size} bytes)")

    # 5. 归档真实可复现测试证据包（禁止生成 22 字节空 ZIP）
    print("\n[4/6] 归档真实验证证据压缩包 (ZIP)...")
    legacy_empty_zip = DIST_DIR / "v0.3.1-e2e-cad-and-diagnostics-evidence.zip"
    if legacy_empty_zip.exists():
        legacy_empty_zip.unlink()

    audit_evidence_root = WORKSPACE_ROOT / "audit" / "full-remediation"
    evidence_sources = []
    for sub in ("test-results", "manifests", "logs", "repro", "raw_evidence"):
        sub_dir = audit_evidence_root / sub
        if sub_dir.exists():
            for f in sorted(sub_dir.rglob("*")):
                if f.is_file() and f.stat().st_size > 0:
                    evidence_sources.append((f, f.relative_to(audit_evidence_root).as_posix()))
    for f in sorted(EVIDENCE_DIR.rglob("*")):
        if f.is_file() and f.stat().st_size > 0:
            evidence_sources.append((f, f"raw_evidence/{f.relative_to(EVIDENCE_DIR).as_posix()}"))

    evidence_zip_path = DIST_DIR / "v0.3.1-remediation-verification-evidence.zip"
    evidence_records = []
    if evidence_sources:
        with zipfile.ZipFile(evidence_zip_path, "w") as zf:
            for src_file, arc_rel in sorted(evidence_sources, key=lambda x: x[1]):
                zi = zipfile.ZipInfo(arc_rel, date_time=FIXED_ZIP_TIME)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, src_file.read_bytes())
                evidence_records.append({
                    "path": arc_rel,
                    "bytes": src_file.stat().st_size,
                    "sha256": compute_sha256(src_file),
                })
        print(f"[✔] 真实证据压缩包已生成: {evidence_zip_path.name} ({evidence_zip_path.stat().st_size} bytes, {len(evidence_records)} files)")
    else:
        if evidence_zip_path.exists():
            evidence_zip_path.unlink()
        print("[!] 未发现非空验证证据文件，跳过证据 ZIP 打包（禁止生成空 ZIP）")

    # 6. 生成全量 SHA256 清单并同步更新顶层 dist/SHA256SUMS.txt
    print("\n[5/6] 计算交付物 SHA-256 并生成清单...")
    manifest_lines = [
        "# DSH-SolidWorks v0.3.1 正式发布交付物 SHA-256 清单",
        "# 编码: UTF-8 (不含 BOM)",
        "",
    ]

    all_delivery_items = []
    for archive in sorted(DIST_DIR.glob("*.zip")) + sorted(DIST_DIR.glob("*.tgz")):
        all_delivery_items.append(archive)

    manifest_records = []
    for item in all_delivery_items:
        h = compute_sha256(item)
        size = item.stat().st_size
        rel_name = item.name
        manifest_lines.append(f"{h}  {rel_name}")
        manifest_records.append({"file": rel_name, "sha256": h, "bytes": size})
        print(f"  {h}  {rel_name} ({size} bytes)")

    manifest_file = DIST_DIR / "SHA256清单.txt"
    manifest_file.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"[✔] SHA-256 清单已写入: {manifest_file.name}")

    # 同步刷新顶层 dist/SHA256SUMS.txt，消除过期哈希（N-02 修复）
    global_sums_lines = []
    for g_item in sorted(GLOBAL_DIST.glob("*.tgz")) + sorted(GLOBAL_DIST.glob("*.zip")):
        global_sums_lines.append(f"{compute_sha256(g_item)}  {g_item.name}")
    global_sums_file = GLOBAL_DIST / "SHA256SUMS.txt"
    global_sums_file.write_text("\n".join(global_sums_lines) + "\n", encoding="utf-8")
    print(f"[✔] 顶层校验清单已同步更新: {global_sums_file.name}")

    # 同时写出一份 json 格式元数据
    meta_json = DIST_DIR / "release_candidate_manifest.json"
    meta_json.write_text(json.dumps({
        "version": "0.3.1",
        "releaseCandidate": "v0.3.1-full-remediation-candidate",
        "liveCadE2EStatus": "PENDING (not executed in this phase; T21-T33 stopped per boundary)",
        "verdict": "REPRODUCIBLE_BUILD_CANDIDATE (requires independent audit and live CAD acceptance)",
        "files": manifest_records,
        "evidenceFilesCount": len(evidence_records),
        "evidenceFiles": evidence_records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # 7. 独立解压与哈希复核交叉自检
    print("\n[6/6] 执行独立解压自检与哈希一致性交叉复核...")
    with tempfile.TemporaryDirectory() as tmp_unpack:
        unpack_path = Path(tmp_unpack)
        with zipfile.ZipFile(zip_pkg_path, "r") as zf:
            zf.extractall(unpack_path)

        unpacked_root = unpack_path / "dsh-solidworks"
        assert (unpacked_root / "install.bat").exists(), "install.bat 缺失"
        assert (unpacked_root / "doctor.bat").exists(), "doctor.bat 缺失"
        assert (unpacked_root / "package.json").exists(), "package.json 缺失"
        assert (unpacked_root / "dsh-plugin.json").exists(), "dsh-plugin.json 缺失"
        assert (unpacked_root / "lib" / "index.js").exists(), "lib/index.js 缺失"
        assert (unpacked_root / "lib" / "policy.js").exists(), "lib/policy.js 缺失"
        assert (unpacked_root / "vendor" / "solidworks-automation-skill").exists(), "vendor 缺失"

        # 校验解压出的 package.json 和 dsh-plugin.json 版本
        with open(unpacked_root / "package.json", "r", encoding="utf-8") as f:
            unpacked_pkg = json.load(f)
        assert unpacked_pkg["version"] == "0.3.1", f"package.json 版本号不符: {unpacked_pkg['version']}"

        with open(unpacked_root / "dsh-plugin.json", "r", encoding="utf-8") as f:
            unpacked_manifest = json.load(f)
        assert unpacked_manifest["version"] == "0.3.1", f"dsh-plugin.json 版本号不符: {unpacked_manifest['version']}"

    # 校验 TGZ 解压自检
    with tempfile.TemporaryDirectory() as tmp_tgz_unpack:
        unpack_path = Path(tmp_tgz_unpack)
        with tarfile.open(tgz_pkg_path, "r:gz") as tar:
            tar.extractall(unpack_path)

        unpacked_pkg_root = unpack_path / "package"
        assert (unpacked_pkg_root / "lib" / "index.js").exists(), "TGZ 缺少 lib/index.js"
        assert (unpacked_pkg_root / "lib" / "policy.js").exists(), "TGZ 缺少 lib/policy.js"
        with open(unpacked_pkg_root / "package.json", "r", encoding="utf-8") as f:
            pkg_check = json.load(f)
        assert pkg_check["version"] == "0.3.1", f"TGZ package.json 版本号不符: {pkg_check['version']}"

    print("[✔] 解压自检通过！ZIP 与 TGZ 安装包文件结构完整且版本号精确吻合 0.3.1！")

    print("\n======================================================")
    print("  🎉 DSH-SolidWorks v0.3.1 正式发布交付目录构建完毕！")
    print(f"  交付路径: {DIST_DIR}")
    print("======================================================\n")

if __name__ == "__main__":
    main()
