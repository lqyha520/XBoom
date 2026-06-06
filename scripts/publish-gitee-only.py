#!/usr/bin/env python3
"""Publish current version to Gitee Release (no PowerShell encoding issues)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip()
    return data


def main() -> int:
    gitee = load_env(ROOT / "scripts" / "gitee-release.env")
    mirror = load_env(ROOT / "scripts" / "update-mirror.env")
    token = gitee.get("GITEE_TOKEN", "")
    if not token:
        print("Missing GITEE_TOKEN in scripts/gitee-release.env", file=sys.stderr)
        return 1

    owner = gitee.get("GITEE_OWNER", "lqyha520")
    repo = gitee.get("GITEE_REPO", "XBoom")
    branch = gitee.get("GITEE_BRANCH", "master")

    sys.path.insert(0, str(ROOT))
    from src.ai_write_x.version import get_version

    version = get_version()
    tag = f"v{version}"
    setup_items = sorted(
        (ROOT / "dist" / "installer").glob("*-Setup.exe"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not setup_items:
        print("Run build_windows_installer.ps1 first", file=sys.stderr)
        return 1
    setup = setup_items[0]
    installer_name = setup.name

    mirror_base = mirror.get("MIRROR_BASE_URL", "").rstrip("/")
    if not mirror_base:
        print(
            "璇峰湪 scripts/update-mirror.env 閰嶇疆 MIRROR_BASE_URL锛堣吘璁簯 updates 鐩綍锛?,
            file=sys.stderr,
        )
        return 1
    download_url = f"{mirror_base}/{installer_name}"

    existing_policy = {}
    local_policy_path = ROOT / "version-policy.json"
    if local_policy_path.exists():
        try:
            existing_policy = json.loads(local_policy_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    min_supported = existing_policy.get("min_supported_version") or "1.0.4"

    policy = {
        "latest_version": version,
        "min_supported_version": min_supported,
        "auto_update_on_startup": True,
        "auto_update_silent": True,
        "download_url": download_url,
        "release_notes": f"灏忕垎鏉ュ挴 v{version}",
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    policy_path = ROOT / "version-policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")

    base = f"https://gitee.com/api/v5/repos/{owner}/{repo}"
    headers = {"User-Agent": "AIWriteX-Publisher"}
    params = {"access_token": token}

    with httpx.Client(timeout=60, headers=headers) as client:
        releases = client.get(f"{base}/releases", params={**params, "per_page": 50}).json()
        for rel in releases:
            old_tag = rel.get("tag_name", "")
            if old_tag and old_tag != tag:
                rid = rel["id"]
                client.delete(f"{base}/releases/{rid}", params=params)
                print(f"Deleted old release {old_tag}")

        existing = next((r for r in releases if r.get("tag_name") == tag), None)
        if existing:
            client.delete(f"{base}/releases/{existing['id']}", params=params)
            print(f"Recreate release {tag}")

        body = {
            "tag_name": tag,
            "name": f"灏忕垎鏉ュ挴 {tag}",
            "body": policy["release_notes"],
            "target_commitish": branch,
            "prerelease": False,
        }
        created = client.post(f"{base}/releases", params=params, json=body)
        created.raise_for_status()
        release_id = created.json()["id"]

        uri = f"{base}/releases/{release_id}/attach_files?access_token={token}"
        subprocess.run(
            ["curl.exe", "-sS", "-X", "POST", uri, "-F", f"file=@{policy_path}"],
            check=True,
        )
        if setup.stat().st_size <= 100 * 1024 * 1024:
            subprocess.run(
                ["curl.exe", "-sS", "-X", "POST", uri, "-F", f"file=@{setup}"],
                check=True,
            )
            print("Uploaded installer to Gitee")
        else:
            print("Installer > 100MB, skip Gitee exe (use Tencent mirror)")

    ssh_host = mirror.get("SSH_HOST", "").strip()
    if ssh_host:
        upload = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ssh-upload-mirror.py")],
            cwd=str(ROOT),
        )
        if upload.returncode != 0:
            return upload.returncode
    else:
        print("鏈厤缃?SSH_HOST锛岃鎵嬪姩涓婁紶瀹夎鍖呬笌 version-policy.json 鍒拌吘璁簯", file=sys.stderr)

    print(f"Done: https://gitee.com/{owner}/{repo}/releases/tag/{tag}")
    print(f"download_url: {download_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

