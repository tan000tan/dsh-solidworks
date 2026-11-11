import json
import re
import ast
from pathlib import Path

plugin_root = Path(r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin")
dsh_plugin_path = plugin_root / "dsh-plugin.json"
server_path = plugin_root / "vendor" / "solidworks-automation-skill" / "mcp-server" / "server.py"

dsh_data = json.loads(dsh_plugin_path.read_text(encoding="utf-8"))
dsh_tools = {t["name"]: t for t in dsh_data.get("tools", [])}

server_text = server_path.read_text(encoding="utf-8")

# 提取 @mcp.tool(name="...")
tool_pattern = re.compile(r'@mcp\.tool\(\s*name=[\'"]([^\'"]+)[\'"]')
server_tools = set(tool_pattern.findall(server_text))

print(f"Total tools in dsh-plugin.json: {len(dsh_tools)}")
print(f"Total tools in server.py: {len(server_tools)}")

missing_in_server = set(dsh_tools.keys()) - server_tools
missing_in_dsh = server_tools - set(dsh_tools.keys())

print(f"Declared in dsh-plugin.json but missing in server.py: {missing_in_server}")
print(f"Registered in server.py but missing in dsh-plugin.json: {missing_in_dsh}")

# 逐一分析每个工具的函数定义与关键安全特征
# 解析 server.py 的 AST 寻找每个工具的函数体
tree = ast.parse(server_text)

tool_func_info = {}

for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        tool_name = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                func_name = getattr(dec.func, "attr", getattr(dec.func, "id", None))
                if func_name == "tool":
                    for kw in dec.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            tool_name = kw.value.value
                            break
        if tool_name:
            # 检查函数内部引用的安全检查函数
            func_source = ast.get_source_segment(server_text, node) or ""
            has_owned_check = any(w in func_source for w in [
                "_active_model_required",
                "_active_part_required",
                "_active_assembly_required",
                "validate_path_against_allowed_roots",
                "is_document_owned",
                "_load_automation_modules",
                "register_owned_document"
            ])
            is_read_only = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg == "annotations" and isinstance(kw.value, ast.Dict):
                            for k, v in zip(kw.value.keys, kw.value.values):
                                if isinstance(k, ast.Constant) and k.value == "readOnlyHint":
                                    if isinstance(v, ast.Constant):
                                        is_read_only = bool(v.value)
            
            tool_func_info[tool_name] = {
                "function_name": node.name,
                "readOnlyHint": is_read_only,
                "has_owned_check": has_owned_check,
                "body_lines": len(func_source.splitlines()),
                "source_snippet": func_source[:200].replace("\n", " ")
            }

print(f"\nParsed {len(tool_func_info)} tool function implementations.")

# 检查是否存在没有安全防护的变异工具
unprotected_mutators = []
for tname, info in tool_func_info.items():
    if not info["readOnlyHint"] and not info["has_owned_check"]:
        # 排除无需连接 CAD 的独立工具，如预检/本地格式验证
        if tname not in ["solidworks_health_check", "solidworks_design_spec_validate", "solidworks_drawing_validate_spec"]:
            unprotected_mutators.append(tname)

if unprotected_mutators:
    print(f"\n[WARNING] Found mutating tools without explicit ownership/sandbox check: {unprotected_mutators}")
else:
    print("\n[OK] All mutating tools enforce ownership check or sandbox validation!")

# 将全量审查结果写入 JSON 备用
out_report = {
    "total_dsh_tools": len(dsh_tools),
    "total_server_tools": len(server_tools),
    "missing_in_server": list(missing_in_server),
    "missing_in_dsh": list(missing_in_dsh),
    "tools_detail": tool_func_info
}
Path("audit_tools_result.json").write_text(json.dumps(out_report, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nWrote full tool capability audit to audit_tools_result.json")
