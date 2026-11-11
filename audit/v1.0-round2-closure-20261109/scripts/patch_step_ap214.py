p = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\scripts\sw_export.py"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

# 1. 修改 export_to_step
old_step = """def export_to_step(model, output_path):
    \"\"\"导出为 STEP 格式\"\"\"
    return _export_generic(model, output_path)"""

new_step = """def export_to_step(model, output_path):
    \"\"\"导出为 STEP AP214 格式\"\"\"
    try:
        sw = model.GetSldWorksObject() or getattr(model, "Application", None)
        if sw:
            sw.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214
    except Exception:
        pass
    return _export_generic(model, output_path)"""

# 2. 修改 _export_generic
old_generic = """def _export_generic(model, output_path):
    \"\"\"通用导出（STEP/STL/IGES/Parasolid/DXF）\"\"\"
    model.ClearSelection2(True)"""

new_generic = """def _export_generic(model, output_path):
    \"\"\"通用导出（STEP/STL/IGES/Parasolid/DXF）\"\"\"
    model.ClearSelection2(True)
    ext_lower = os.path.splitext(output_path)[1].lower()
    if ext_lower in ('.step', '.stp'):
        try:
            sw = model.GetSldWorksObject() or getattr(model, "Application", None)
            if sw:
                sw.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214
        except Exception:
            pass"""

# 3. 在 batch_export_formats 中加入 AP214 设置
old_batch_loop = "            for extension in extensions:"
new_batch_loop = """            for extension in extensions:
                if extension in ('.step', '.stp'):
                    try:
                        sw.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214
                    except Exception:
                        pass"""

c_norm = c.replace("\r\n", "\n")
t_step = old_step.replace("\r\n", "\n")
t_gen = old_generic.replace("\r\n", "\n")
t_loop = old_batch_loop.replace("\r\n", "\n")

if t_step in c_norm and t_gen in c_norm and t_loop in c_norm:
    c_norm = c_norm.replace(t_step, new_step.replace("\r\n", "\n"), 1)
    c_norm = c_norm.replace(t_gen, new_generic.replace("\r\n", "\n"), 1)
    c_norm = c_norm.replace(t_loop, new_batch_loop.replace("\r\n", "\n"), 1)
    if "\r\n" in c:
        c_norm = c_norm.replace("\n", "\r\n")
    with open(p, "w", encoding="utf-8") as f:
        f.write(c_norm)
    print("STEP AP214 configuration successfully patched in sw_export.py!")
else:
    print("Failed to find targets in sw_export.py")
