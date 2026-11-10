# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_preflight.py
SolidWorks 真实环境端到端验证准备——只读环境预检查程序 (PRECHECK)。

设计原则：
1. 100% 只读探测，严禁执行任何几何创建、修改、保存或关闭操作；
2. 严禁获取或操作 ActiveDoc；
3. 检查并记录 SolidWorks 版本、STA 队列、COM 单元、Python 运行库与沙箱权限；
4. 为后续受控实机端到端验收提供清晰、确凿的就绪证明。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 确保 Windows 终端支持 utf-8 输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
MCP_SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
REAL_CAD_DIR = Path(__file__).resolve().parent

for p in (str(SCRIPTS_DIR), str(MCP_SERVER_DIR), str(REAL_CAD_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


class PreflightChecker:
    """环境预检查执行器。"""

    def __init__(self):
        self.results = {}
        self.all_passed = True
        self.warnings = []
        self.errors = []

    def log_check(self, name: str, success: bool, details: str = ""):
        self.results[name] = success
        tag = "[PASS]" if success else "[FAIL]"
        if not success:
            self.all_passed = False
            self.errors.append(f"{name}: {details}")
            print(f"{tag} {name}: {details}")
        else:
            print(f"{tag} {name}{': ' + details if details else ''}")

    def run_all(self):
        print("=" * 65)
        print("   SolidWorks 真实实机端到端验证前置只读检查 (PRECHECK)")
        print("=" * 65)

        # 1. 检查 Python 运行时与 COM 核心依赖
        try:
            import pythoncom
            import win32com.client
            import pydantic
            self.log_check("PYTHON_COM_LIBS", True, f"Python {sys.version.split()[0]}, pywin32, pydantic 已就绪")
        except Exception as e:
            self.log_check("PYTHON_COM_LIBS", False, str(e))

        # 2. 检查桌面与 STA Worker 交互权限
        try:
            from sw_connect import get_sta_worker, _is_default_desktop
            is_def = _is_default_desktop()
            worker = get_sta_worker()
            echo_val = worker.execute(lambda: 42, timeout=5.0)
            if echo_val == 42:
                self.log_check("STA_WORKER_DISPATCH", True, f"Default 交互桌面: {is_def}, STA 调度往返正常")
            else:
                self.log_check("STA_WORKER_DISPATCH", False, "STA echo 验证失败")
        except Exception as e:
            self.log_check("STA_WORKER_DISPATCH", False, f"STA Worker 调度异常: {e}")

        # 3. 检查 CAD 核心引擎模块导入
        try:
            from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
            from cad_graph_executor import CADGraphExecutor, ExecutionResult
            from cad_task_context import CADTaskContext, CADTaskRollbackManager, RollbackStatus
            from geometry_verifier import GeometryVerifier, GeometricExpectation
            self.log_check("CAD_MODULES_IMPORT", True, "CADGraphExecutor, FeatureGraphIR, RollbackManager 完整导入")
        except Exception as e:
            self.log_check("CAD_MODULES_IMPORT", False, f"导入核心模块失败: {e}")

        # 4. 检查 SolidWorks 本地运行状态与 COM 心跳（只读探测 RevisionNumber）
        sw_app = None
        try:
            from sw_connect import connect_solidworks, get_com_member
            sw_app, _ = connect_solidworks(wait_seconds=5, visible=None)
            if sw_app is not None:
                rev = get_com_member(sw_app, "RevisionNumber")
                pid = get_com_member(sw_app, "GetProcessID")
                self.log_check("SOLIDWORKS_LIVE_PROCESS", True, f"已连接运行中的 SolidWorks (PID={pid}, 版本修订号={rev})")
            else:
                self.log_check("SOLIDWORKS_LIVE_PROCESS", False, "未能连接到 SolidWorks COM 根对象")
        except Exception as e:
            self.log_check("SOLIDWORKS_LIVE_PROCESS", False, f"连接 SolidWorks 异常: {e}")

        # 5. 检查用户现有文档隔离（只读快照已打开文档）
        if sw_app is not None:
            try:
                from sw_connect import snapshot_open_documents
                docs = snapshot_open_documents(sw_app, strict=False)
                self.log_check("USER_DOCUMENTS_ISOLATION", True, f"已成功探测到用户现有打开文档 ({len(docs)} 个): {docs} (保护就绪)")
            except Exception as e:
                self.log_check("USER_DOCUMENTS_ISOLATION", False, f"探测文档快照异常: {e}")

        # 6. 检查零件模板定位能力（只读定位模板路径，不新建文档）
        if sw_app is not None:
            try:
                from sw_connect import find_template
                tpl = find_template(sw_app, "part")
                if tpl and os.path.exists(tpl):
                    self.log_check("PART_TEMPLATE_PATH", True, f"找到有效零件模板: {tpl}")
                else:
                    self.log_check("PART_TEMPLATE_PATH", False, f"零件模板不存在: {tpl}")
            except Exception as e:
                self.log_check("PART_TEMPLATE_PATH", False, f"查找模板异常: {e}")

        # 7. 检查沙箱物理目录存在性与写保护隔离
        sandbox_dir = REAL_CAD_DIR / "sandbox"
        try:
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            test_file = sandbox_dir / f".probe_test_{int(time.time()*1000)}.tmp"
            test_file.write_text("probe", encoding="utf-8")
            test_file.unlink()
            self.log_check("SANDBOX_DIRECTORY", True, f"沙箱目录就绪且可写: {sandbox_dir}")
        except Exception as e:
            self.log_check("SANDBOX_DIRECTORY", False, f"沙箱不可写: {e}")

        print("=" * 65)
        if self.all_passed:
            print("  [PRECHECK 全部通过] 当前实机环境完全具备开展受控实机验证的条件。")
            print("  【声明】：本次为纯只读预检查，未对用户 CAD 产生任何几何写入。")
        else:
            print("  [PRECHECK 存在未通过项] 请修复后再行测试。")
        print("=" * 65)

        return self.all_passed


if __name__ == "__main__":
    checker = PreflightChecker()
    success = checker.run_all()
    sys.exit(0 if success else 1)
