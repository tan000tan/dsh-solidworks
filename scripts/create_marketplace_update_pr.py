# -*- coding: utf-8 -*-
"""
Create Version Update PR to awesome-dsh-plugin for v0.2.0
"""
import os
import subprocess
import json
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_YML = os.path.join(BASE_DIR, "docs", "submission", "tan000tan__dsh-solidworks.yml")

def log(msg):
    clean = str(msg).encode("ascii", errors="backslashreplace").decode("ascii")
    print(f"[MARKET-PR] {clean}")

def get_submission_repo():
    for d in os.listdir(BASE_DIR):
        if "备份" in d:
            p = os.path.join(BASE_DIR, d)
            for sub in os.listdir(p):
                if "awesome" in sub:
                    return os.path.join(p, sub)
    raise RuntimeError("Submission repo not found")

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], cwd=BASE_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for l in out.splitlines():
        if l.startswith("password="):
            return l.split("=", 1)[1].strip()
    raise RuntimeError("No token")

if __name__ == "__main__":
    token = get_token()
    repo = get_submission_repo()
    log(f"Operating in repo: {repo}")
    
    # 1. Fetch origin main
    subprocess.run(["git", "fetch", "origin", "main"], cwd=repo, check=True)
    
    # 2. Create clean branch for v0.2.0 update
    branch_name = "feat/update-tan000tan-dsh-solidworks-v020"
    subprocess.run(["git", "checkout", "-B", branch_name, "origin/main"], cwd=repo, check=True)
    
    # 3. Copy v0.2.0 YAML
    dst_yml = os.path.join(repo, "data", "plugins", "tan000tan__dsh-solidworks.yml")
    with open(SRC_YML, "r", encoding="utf-8") as f:
        content = f.read()
    with open(dst_yml, "w", encoding="utf-8") as f:
        f.write(content)
        
    subprocess.run(["git", "add", "data/plugins/tan000tan__dsh-solidworks.yml"], cwd=repo, check=True)
    commit_res = subprocess.run(["git", "commit", "-m", "feat(plugins): update tan000tan/dsh-solidworks to v0.2.0"], cwd=repo, capture_output=True, text=True)
    log(f"Commit: {commit_res.stdout.strip()}")
    
    # 4. Push to user fork
    log(f"Pushing {branch_name} to fork...")
    push_res = subprocess.run(["git", "push", "-u", "fork", branch_name, "--force"], cwd=repo, capture_output=True, text=True)
    log(f"Push: {push_res.stdout.strip()} {push_res.stderr.strip()}")
    
    # 5. Create Pull Request
    api_url = "https://api.github.com/repos/awesome-dsh-plugin/awesome-dsh-plugin/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Antigravity-Market-Submitter"
    }
    
    pr_payload = {
        "title": "feat(plugins): update tan000tan/dsh-solidworks to v0.2.0",
        "head": f"tan000tan:{branch_name}",
        "base": "main",
        "body": (
            "### Description\n"
            "Update `tan000tan/dsh-solidworks` to official release `v0.2.0`.\n\n"
            "### Release Details\n"
            "- **Plugin**: `tan000tan/dsh-solidworks`\n"
            "- **Version**: `v0.2.0`\n"
            "- **Category**: `tools`\n"
            "- **Release Notes**: https://github.com/tan000tan/dsh-solidworks/releases/tag/v0.2.0\n"
            "- **Tarball**: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.2.0/dsh-solidworks-0.2.0.tgz\n"
            "- **SHA-256**: `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`\n"
        )
    }
    
    req = urllib.request.Request(api_url, data=json.dumps(pr_payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            pr_data = json.loads(resp.read().decode("utf-8"))
            log(f"New PR created successfully: {pr_data['html_url']} (PR #{pr_data['number']})")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        log(f"PR Creation result: HTTP {e.code} - {err_msg}")
