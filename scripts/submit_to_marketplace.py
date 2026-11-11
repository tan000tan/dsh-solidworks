# -*- coding: utf-8 -*-
"""
Marketplace Submission Updater & PR Submitter for DSH-SolidWorks v0.2.0
"""
import os
import shutil
import subprocess
import json
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_YML = os.path.join(BASE_DIR, "docs", "submission", "tan000tan__dsh-solidworks.yml")

def log(msg):
    clean = str(msg).encode("ascii", errors="backslashreplace").decode("ascii")
    print(f"[MARKET] {clean}")

def get_submission_repo_path():
    for d in os.listdir(BASE_DIR):
        if "备份" in d:
            p = os.path.join(BASE_DIR, d)
            for sub in os.listdir(p):
                if "awesome" in sub:
                    return os.path.join(p, sub)
    raise RuntimeError("Submission repo not found in backup directory")

def get_github_pat():
    p = subprocess.Popen(
        ['git', 'credential', 'fill'],
        cwd=BASE_DIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("GitHub PAT not found")

def update_and_push_marketplace_branch(repo_path, token):
    log(f"Updating submission in: {repo_path}")
    dst_yml = os.path.join(repo_path, "data", "plugins", "tan000tan__dsh-solidworks.yml")
    assert os.path.isfile(SRC_YML), f"Source YML missing: {SRC_YML}"
    
    # Read and ensure v0.2.0
    with open(SRC_YML, "r", encoding="utf-8") as f:
        content = f.read()
    log(f"New YML content:\n{content.strip()}")
    
    with open(dst_yml, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Check git status
    res = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True)
    log(f"Status in submission repo:\n{res.stdout.strip()}")
    
    subprocess.run(["git", "add", "data/plugins/tan000tan__dsh-solidworks.yml"], cwd=repo_path, check=True)
    commit_res = subprocess.run(
        ["git", "commit", "-m", "feat(plugins): update tan000tan/dsh-solidworks to v0.2.0"],
        cwd=repo_path, capture_output=True, text=True
    )
    log(f"Commit output: {commit_res.stdout.strip()} {commit_res.stderr.strip()}")
    
    # Push to fork
    log("Pushing to fork/feat/add-tan000tan-dsh-solidworks...")
    push_res = subprocess.run(
        ["git", "push", "fork", "feat/add-tan000tan-dsh-solidworks"],
        cwd=repo_path, capture_output=True, text=True
    )
    log(f"Push output: {push_res.stdout.strip()} {push_res.stderr.strip()}")
    
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path, text=True).strip()
    return head_sha

def check_or_create_marketplace_pr(token, branch_sha):
    log("=== Checking / Creating Pull Request to awesome-dsh-plugin ===")
    api_url = "https://api.github.com/repos/awesome-dsh-plugin/awesome-dsh-plugin/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Antigravity-Market-Submitter"
    }
    
    # Check existing open PRs from tan000tan
    req = urllib.request.Request(f"{api_url}?head=tan000tan:feat/add-tan000tan-dsh-solidworks&state=all", headers=headers)
    existing_pr = None
    try:
        with urllib.request.urlopen(req) as resp:
            prs = json.loads(resp.read().decode("utf-8"))
            if prs:
                existing_pr = prs[0]
                log(f"Found existing PR #{existing_pr['number']}: {existing_pr['html_url']} (state: {existing_pr['state']})")
    except urllib.error.HTTPError as e:
        log(f"Error checking PRs: {e.code} {e.read().decode('utf-8')}")
        
    if existing_pr:
        return {
            "pr_url": existing_pr["html_url"],
            "pr_number": existing_pr["number"],
            "state": existing_pr["state"],
            "status": "UPDATED_EXISTING_PR"
        }
    else:
        pr_payload = {
            "title": "feat(plugins): add tan000tan/dsh-solidworks v0.2.0",
            "head": "tan000tan:feat/add-tan000tan-dsh-solidworks",
            "base": "main",
            "body": (
                "### Description\n"
                "Submitting `tan000tan/dsh-solidworks` v0.2.0 to DSH Plugin Marketplace.\n\n"
                "### Details\n"
                "- **Plugin**: `tan000tan/dsh-solidworks`\n"
                "- **Version**: `v0.2.0`\n"
                "- **Category**: `tools`\n"
                "- **Release URL**: https://github.com/tan000tan/dsh-solidworks/releases/tag/v0.2.0\n"
                "- **Tarball**: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.2.0/dsh-solidworks-0.2.0.tgz\n"
                "- **SHA-256**: `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`\n"
            )
        }
        create_req = urllib.request.Request(api_url, data=json.dumps(pr_payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(create_req) as resp:
                new_pr = json.loads(resp.read().decode("utf-8"))
                log(f"Created new PR #{new_pr['number']}: {new_pr['html_url']}")
                return {
                    "pr_url": new_pr["html_url"],
                    "pr_number": new_pr["number"],
                    "state": new_pr["state"],
                    "status": "CREATED_NEW_PR"
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            log(f"HTTPError creating PR: {e.code} {err_msg}")
            return {
                "pr_url": "https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/compare/main...tan000tan:awesome-dsh-plugin:feat/add-tan000tan-dsh-solidworks?expand=1",
                "pr_number": None,
                "state": "READY_FOR_ONE_CLICK_CREATION",
                "status": f"SUBMITTED_TO_FORK_NEED_MANUAL_CLICK ({e.code})",
                "detail": err_msg
            }

if __name__ == "__main__":
    token = get_github_pat()
    repo_path = get_submission_repo_path()
    branch_sha = update_and_push_marketplace_branch(repo_path, token)
    pr_info = check_or_create_marketplace_pr(token, branch_sha)
    log(f"Marketplace submission complete: {pr_info}")
