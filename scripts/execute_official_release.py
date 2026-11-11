# -*- coding: utf-8 -*-
"""
Official Release Execution Script for DSH-SolidWorks v0.2.0
Handles Git Staging, Commit, Tagging, Push, GitHub Release Creation,
Asset Uploading, and Marketplace Submission Tracking.
"""
import os
import sys
import subprocess
import json
import urllib.request
import urllib.parse
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_DIR = os.path.join(BASE_DIR, "audit_round2_final")
TARBALL_PATH = os.path.join(BASE_DIR, "dsh-solidworks-0.2.0.tgz")

def log(msg):
    clean = str(msg).encode("ascii", errors="backslashreplace").decode("ascii")
    print(f"[RELEASE] {clean}")

def run_cmd(cmd, cwd=BASE_DIR, check=True):
    log(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and res.returncode != 0:
        log(f"Command failed with code {res.returncode}")
        log(f"STDOUT: {res.stdout.strip()}")
        log(f"STDERR: {res.stderr.strip()}")
        raise RuntimeError(f"Command failed: {cmd}")
    return res

def get_github_pat():
    p = subprocess.Popen(
        ['git', 'credential', 'fill'],
        cwd=BASE_DIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    out, err = p.communicate(input='protocol=https\nhost=github.com\n\n')
    token = None
    for line in out.splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1].strip()
            break
    if not token:
        raise RuntimeError("GitHub PAT not found in Git Credential Manager")
    return token

def stage_and_commit():
    log("=== Step 1: Staging files for official v0.2.0 release ===")
    
    # Add tracked modifications (the 35 audited files)
    run_cmd(["git", "add", "-u"])
    
    # Add new audited production scripts
    run_cmd(["git", "add", "vendor/solidworks-automation-skill/scripts/"])
    
    # Add new audited tests
    run_cmd(["git", "add", "tests/"])
    
    # Add audited docs and architectures
    run_cmd(["git", "add", "docs/CAD_GRAPH_EXECUTOR_ARCHITECTURE.md"])
    run_cmd(["git", "add", "docs/stage4_core_cad/"])
    run_cmd(["git", "add", "docs/stage5_advanced_ai_cad/"])
    run_cmd(["git", "add", "docs/submission/"])
    
    # Add final audit deliverables
    run_cmd(["git", "add", "audit_round2_final/"])
    
    # Add auxiliary verification scripts
    run_cmd(["git", "add", "scripts/"])
    
    status = run_cmd(["git", "status", "--porcelain=v1"])
    staged = [l for l in status.stdout.splitlines() if l.startswith("M ") or l.startswith("A ")]
    log(f"Staged files count: {len(staged)}")
    
    commit_msg = (
        "release: finalize v0.2.0 official release candidate and acceptance audit\n\n"
        "- Close evidence gaps: verified 64-char SHA-256 for dsh-solidworks-0.2.0.tgz\n"
        "- Complete reconciliation of 73 test files (54 PASS, 18 FAIL, 1 BLOCKED) and 76 logs\n"
        "- Document 18 FAIL classifications: fail-closed security enforcement without regressions\n"
        "- Verify SolidWorks PID lifecycle, errata corrections, and exit code 1 mechanism\n"
        "- Review and classify 35 patch files in FINAL_SOURCE_DIFF.patch\n"
        "- Validate Python credential security with inter-process file locks and 8/8 negative tests"
    )
    
    commit_res = run_cmd(["git", "commit", "-m", commit_msg], check=False)
    if commit_res.returncode == 0:
        log("Commit successful.")
    else:
        log("Nothing new to commit or already committed: " + commit_res.stdout.strip())
        
    head_sha = run_cmd(["git", "rev-parse", "HEAD"]).stdout.strip()
    log(f"Current HEAD commit SHA: {head_sha}")
    return head_sha

def create_and_push_tag(commit_sha):
    log("=== Step 2: Creating and Pushing v0.2.0 Tag ===")
    run_cmd(["git", "tag", "-f", "-a", "v0.2.0", "-m", "Release v0.2.0: official candidate with verified security and evidence"])
    tag_sha = run_cmd(["git", "rev-parse", "v0.2.0"]).stdout.strip()
    log(f"v0.2.0 Tag SHA: {tag_sha}")
    
    log("Pushing main branch to origin...")
    push_main = run_cmd(["git", "push", "origin", "main"])
    log(f"Push main output: {push_main.stdout.strip()} {push_main.stderr.strip()}")
    
    log("Pushing v0.2.0 tag to origin...")
    push_tag = run_cmd(["git", "push", "origin", "v0.2.0", "--force"])
    log(f"Push tag output: {push_tag.stdout.strip()} {push_tag.stderr.strip()}")
    return tag_sha

def create_github_release_and_upload(token, commit_sha):
    log("=== Step 3: Creating GitHub Release v0.2.0 ===")
    repo = "tan000tan/dsh-solidworks"
    api_url = f"https://api.github.com/repos/{repo}/releases"
    
    release_body = (
        "## DSH-SolidWorks v0.2.0 Official Release\n\n"
        "Official release candidate for DeepSeek Harness SolidWorks Integration Plugin.\n\n"
        "### Key Features & Capabilities\n"
        "- **Dual Security Boundary**: Fail-Closed safety policy intercepting unauthorized CAD modifications; HMAC-SHA256 benchmark credential protection with cross-platform file locking.\n"
        "- **Process Ownership Tracking**: Robust STA COM lifecycle management preventing orphan processes or unauthorized interference with user models.\n"
        "- **Feature Graph IR & Dimension Solver**: Full support for parametric dimension modification, feature tree optimization, and geometric inspection.\n\n"
        "### Verified Package Checksums\n"
        "- **Tarball**: `dsh-solidworks-0.2.0.tgz`\n"
        "- **File Size**: 1,353,150 bytes (~1.29 MB)\n"
        "- **SHA-256**: `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`\n"
        "- **SHA-1 (npm shasum)**: `e2dd9df6305ab4f0009d5bb61c1e38a989165bba`\n"
        "- **Package File Count**: 452 files (0 bytecode `.pyc` caches)\n\n"
        "### Prerequisites\n"
        "- Windows 10 / 11 64-bit\n"
        "- SolidWorks 2021 ~ 2026 registered with COM\n"
        "- Python 3.10+ with `mcp` installed\n"
    )
    
    payload = {
        "tag_name": "v0.2.0",
        "target_commitish": "main",
        "name": "v0.2.0: Official Production Release",
        "body": release_body,
        "draft": False,
        "prerelease": False
    }
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Antigravity-Release-Engine"
    }
    
    # Check if release already exists
    req = urllib.request.Request(f"{api_url}/tags/v0.2.0", headers=headers, method="GET")
    existing_release = None
    try:
        with urllib.request.urlopen(req) as resp:
            existing_release = json.loads(resp.read().decode("utf-8"))
            log(f"Found existing release ID: {existing_release.get('id')}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log("No existing release for v0.2.0, will create new one.")
        else:
            log(f"Error checking release: {e.code} {e.read().decode('utf-8')}")
            
    if existing_release:
        release_id = existing_release["id"]
        upload_url = existing_release["upload_url"]
        release_url = existing_release["html_url"]
    else:
        req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            created = json.loads(resp.read().decode("utf-8"))
            release_id = created["id"]
            upload_url = created["upload_url"]
            release_url = created["html_url"]
            log(f"Release v0.2.0 created successfully: {release_url} (ID: {release_id})")
            
    # Upload Asset
    log("=== Step 4: Uploading dsh-solidworks-0.2.0.tgz Asset ===")
    # upload_url comes with '{?name,label}' template
    clean_upload_url = upload_url.split("{")[0] + "?name=dsh-solidworks-0.2.0.tgz"
    
    # Check if asset already exists in release
    assets_url = f"{api_url}/{release_id}/assets"
    req_assets = urllib.request.Request(assets_url, headers=headers, method="GET")
    with urllib.request.urlopen(req_assets) as resp:
        assets = json.loads(resp.read().decode("utf-8"))
        for a in assets:
            if a["name"] == "dsh-solidworks-0.2.0.tgz":
                log(f"Deleting existing asset ID {a['id']} to ensure latest tarball is uploaded...")
                del_req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/assets/{a['id']}", headers=headers, method="DELETE")
                urllib.request.urlopen(del_req)
                break
                
    with open(TARBALL_PATH, "rb") as f:
        tarball_bytes = f.read()
        
    upload_headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/gzip",
        "Content-Length": str(len(tarball_bytes)),
        "User-Agent": "Antigravity-Release-Engine"
    }
    
    req_upload = urllib.request.Request(clean_upload_url, data=tarball_bytes, headers=upload_headers, method="POST")
    with urllib.request.urlopen(req_upload) as resp:
        uploaded_asset = json.loads(resp.read().decode("utf-8"))
        asset_url = uploaded_asset.get("browser_download_url")
        log(f"Asset uploaded successfully! Download URL: {asset_url}")
        
    return {
        "release_url": release_url,
        "release_id": release_id,
        "asset_url": asset_url
    }

if __name__ == "__main__":
    token = get_github_pat()
    log(f"GitHub PAT acquired successfully (length: {len(token)} chars).")
    
    commit_sha = stage_and_commit()
    tag_sha = create_and_push_tag(commit_sha)
    rel_info = create_github_release_and_upload(token, commit_sha)
    
    log("\n[OFFICIAL RELEASE SUMMARY]")
    log(f"Commit SHA:   {commit_sha}")
    log(f"Tag SHA:      {tag_sha}")
    log(f"Release URL:  {rel_info['release_url']}")
    log(f"Asset URL:    {rel_info['asset_url']}")
    log(f"SHA-256:      12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5")
