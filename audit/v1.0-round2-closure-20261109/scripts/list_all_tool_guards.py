import ast
import os

server_path = r'D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\mcp-server\server.py'
with open(server_path, 'r', encoding='utf-8', errors='replace') as f:
    code = f.read()

tree = ast.parse(code, filename=server_path)
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        is_tool = False
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and getattr(dec.func, 'attr', '') == 'tool') or \
               (isinstance(dec, ast.Attribute) and dec.attr == 'tool'):
                is_tool = True
                break
        if is_tool:
            func_name = node.name
            func_code = ast.get_source_segment(code, node) or ''
            guards = []
            for g in ['_active_model_required', '_active_part_required', '_active_assembly_required', 'is_document_owned', 'validate_path']:
                if g in func_code:
                    guards.append(g)
            print(f"{node.lineno:4d} | {func_name:<40} | guards: {', '.join(guards) if guards else 'NONE'}")
