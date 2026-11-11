import os
import shutil
import hashlib

src_repo = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
backups_root = r"D:\Agent工作区\Backups"
latest_old_backup = os.path.join(backups_root, "dsh-solidworks-plugin-backup-final-release-20261108")
new_backup = os.path.join(backups_root, "dsh-solidworks-plugin-backup-round2-closure-20261109")

# 1. 详细比对 latest_old_backup 与当前工作区
old_files = {}
for root, dirs, files in os.walk(latest_old_backup):
    for f in files:
        full_p = os.path.join(root, f)
        rel_p = os.path.relpath(full_p, latest_old_backup).replace("\\", "/")
        old_files[rel_p] = os.path.getsize(full_p)

current_files = {}
for root, dirs, files in os.walk(src_repo):
    if any(x in root for x in [".git", "node_modules", ".venv"]):
        continue
    for f in files:
        full_p = os.path.join(root, f)
        rel_p = os.path.relpath(full_p, src_repo).replace("\\", "/")
        current_files[rel_p] = os.path.getsize(full_p)

added_in_current = [p for p in current_files if p not in old_files]
missing_in_current = [p for p in old_files if p not in current_files]
size_changed = [p for p in current_files if p in old_files and current_files[p] != old_files[p]]

diff_report = {
    "latest_old_backup_files": len(old_files),
    "current_working_files": len(current_files),
    "added_count": len(added_in_current),
    "missing_count": len(missing_in_current),
    "size_changed_count": len(size_changed),
    "added_sample": added_in_current[:20],
    "missing_sample": missing_in_current[:20],
    "size_changed_sample": size_changed[:20]
}

report_path = os.path.join(src_repo, "audit", "v1.0-round2-closure-20261109", "BACKUP_DIFFERENTIAL_AUDIT.json")
import json
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(diff_report, f, ensure_ascii=False, indent=2)

print("Backup differential analysis complete!")
print(f"Old backup: {len(old_files)} files, Current: {len(current_files)} files")
print(f"Added: {len(added_in_current)}, Missing: {len(missing_in_current)}, Changed: {len(size_changed)}")

# 2. 制作全新的 Round 2 物理备份
if not os.path.exists(new_backup):
    print(f"Creating new backup at {new_backup}...")
    def ignore_patterns(path, names):
        ignored = []
        for n in names:
            if n in [".git", "node_modules", ".venv"]:
                ignored.append(n)
        return ignored
    shutil.copytree(src_repo, new_backup, ignore=ignore_patterns)
    print("New round 2 backup created successfully!")
else:
    print(f"New backup already exists at {new_backup}")

# 统计新备份
new_total_files = 0
new_total_size = 0
for root, dirs, files in os.walk(new_backup):
    new_total_files += len(files)
    for f in files:
        new_total_size += os.path.getsize(os.path.join(root, f))

print(f"Round 2 backup stats: {new_total_files} files, {new_total_size} bytes ({new_total_size/1024/1024:.2f} MB)")
