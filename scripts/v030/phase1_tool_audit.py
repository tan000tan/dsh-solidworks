import ast
import json
import os
import re
import sys
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PY = os.path.join(PLUGIN_ROOT, "vendor", "solidworks-automation-skill", "mcp-server", "server.py")
POLICY_JS = os.path.join(PLUGIN_ROOT, "lib", "policy.js")
RAW_DIR = os.path.join(PLUGIN_ROOT, "v0.3.0-phase1-6-delivery", "evidence_raw", "A-Audit")
os.makedirs(RAW_DIR, exist_ok=True)

def parse_risk_table(policy_path):
    with open(policy_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # match RISK_TABLE = Object.freeze({ ... });
    match = re.search(r"export\s+const\s+RISK_TABLE\s*=\s*Object\.freeze\(\{\s*(.*?)\s*\}\);", content, re.DOTALL)
    table = {}
    if match:
        block = match.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            m = re.match(r"([a-zA-Z0-9_]+)\s*:\s*([a-zA-Z0-9_]+)", line)
            if m:
                table[m.group(1)] = m.group(2).lower()
    return table

def parse_server_tools(server_py_path):
    with open(server_py_path, "r", encoding="utf-8") as f:
        code = f.read()
    
    tree = ast.parse(code, filename="server.py")
    lines = code.splitlines()
    
    tools = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_tool = False
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call):
                    func = deco.func
                    if (isinstance(func, ast.Attribute) and func.attr == "tool") or (isinstance(func, ast.Name) and func.id == "tool"):
                        is_tool = True
                elif (isinstance(deco, ast.Attribute) and deco.attr == "tool") or (isinstance(deco, ast.Name) and deco.id == "tool"):
                    is_tool = True
            
            if is_tool:
                doc = ast.get_docstring(node) or ""
                # extract parameter types and annotations if available
                args = []
                for a in node.args.args:
                    arg_name = a.arg
                    arg_type = ast.unparse(a.annotation) if a.annotation else "Any"
                    args.append({"name": arg_name, "type": arg_type})
                
                # Check implementation body for COM calls, mock calls, or external service calls
                func_code = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                
                has_com = bool(re.search(r"(Dispatch|win32com|swApp|swModel|GetActiveDoc|OpenDoc)", func_code, re.I))
                has_guard = bool(re.search(r"(_active_model_required|is_document_owned|validate_token|guard)", func_code, re.I))
                has_external_cli = bool(re.search(r"(subprocess|run_command|curl|http|requests)", func_code, re.I))
                returns_dummy = bool(re.search(r"return\s*\{['\"]status['\"]:\s*['\"]not_implemented['\"]\}", func_code, re.I))
                
                tools.append({
                    "name": node.name,
                    "file": "vendor/solidworks-automation-skill/mcp-server/server.py",
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "line_count": node.end_lineno - node.lineno + 1,
                    "args": args,
                    "doc": doc.strip(),
                    "has_com": has_com,
                    "has_guard": has_guard,
                    "has_external_cli": has_external_cli,
                    "returns_dummy": returns_dummy,
                    "code_sample": lines[node.lineno - 1].strip()
                })
    return tools

def main():
    start_time = time.time()
    risk_table = parse_risk_table(POLICY_JS)
    tools = parse_server_tools(SERVER_PY)
    
    print(f"Parsed {len(risk_table)} tools from policy.js RISK_TABLE.")
    print(f"Parsed {len(tools)} tools from server.py AST.")
    
    # Merge and cross-check
    inventory = []
    missing_in_policy = []
    missing_in_server = set(risk_table.keys())
    
    for t in tools:
        name = t["name"]
        risk = risk_table.get(name, "unknown")
        if name in missing_in_server:
            missing_in_server.remove(name)
        else:
            missing_in_policy.append(name)
        
        # Analyze operational state
        # state category:
        # 'real_com': implements COM call directly or via helper
        # 'analytical': pure python computational logic (dfm, math, bounding box)
        # 'external_service': calls backend REST/C# service
        # 'guard_only': defensive fallback / stub
        state_type = "analytical"
        if t["has_com"]:
            state_type = "real_com"
        elif t["has_external_cli"]:
            state_type = "external_or_subproc"
        elif t["returns_dummy"]:
            state_type = "stub"
        
        inventory.append({
            "name": name,
            "risk_tier": risk,
            "implementation_file": t["file"],
            "lines": f"{t['lineno']}-{t['end_lineno']} ({t['line_count']} lines)",
            "args": t["args"],
            "state_type": state_type,
            "has_guard": t["has_guard"],
            "summary": t["doc"].split("\n")[0] if t["doc"] else ""
        })
    
    inventory_out = {
        "audit_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tools": len(inventory),
        "policy_table_count": len(risk_table),
        "missing_in_policy": missing_in_policy,
        "missing_in_server": list(missing_in_server),
        "tools": inventory
    }
    
    out_file = os.path.join(RAW_DIR, "mcp_tool_inventory_66.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(inventory_out, f, indent=2, ensure_ascii=False)
    
    duration = time.time() - start_time
    print(f"MCP tool inventory completed in {duration:.3f}s. Saved to {out_file}")
    print(f"Missing in policy: {missing_in_policy}")
    print(f"Missing in server: {list(missing_in_server)}")

if __name__ == "__main__":
    main()
