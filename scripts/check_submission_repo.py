# -*- coding: utf-8 -*-
import os
import subprocess

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backup_dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
print("Directories in base:")
for d in backup_dirs:
    print(" ", repr(d))

for d in backup_dirs:
    if "备份" in d or "awesome" in d:
        p = os.path.join(base, d)
        print("\nChecking subdirs in:", repr(d))
        for sub in os.listdir(p):
            sub_p = os.path.join(p, sub)
            print("  ", repr(sub))
            if "awesome" in sub:
                # check git
                git_dir = os.path.join(sub_p, ".git")
                print("   .git exists:", os.path.isdir(git_dir))
                res = subprocess.run(["git", "status"], cwd=sub_p, capture_output=True, text=True, errors="replace")
                print("   git status:\n", res.stdout[:300])
                remotes = subprocess.run(["git", "remote", "-v"], cwd=sub_p, capture_output=True, text=True, errors="replace")
                print("   git remotes:\n", remotes.stdout[:300])
                branches = subprocess.run(["git", "branch", "-avv"], cwd=sub_p, capture_output=True, text=True, errors="replace")
                print("   git branches:\n", branches.stdout[:300])
