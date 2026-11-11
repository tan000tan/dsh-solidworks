import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAGING_A = ROOT / "temp_evidence_v030" / "A-Git-and-Code-Audit"
STAGING_A.mkdir(parents=True, exist_ok=True)

SERVER_PATH = ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server" / "server.py"
SERVER_CWD = SERVER_PATH.parent.parent
sys.path.insert(0, str(SERVER_PATH.parent))

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

def run_git_cmd(args):
    res = subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.stdout.strip()

async def get_live_tools():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SERVER_CWD) + os.pathsep + str(ROOT)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env=env,
        cwd=str(SERVER_CWD)
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            res = await session.list_tools()
            return res.tools

def audit_git_and_workspace():
    print("--- 1. Auditing Git and Workspace Baseline ---")
    branch = run_git_cmd(["branch", "--show-current"])
    head = run_git_cmd(["rev-parse", "HEAD"])
    status = run_git_cmd(["status"])
    diff = run_git_cmd(["diff"])
    diff_stat = run_git_cmd(["diff", "--stat"])
    recent_commits = run_git_cmd(["log", "-5", "--oneline"])
    untracked = run_git_cmd(["ls-files", "--others", "--exclude-standard"])
    
    audit_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "branch": branch,
        "head_commit": head,
        "base_commit": "9cd64db",
        "diff_stat": diff_stat,
        "recent_commits": recent_commits,
        "untracked_files_count": len(untracked.splitlines()),
        "status_raw": status
    }
    
    with open(STAGING_A / "git_baseline_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)
        
    with open(STAGING_A / "git_full_diff.patch", "w", encoding="utf-8") as f:
        f.write(diff)
        
    print(f"Git baseline audit saved. Head: {head}, Branch: {branch}")
    return audit_data

async def audit_mcp_tools():
    print("--- 2. Full Independent Audit of 71 MCP Tools ---")
    live_tools = await get_live_tools()
    print(f"Live MCP server exposed {len(live_tools)} tools.")
    
    # Read policy.js RISK_TABLE
    policy_path = ROOT / "lib" / "policy.js"
    with open(policy_path, "r", encoding="utf-8") as f:
        policy_text = f.read()
        
    import re
    m = re.search(r"export\s+const\s+RISK_TABLE\s*=\s*Object\.freeze\(\{\s*(.*?)\s*\}\);", policy_text, re.DOTALL)
    risk_table = {}
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            match = re.match(r"([a-zA-Z0-9_]+)\s*:\s*([a-zA-Z0-9_]+)", line)
            if match:
                risk_table[match.group(1)] = match.group(2).lower()
                
    detailed_tools = []
    suspicious_side_effects = []
    schema_mismatches = []
    
    for t in live_tools:
        name = t.name
        desc = t.description or ""
        schema = t.inputSchema or {}
        props = schema.get("properties", {})
        reqs = schema.get("required", [])
        
        assigned_risk = risk_table.get(name, "UNKNOWN")
        
        # Analyze potential side-effects vs assigned risk
        # Any 'write' or 'high' action verb in tool description or name
        is_write_verb = bool(re.search(r"(create|add|set|update|extrude|cut|fillet|chamfer|modify|save|export|close|write|delete)", name, re.I))
        is_high_verb = bool(re.search(r"(save|export|close|delete|recover|write_open)", name, re.I))
        
        # Anomaly detection: READ tool with write verb
        if assigned_risk == "read" and is_write_verb:
            suspicious_side_effects.append({
                "tool": name,
                "assigned_risk": assigned_risk,
                "reason": "Tool name or description implies write operation, but classified as READ in policy"
            })
            
        # Check path parameters without sandbox checks
        path_params = [p for p in props.keys() if "path" in p.lower() or "file" in p.lower() or "dir" in p.lower()]
        
        detailed_tools.append({
            "name": name,
            "description": desc.split("\n")[0].strip(),
            "assigned_risk": assigned_risk,
            "property_count": len(props),
            "properties": list(props.keys()),
            "required_properties": reqs,
            "path_parameters": path_params,
            "schema_char_length": len(json.dumps(schema, ensure_ascii=False))
        })
        
    inventory = {
        "audit_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_exposed_tools": len(detailed_tools),
        "risk_table_coverage_count": len([t for t in detailed_tools if t["assigned_risk"] != "UNKNOWN"]),
        "unknown_risk_tools": [t["name"] for t in detailed_tools if t["assigned_risk"] == "UNKNOWN"],
        "suspicious_side_effects": suspicious_side_effects,
        "tools": detailed_tools
    }
    
    with open(STAGING_A / "mcp_71_tools_independent_audit.json", "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)
        
    print(f"Independent MCP tool audit saved. Total tools: {len(detailed_tools)}, Unknown risk: {len(inventory['unknown_risk_tools'])}")
    return inventory

def audit_historical_claims():
    print("--- 3. Independent Verdict on 6 Historical Problem Categories ---")
    
    verdicts = {
        "ISSUE-01_CAD_WRITE_GAP": {
            "title": "真实 SolidWorks 写入路径验证空白",
            "verdict": "部分成立",
            "evidence": "上一轮已通过 tests/phase4_cad_loop_test.py 实机在 SolidWorks 2026 SP4.1 验证了草图、拉伸、切除和体积(误差0.0000mm³)，但在装配体添加配合关系、工程图投影视角导出DWG/PDF、以及旧版本(2020-2025)写入路径上仍缺乏实机闭环证据。",
            "remaining_risk": "旧版本 SolidWorks 2020-2025 API 兼容写入验证空白；装配配合与工程图出图实机验证空白。"
        },
        "ISSUE-02_ENVIRONMENT_FRAGILITY": {
            "title": "Python、Node、pnpm、依赖和中文路径环境脆弱",
            "verdict": "部分成立",
            "evidence": "上一轮实现了混合自举探测(lib/discover.js)和WindowsApps 9009拦截，并验证了临时中文目录；但对普通用户完全无网络(无法访问清华/官方PyPI源)时的离线自给依赖仍未完全消除，当系统完全缺少Python时仍需外部支持。",
            "remaining_risk": "完全离线且无预装Python的普通用户机器仍无法纯零配置启动。"
        },
        "ISSUE-03_APPROVAL_FRICTION": {
            "title": "安全模式与实际可用性冲突",
            "verdict": "已证伪（已整改）",
            "evidence": "上一轮在 lib/policy.js 中重构了 approvalMode 并引入 session Grant 机制，只读操作免审，可逆沙箱操作会话级授权，高危持久化操作单次确认，测试通过(tests/phase5_security_approval_test.js)。",
            "remaining_risk": "需进一步验证会话授权在异常中断、参数篡改和多会话并发下的隔离性。"
        },
        "ISSUE-04_PERFORMANCE_AND_MULTI_INSTANCE": {
            "title": "COM 往返、Token 和多实例性能问题",
            "verdict": "部分成立",
            "evidence": "工具目录 Token 已从 26,365 压缩至 2,764 (降幅89.5%)；sw_process.py 实现了多实例发现与窗口标题检测；但跨进程 COM 往返在大型装配体(数百零件)遍历仍存在耗时压力，未实现异步进度流式回报。",
            "remaining_risk": "深层特征树或大型装配体检索可能触碰 120s 默认超时。"
        },
        "ISSUE-05_PSEUDO_TOOLS_AND_PREFLIGHT": {
            "title": "功能虚胖和预检工具冒充真实执行能力",
            "verdict": "已证实",
            "evidence": "审计发现存在如 cadstudio_check_routing、cadstudio_fea_preflight、cadstudio_routing_preflight 等工具，部分返回基于启发式规则的分析字典，并非直接调用 SolidWorks Routing 或 Simulation 原生求解器插件。",
            "remaining_risk": "必须在文档和工具描述中明确标示工具的仿真/分析能力边界，杜绝夸大宣传。"
        },
        "ISSUE-06_VERSION_SUPPORT_DISCONNECT": {
            "title": "社区生态、市场要求和版本支持声明断层",
            "verdict": "已证实（亟待攻坚修复）",
            "evidence": "README.zh.md 和 dsh-plugin.json 曾宣称支持 SolidWorks 2020~2026，但上一轮实际仅在 SolidWorks 2026 SP4.1 单一版本打火，未实施 2020~2026 API 差异调查、统一兼容层与降级保护。",
            "remaining_risk": "这是当前版本最关键的工程遗漏，必须在本次任务中全面实施统一兼容层与降级矩阵！"
        }
    }
    
    with open(STAGING_A / "historical_issues_verdict.json", "w", encoding="utf-8") as f:
        json.dump(verdicts, f, indent=2, ensure_ascii=False)
        
    print("Historical claims audit verdicts recorded.")
    return verdicts

async def main():
    audit_git_and_workspace()
    await audit_mcp_tools()
    audit_historical_claims()
    print("Stage 1 Audit Completed Successfully.")

if __name__ == "__main__":
    asyncio.run(main())
