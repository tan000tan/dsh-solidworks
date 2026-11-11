import os

server_py = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\mcp-server\server.py"

with open(server_py, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

# 1. 补丁 solidworks_batch_export_files
old_batch = """def solidworks_batch_export_files(params: SolidWorksBatchExportInput) -> str:
    \"\"\"Export multiple local SolidWorks files and verify every output was produced this run.\"\"\"

    def op():
        sw, _model = connect_solidworks(wait_seconds=1)"""

new_batch = """def solidworks_batch_export_files(params: SolidWorksBatchExportInput) -> str:
    \"\"\"Export multiple local SolidWorks files and verify every output was produced this run.\"\"\"

    def op():
        from scripts.sw_connect import validate_path_against_allowed_roots
        if not validate_path_against_allowed_roots(params.output_dir):
            raise PermissionError(f"Access denied: output_dir '{params.output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
        for fp in params.file_paths:
            if not validate_path_against_allowed_roots(fp):
                raise PermissionError(f"Access denied: file_path '{fp}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
        sw, _model = connect_solidworks(wait_seconds=1)"""

# 2. 补丁 solidworks_generate_drawing
old_gen = """def solidworks_generate_drawing(params: SolidWorksGenerateDrawingInput) -> str:
    \"\"\"按 DrawingSpec v1 创建工程图、PDF、预览和机器审视报告。\"\"\"

    def op():
        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()"""

new_gen = """def solidworks_generate_drawing(params: SolidWorksGenerateDrawingInput) -> str:
    \"\"\"按 DrawingSpec v1 创建工程图、PDF、预览和机器审视报告。\"\"\"

    def op():
        from scripts.sw_connect import validate_path_against_allowed_roots
        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()
        if not validate_path_against_allowed_roots(str(output_dir)):
            raise PermissionError(f"Access denied: output_dir '{output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
        if params.spec_path and not validate_path_against_allowed_roots(str(params.spec_path)):
            raise PermissionError(f"Access denied: spec_path '{params.spec_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")"""

# 3. 补丁 solidworks_generate_drawing 中的 source_path
old_source = """        source_path = Path(os.path.expandvars(str(spec["sourceModel"]))).expanduser().resolve()
        if not source_path.is_file():"""

new_source = """        source_path = Path(os.path.expandvars(str(spec["sourceModel"]))).expanduser().resolve()
        if not validate_path_against_allowed_roots(str(source_path)):
            raise PermissionError(f"Access denied: sourceModel '{source_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
        if not source_path.is_file():"""

# 4. 补丁 solidworks_review_drawing
old_review = """def solidworks_review_drawing(params: SolidWorksReviewDrawingInput) -> str:
    \"\"\"打开工程图并执行 DrawingSpec、布局、尺寸、孔槽和 PDF 证据审视。\"\"\"

    def op():
        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()"""

new_review = """def solidworks_review_drawing(params: SolidWorksReviewDrawingInput) -> str:
    \"\"\"打开工程图并执行 DrawingSpec、布局、尺寸、孔槽和 PDF 证据审视。\"\"\"

    def op():
        from scripts.sw_connect import validate_path_against_allowed_roots
        if not validate_path_against_allowed_roots(str(params.drawing_path)):
            raise PermissionError(f"Access denied: drawing_path '{params.drawing_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()
        if not validate_path_against_allowed_roots(str(output_dir)):
            raise PermissionError(f"Access denied: output_dir '{output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)")"""

# 5. 补丁 solidworks_inspect_drawing
old_inspect = """def solidworks_inspect_drawing(params: SolidWorksInspectDrawingInput) -> str:
    \"\"\"只读读取工程图页、视图、尺寸、注释和表格结构，并生成预览证据。\"\"\"

    def op():
        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()"""

new_inspect = """def solidworks_inspect_drawing(params: SolidWorksInspectDrawingInput) -> str:
    \"\"\"只读读取工程图页、视图、尺寸、注释和表格结构，并生成预览证据。\"\"\"

    def op():
        from scripts.sw_connect import validate_path_against_allowed_roots
        if not validate_path_against_allowed_roots(str(params.drawing_path)):
            raise PermissionError(f"Access denied: drawing_path '{params.drawing_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)")
        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()
        if not validate_path_against_allowed_roots(str(output_dir)):
            raise PermissionError(f"Access denied: output_dir '{output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)")"""

# 规范化换行进行替换
def do_replace(txt, old_s, new_s):
    # 处理双换行或单换行
    old_crlf = old_s.replace("\r\n", "\n").replace("\n", "\r\n")
    old_lf = old_s.replace("\r\n", "\n")
    new_norm = new_s.replace("\r\n", "\n")
    if "\r\n" in txt:
        new_norm = new_norm.replace("\n", "\r\n")
        if old_crlf in txt:
            return txt.replace(old_crlf, new_norm, 1)
    if old_lf in txt:
        return txt.replace(old_lf, new_norm, 1)
    
    # 尝试正则替换多余空行
    import re
    pat = re.escape(old_lf).replace(r"\n", r"\s*\n\s*")
    sub_res = re.sub(pat, new_norm, txt, count=1)
    return sub_res

original = content
content = do_replace(content, old_batch, new_batch)
content = do_replace(content, old_gen, new_gen)
content = do_replace(content, old_source, new_source)
content = do_replace(content, old_review, new_review)
content = do_replace(content, old_inspect, new_inspect)

if content != original:
    with open(server_py, "w", encoding="utf-8") as f:
        f.write(content)
    print("server.py successfully patched with security guards!")
else:
    print("Warning: No patches applied to server.py!")
