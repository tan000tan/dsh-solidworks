import os

backups_root = r"D:\Agent工作区\Backups"
dirs = [
    "dsh-solidworks-plugin-backup-pre-v1.0-20261108",
    "dsh-solidworks-plugin-backup-pre-continuous-rework-20261108",
    "dsh-solidworks-plugin-backup-final-release-20261108"
]

for d in dirs:
    p = os.path.join(backups_root, d)
    if not os.path.exists(p):
        print(f"Not found: {p}")
        continue
    total_files = 0
    total_size = 0
    subdirs = {}
    for root, dirnames, filenames in os.walk(p):
        total_files += len(filenames)
        for f in filenames:
            total_size += os.path.getsize(os.path.join(root, f))
        top = os.path.relpath(root, p).split(os.sep)[0]
        subdirs[top] = subdirs.get(top, 0) + len(filenames)
    print(f"=== {d} ===")
    print(f"  Total files: {total_files}")
    print(f"  Total size: {total_size} bytes ({total_size/1024/1024:.2f} MB)")
    print(f"  Top subdirs file counts: {sorted(subdirs.items(), key=lambda x: x[1], reverse=True)[:6]}")
