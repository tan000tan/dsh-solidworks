import os
import shutil
import stat

def remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ignore_dirs = {".git", ".venv", "node_modules"}

count_files = 0
count_dirs = 0

for dirpath, dirnames, filenames in os.walk(root, topdown=False):
    if any(ig in dirpath for ig in ignore_dirs):
        continue
    for f in filenames:
        if f.endswith(".pyc") or f.endswith(".pyo"):
            fp = os.path.join(dirpath, f)
            try:
                os.chmod(fp, stat.S_IWRITE)
                os.remove(fp)
                count_files += 1
            except Exception as e:
                print(f"Failed to remove file {fp}: {e}")
    for d in dirnames:
        if d == "__pycache__":
            dp = os.path.join(dirpath, d)
            try:
                os.chmod(dp, stat.S_IWRITE)
                shutil.rmtree(dp, onerror=remove_readonly)
                count_dirs += 1
            except Exception as e:
                print(f"Failed to remove dir {dp}: {e}")

print(f"Cleaned {count_files} bytecode files and {count_dirs} cache directories.")
