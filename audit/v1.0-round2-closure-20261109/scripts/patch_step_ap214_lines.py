p = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\scripts\sw_export.py"
with open(p, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if "def export_to_step(model, output_path):" in line:
        patch = (
            "    try:\n"
            "        sw = model.GetSldWorksObject() or getattr(model, 'Application', None)\n"
            "        if sw:\n"
            "            sw.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214\n"
            "    except Exception:\n"
            "        pass\n"
        )
        new_lines.append(patch)
    elif "def _export_generic(model, output_path):" in line:
        patch = (
            "    ext_lower = os.path.splitext(output_path)[1].lower()\n"
            "    if ext_lower in ('.step', '.stp'):\n"
            "        try:\n"
            "            sw = model.GetSldWorksObject() or getattr(model, 'Application', None)\n"
            "            if sw:\n"
            "                sw.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214\n"
            "        except Exception:\n"
            "            pass\n"
        )
        new_lines.append(patch)
    elif "for extension in extensions:" in line:
        patch = (
            "                if extension in ('.step', '.stp'):\n"
            "                    try:\n"
            "                        sw.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214\n"
            "                    except Exception:\n"
            "                        pass\n"
        )
        new_lines.append(patch)

with open(p, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("STEP AP214 successfully injected into sw_export.py!")
