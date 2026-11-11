server_py = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\mcp-server\server.py"

with open(server_py, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    
    # 1. batch_export
    if "def solidworks_batch_export_files(" in line:
        # 找到其 def op():
        while i + 1 < len(lines) and "def op():" not in lines[i+1]:
            i += 1
            new_lines.append(lines[i])
        if i + 1 < len(lines):
            i += 1
            new_lines.append(lines[i]) # def op():
            patch = (
                "\n"
                "        from scripts.sw_connect import validate_path_against_allowed_roots\n"
                "\n"
                "        if not validate_path_against_allowed_roots(params.output_dir):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: output_dir '{params.output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
                "\n"
                "        for fp in params.file_paths:\n"
                "\n"
                "            if not validate_path_against_allowed_roots(fp):\n"
                "\n"
                "                raise PermissionError(f\"Access denied: file_path '{fp}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
            )
            new_lines.append(patch)
            
    # 2. generate_drawing
    elif "def solidworks_generate_drawing(" in line:
        while i + 1 < len(lines) and "def op():" not in lines[i+1]:
            i += 1
            new_lines.append(lines[i])
        if i + 1 < len(lines):
            i += 1
            new_lines.append(lines[i]) # def op():
            patch = (
                "\n"
                "        from scripts.sw_connect import validate_path_against_allowed_roots\n"
                "\n"
                "        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()\n"
                "\n"
                "        if not validate_path_against_allowed_roots(str(output_dir)):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: output_dir '{output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
                "\n"
                "        if params.spec_path and not validate_path_against_allowed_roots(str(params.spec_path)):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: spec_path '{params.spec_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
            )
            new_lines.append(patch)
            # 跳过原有的 output_dir 行
            while i + 1 < len(lines) and "output_dir = Path(" not in lines[i+1]:
                i += 1
                new_lines.append(lines[i])
            if i + 1 < len(lines) and "output_dir = Path(" in lines[i+1]:
                i += 1 # 跳过原有的 output_dir = Path(...)
                
    # 3. review_drawing
    elif "def solidworks_review_drawing(" in line:
        while i + 1 < len(lines) and "def op():" not in lines[i+1]:
            i += 1
            new_lines.append(lines[i])
        if i + 1 < len(lines):
            i += 1
            new_lines.append(lines[i]) # def op():
            patch = (
                "\n"
                "        from scripts.sw_connect import validate_path_against_allowed_roots\n"
                "\n"
                "        if not validate_path_against_allowed_roots(str(params.drawing_path)):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: drawing_path '{params.drawing_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
                "\n"
                "        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()\n"
                "\n"
                "        if not validate_path_against_allowed_roots(str(output_dir)):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: output_dir '{output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
            )
            new_lines.append(patch)
            while i + 1 < len(lines) and "output_dir = Path(" not in lines[i+1]:
                i += 1
                new_lines.append(lines[i])
            if i + 1 < len(lines) and "output_dir = Path(" in lines[i+1]:
                i += 1

    # 4. inspect_drawing
    elif "def solidworks_inspect_drawing(" in line:
        while i + 1 < len(lines) and "def op():" not in lines[i+1]:
            i += 1
            new_lines.append(lines[i])
        if i + 1 < len(lines):
            i += 1
            new_lines.append(lines[i]) # def op():
            patch = (
                "\n"
                "        from scripts.sw_connect import validate_path_against_allowed_roots\n"
                "\n"
                "        if not validate_path_against_allowed_roots(str(params.drawing_path)):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: drawing_path '{params.drawing_path}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
                "\n"
                "        output_dir = Path(os.path.expandvars(params.output_dir)).expanduser().resolve()\n"
                "\n"
                "        if not validate_path_against_allowed_roots(str(output_dir)):\n"
                "\n"
                "            raise PermissionError(f\"Access denied: output_dir '{output_dir}' is outside allowed roots (DSH_ALLOWED_ROOTS)\")\n"
            )
            new_lines.append(patch)
            while i + 1 < len(lines) and "output_dir = Path(" not in lines[i+1]:
                i += 1
                new_lines.append(lines[i])
            if i + 1 < len(lines) and "output_dir = Path(" in lines[i+1]:
                i += 1

    i += 1

with open(server_py, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("server.py safely patched with security guards!")
