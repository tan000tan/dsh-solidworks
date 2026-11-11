p = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\scripts\sw_export.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

target1 = "    output_root = Path(os.path.expandvars(str(output_dir))).expanduser().resolve()\n    output_root.mkdir(parents=True, exist_ok=True)"
replacement1 = """    output_root = Path(os.path.expandvars(str(output_dir))).expanduser().resolve()
    from scripts.sw_connect import validate_path_against_allowed_roots, is_document_owned
    if not validate_path_against_allowed_roots(str(output_root)):
        raise PermissionError(f"Access denied: output_root '{output_root}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
    output_root.mkdir(parents=True, exist_ok=True)"""

target2 = """        finally:
            if close_documents and not was_open:
                sw.CloseDoc(get_com_member(model, "GetTitle"))"""

replacement2 = """        finally:
            if close_documents and not was_open and model is not None:
                try:
                    from scripts.sw_connect import is_document_owned
                    if is_document_owned(model):
                        doc_title = get_com_member(model, "GetTitle")
                        if doc_title:
                            sw.CloseDoc(doc_title)
                except Exception:
                    pass"""

c_norm = c.replace("\r\n", "\n")
t1_norm = target1.replace("\r\n", "\n")
t2_norm = target2.replace("\r\n", "\n")
r1_norm = replacement1.replace("\r\n", "\n")
r2_norm = replacement2.replace("\r\n", "\n")

if t1_norm in c_norm and t2_norm in c_norm:
    c_norm = c_norm.replace(t1_norm, r1_norm, 1).replace(t2_norm, r2_norm, 1)
    if "\r\n" in c:
        c_norm = c_norm.replace("\n", "\r\n")
    with open(p, "w", encoding="utf-8") as f:
        f.write(c_norm)
    print("sw_export.py patched successfully!")
else:
    print("Targets not found in sw_export.py")
