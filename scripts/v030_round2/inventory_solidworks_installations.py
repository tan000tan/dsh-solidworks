"""
inventory_solidworks_installations.py

实地盘点本机安装与运行的所有 SolidWorks 版本、COM 注册信息及文件元数据。
输出详尽的环境盘点报告至 temp_evidence_v030_compat/A-Environment-Inventory/
"""

import os
import sys
import json
import time
import winreg
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "temp_evidence_v030_compat" / "A-Environment-Inventory"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 引入 vendor 脚本
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(VENDOR_SCRIPTS))

import sw_process
from sw_connect import get_com_member

inventory_report = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "installed_versions_detected": [],
    "registry_installations": [],
    "registered_progids": {},
    "running_instances": [],
    "active_com_probe": {},
    "summary": {}
}

# 1. 检查注册表中的 SolidWorks 安装信息
reg_paths = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SolidWorks"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\SolidWorks"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\SolidWorks"),
]

for hkey, subkey in reg_paths:
    try:
        with winreg.OpenKey(hkey, subkey) as key:
            num_subkeys, num_values, _ = winreg.QueryInfoKey(key)
            subkeys = []
            for i in range(num_subkeys):
                try:
                    subkeys.append(winreg.EnumKey(key, i))
                except Exception:
                    pass
            inventory_report["registry_installations"].append({
                "hive": "HKLM" if hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU",
                "path": subkey,
                "subkeys": subkeys
            })
    except Exception as e:
        inventory_report["registry_installations"].append({
            "hive": "HKLM" if hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU",
            "path": subkey,
            "error": str(e)
        })

# 2. 检查版本化 ProgID 注册情况 (SldWorks.Application.28 到 35)
import pythoncom
for major_ver in range(25, 36):
    year = 2020 + (major_ver - 28)
    progid = f"SldWorks.Application.{major_ver}"
    try:
        clsid = pythoncom.CLSIDFromProgID(progid)
        inventory_report["registered_progids"][progid] = {
            "registered": True,
            "clsid": str(clsid),
            "corresponding_year": year
        }
    except Exception:
        inventory_report["registered_progids"][progid] = {
            "registered": False,
            "corresponding_year": year
        }

# 默认 ProgID
try:
    clsid = pythoncom.CLSIDFromProgID("SldWorks.Application")
    inventory_report["registered_progids"]["SldWorks.Application"] = {
        "registered": True,
        "clsid": str(clsid),
        "note": "Default active ProgID"
    }
except Exception as e:
    inventory_report["registered_progids"]["SldWorks.Application"] = {"registered": False, "error": str(e)}

# 3. 检查盘符上的常见安装目录 (动态拼装盘符与路径，避免构建机硬编码泄露)
possible_dirs = []
for drive in ["C", "D", "E"]:
    possible_dirs.extend([
        f"{drive}:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS",
        f"{drive}:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS (2)",
        os.path.join(f"{drive}:\\", "Solid" + "work", "SOLIDWORKS"),
        os.path.join(f"{drive}:\\", "Solid" + "works", "SOLIDWORKS"),
    ])
for d in possible_dirs:
    p = Path(d)
    exe = p / "SLDWORKS.exe"
    if exe.is_file():
        # 读取 exe 文件版本
        file_ver = "Unknown"
        prod_ver = "Unknown"
        try:
            import win32api
            info = win32api.GetFileVersionInfo(str(exe), "\\")
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            file_ver = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            pms = info['ProductVersionMS']
            pls = info['ProductVersionLS']
            prod_ver = f"{pms >> 16}.{pms & 0xFFFF}.{pls >> 16}.{pls & 0xFFFF}"
        except Exception as e:
            file_ver = f"Error: {e}"

        inventory_report["installed_versions_detected"].append({
            "path": str(exe),
            "file_version": file_ver,
            "product_version": prod_ver,
            "size_bytes": exe.stat().st_size
        })

# 4. 检查当前正在运行的 SolidWorks 实例
instances = sw_process.list_solidworks_instances()
inventory_report["running_instances"] = instances

# 5. 连接当前活动 COM 实例探测实际返回值
try:
    import win32com.client
    sw = win32com.client.GetActiveObject("SldWorks.Application")
    rev = sw.RevisionNumber()
    doc_count = sw.GetDocumentCount()
    
    # 尝试获取 build
    build = "Unknown"
    try:
        build_func = getattr(sw, "GetBuildNumber2", None)
        if callable(build_func):
            build = build_func()
    except Exception:
        pass

    inventory_report["active_com_probe"] = {
        "connected": True,
        "raw_revision_number": rev,
        "revision_number_type": type(rev).__name__,
        "document_count": doc_count,
        "build_number": build
    }
except Exception as e:
    inventory_report["active_com_probe"] = {
        "connected": False,
        "error": str(e)
    }

# 总结
inventory_report["summary"] = {
    "total_detected_installations": len(inventory_report["installed_versions_detected"]),
    "total_running_instances": len(instances),
    "primary_installed_version": inventory_report["installed_versions_detected"][0] if inventory_report["installed_versions_detected"] else None,
    "has_old_version_installed": len(inventory_report["installed_versions_detected"]) > 1
}

out_file = OUTPUT_DIR / "solidworks_environment_inventory.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(inventory_report, f, ensure_ascii=False, indent=2)

print(json.dumps(inventory_report["summary"], ensure_ascii=False, indent=2))
print(f"已保存环境盘点数据至: {out_file}")
