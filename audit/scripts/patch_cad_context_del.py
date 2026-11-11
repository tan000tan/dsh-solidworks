path = r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\vendor\solidworks-automation-skill\scripts\cad_task_context.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 替换三处 DeleteSelection2(1) 为 DeleteSelection2(0)
old_del = "ext.DeleteSelection2(1)"
new_del = "ext.DeleteSelection2(0)"

count = content.count(old_del)
content = content.replace(old_del, new_del)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"SUCCESS: Replaced {count} occurrences of DeleteSelection2(1) with DeleteSelection2(0) in cad_task_context.py")
