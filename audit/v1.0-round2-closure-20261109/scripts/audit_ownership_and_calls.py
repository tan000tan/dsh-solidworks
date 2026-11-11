import ast
import os

server_path = r'D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\mcp-server\server.py'
with open(server_path, 'r', encoding='utf-8', errors='replace') as f:
    code = f.read()

tree = ast.parse(code, filename=server_path)
tools_info = []

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
            has_guard = any(g in func_code for g in ['_active_model_required', '_active_part_required', '_active_assembly_required', 'is_document_owned'])
            
            touches_sw = any(w in func_code for w in ['connect_solidworks', 'GetActiveDocument', 'ActiveDoc', 'GetOpenDocumentByName', 'sw.', 'model.', 'asm.', 'part.'])
            
            write_keywords = ['create', 'add', 'sketch', 'extrude', 'revolve', 'fillet', 'chamfer', 
                              'shell', 'pattern', 'mirror', 'save', 'close', 'mate', 'set', 
                              'update', 'modify', 'build', 'execute', 'delete', 'export']
            is_write = any(kw in func_name.lower() for kw in write_keywords)
            
            tools_info.append({
                'name': func_name,
                'line': node.lineno,
                'is_write': is_write,
                'touches_sw': touches_sw,
                'has_guard': has_guard,
                'calls_connect': 'connect_solidworks' in func_code
            })

all_touch_sw_write = [t for t in tools_info if t['is_write'] and t['touches_sw']]
unprotected_write = [t for t in all_touch_sw_write if not t['has_guard']]

print(f'Total tools: {len(tools_info)}')
print(f'Tools that touch SW and write: {len(all_touch_sw_write)}')
print(f'Unprotected SW write tools: {len(unprotected_write)}')
for t in unprotected_write:
    print(f"  Line {t['line']}: {t['name']}")
