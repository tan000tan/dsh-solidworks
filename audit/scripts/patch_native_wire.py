path = r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\scripts\sw_native_wire.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = """    if model is None or os.path.normcase(os.path.abspath(get(model,'GetPathName')))!=os.path.normcase(os.path.abspath(str(expected))):
        raise ValueError('Active document target mismatch')"""

replacement = """    if model is None or os.path.normcase(os.path.abspath(get(model,'GetPathName')))!=os.path.normcase(os.path.abspath(str(expected))):
        raise ValueError('Active document target mismatch')
    from scripts.sw_connect import is_document_owned, validate_path_against_allowed_roots
    if not validate_path_against_allowed_roots(str(expected)):
        raise PermissionError(f"Access denied: document path '{expected}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
    if not is_document_owned(model, path=str(expected)):
        raise PermissionError(f"DEF-SEC-01: Document '{expected}' is not owned by current automation session. Operation refused.")
    for val_key in ('spec_path', 'step_path', 'output_path', 'replacement_path'):
        if val_key in values and values[val_key]:
            vp = str(values[val_key])
            if not validate_path_against_allowed_roots(vp):
                raise PermissionError(f"Access denied: {val_key} '{vp}' is outside allowed roots (DSH_ALLOWED_ROOTS)")"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS: Enhanced sw_native_wire.py with ownership and sandbox boundaries!")
else:
    print("TARGET NOT MATCHED")
