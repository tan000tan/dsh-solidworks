import os
import shutil
import hashlib

backup_src = r"D:\Agent工作区\Backups\dsh-solidworks-plugin-backup-round2-closure-20261109"
restore_dest = r"C:\Users\Khalil\AppData\Local\Temp\dsh-restore-verification-20261109"

if os.path.exists(restore_dest):
    shutil.rmtree(restore_dest, ignore_errors=True)

print(f"Restoring from {backup_src} to {restore_dest}...")
shutil.copytree(backup_src, restore_dest)

# 校验关键文件哈希
key_files = [
    "package.json",
    "dsh-plugin.json",
    "bin/dsh-solidworks.js",
    "lib/index.js",
    "lib/policy.js",
    "vendor/solidworks-automation-skill/mcp-server/server.py",
    "vendor/solidworks-automation-skill/scripts/sw_connect.py",
    "vendor/solidworks-automation-skill/scripts/sw_export.py"
]

results = []
for kf in key_files:
    p_src = os.path.join(backup_src, kf.replace("/", os.sep))
    p_dest = os.path.join(restore_dest, kf.replace("/", os.sep))
    
    if not os.path.exists(p_dest):
        results.append((kf, "MISSING", None, None))
        continue
        
    def hash_file(p):
        h = hashlib.sha256()
        with open(p, "rb") as fp:
            while chunk := fp.read(65536):
                h.update(chunk)
        return h.hexdigest()
        
    h_src = hash_file(p_src)
    h_dest = hash_file(p_dest)
    match = (h_src == h_dest)
    results.append((kf, "MATCH" if match else "MISMATCH", h_src, h_dest))

all_ok = all(r[1] == "MATCH" for r in results)
print(f"Restore verification completed! Result: {'SUCCESS' if all_ok else 'FAILED'}")
for r in results:
    print(f"  {r[0]}: {r[1]}")

report_p = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\v1.0-round2-closure-20261109\RESTORE_VERIFICATION_REPORT.txt"
with open(report_p, "w", encoding="utf-8") as fp:
    fp.write(f"RESTORE VERIFICATION AUDIT\nStatus: {'SUCCESS' if all_ok else 'FAILED'}\n")
    for r in results:
        fp.write(f"{r[0]}: {r[1]} (SHA256: {r[2]})\n")
