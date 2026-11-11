"""
audit_all_com_calls.py

全仓库扫描所有 SolidWorks COM API 调用点：
重点检索 FeatureExtrusion, FeatureCut, InsertMirror, MassProperty, Sketch,
Drawing, Assembly, Mate, Document Save/Open 相关接口。
输出审计表至 temp_evidence_v030_compat/B-API-Audit/
"""

import os
import re
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "temp_evidence_v030_compat" / "B-API-Audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DIRS = [
    REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts",
    REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server",
    REPO_ROOT / "lib",
]

API_PATTERNS = {
    "FeatureExtrusion": re.compile(r"\bFeatureExtrusion\d*\b"),
    "FeatureCut": re.compile(r"\bFeatureCut\d*\b"),
    "InsertMirrorFeature": re.compile(r"\bInsertMirrorFeature\d*\b"),
    "MassProperty": re.compile(r"\b(CreateMassProperty|GetMassProperties\d*)\b"),
    "SketchCreation": re.compile(r"\b(InsertSketch\d*|CreateCenterRectangle|CreateCircle\w*|CreateLine\w*)\b"),
    "DrawingView": re.compile(r"\b(CreateDrawView\w*|CreateUnfoldedView\w*|CreateFlatPatternView\w*)\b"),
    "AssemblyMate": re.compile(r"\b(AddMate\d*|CreateMate\w*)\b"),
    "FileSaveOpen": re.compile(r"\b(SaveAs\d*|OpenDoc\d*|CloseDoc|QuitDoc)\b"),
}

scan_results = {
    "total_files_scanned": 0,
    "api_call_sites": [],
    "summary_by_api": {},
    "bypass_candidates": []
}

for target_dir in TARGET_DIRS:
    for root, _, files in os.walk(target_dir):
        for file in files:
            if not file.endswith((".py", ".js", ".cs", ".ps1")):
                continue
            fpath = Path(root) / file
            rel_path = fpath.relative_to(REPO_ROOT).as_posix()
            scan_results["total_files_scanned"] += 1
            
            try:
                lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines, start=1):
                for category, pattern in API_PATTERNS.items():
                    matches = pattern.findall(line)
                    for m in matches:
                        # 排除注释行和定义行
                        stripped = line.strip()
                        if stripped.startswith(("#", "//", "/*", "*", "def ", "class ")):
                            continue
                        call_info = {
                            "category": category,
                            "api_name": m,
                            "file": rel_path,
                            "line": idx,
                            "code_snippet": stripped[:120]
                        }
                        scan_results["api_call_sites"].append(call_info)
                        scan_results["summary_by_api"][m] = scan_results["summary_by_api"].get(m, 0) + 1
                        
                        # 检查是否绕过了 sw_compat
                        if category in ["FeatureExtrusion", "FeatureCut", "InsertMirrorFeature", "MassProperty"]:
                            if "sw_compat" not in rel_path and "safe_" not in stripped:
                                scan_results["bypass_candidates"].append(call_info)

out_file = OUTPUT_DIR / "com_api_call_audit.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(scan_results, f, ensure_ascii=False, indent=2)

print(f"扫描了 {scan_results['total_files_scanned']} 个文件，发现 {len(scan_results['api_call_sites'])} 处 API 调用。")
print(f"潜在绕过兼容层的高版本调用: {len(scan_results['bypass_candidates'])} 处。")
print("API 汇总分布:", scan_results["summary_by_api"])
