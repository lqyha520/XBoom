#!/usr/bin/env python3
"""通过 SSH/SFTP 上传更新文件到宝塔服务器（密钥或 SSH_PASSWORD，均勿写入 Git）。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import paramiko

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


def _load_private_key(key_path: Path) -> paramiko.PKey:
    errors: list[str] = []
    for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return key_cls.from_private_key_file(str(key_path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key_cls.__name__}: {exc}")
    raise ValueError(f"无法读取私钥 {key_path}: {'; '.join(errors)}")


def _resolve_key_path(env: dict[str, str]) -> Path | None:
    raw = (env.get("SSH_KEY_PATH") or os.environ.get("SSH_KEY_PATH", "")).strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        return candidate if candidate.exists() else None
    default = ROOT / "xiaobao.pem"
    return default if default.exists() else None


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-file", default="")
    parser.add_argument("--setup-file", default="")
    args = parser.parse_args()

    env = load_env(ROOT / "scripts" / "update-mirror.env")
    host = env.get("SSH_HOST") or os.environ.get("SSH_HOST", "")
    user = env.get("SSH_USER", "root")
    port = int(env.get("SSH_PORT", "22"))
    remote_dir = env.get("REMOTE_DIR", "/www/wwwroot/updates.bcxtech.cn")
    base_url = (env.get("MIRROR_BASE_URL") or "https://updates.bcxtech.cn").rstrip("/")
    password = os.environ.get("SSH_PASSWORD", "")
    key_path = _resolve_key_path(env)

    if not host:
        print("缺少 SSH_HOST", file=sys.stderr)
        return 1
    if not password and not key_path:
        print(
            "请设置 SSH 私钥（项目根 xiaobao.pem 或 update-mirror.env 的 SSH_KEY_PATH）"
            "或环境变量 SSH_PASSWORD",
            file=sys.stderr,
        )
        return 1

    sys.path.insert(0, str(ROOT))
    from src.ai_write_x.branding.install import INSTALLER_NAME
    from src.ai_write_x.version import get_version

    version = get_version()
    installer_name = INSTALLER_NAME

    if args.setup_file:
        setup_path = Path(args.setup_file)
    else:
        setup_candidates = sorted(
            (ROOT / "dist" / "installer").glob("*-Setup.exe"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        setup_path = setup_candidates[0] if setup_candidates else None

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
        "release_notes": f"小爆来咯 v{version}",
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "download_url": f"{base_url}/{installer_name}",
    }
    policy_bytes = (json.dumps(policy, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    (ROOT / "version-policy.json").write_bytes(policy_bytes)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    auth = "密钥" if key_path and not password else "密码"
    print(f"连接 {user}@{host}:{port} ({auth}) ...")
    connect_kwargs: dict = {
        "hostname": host,
        "port": port,
        "username": user,
        "timeout": 30,
    }
    if password:
        connect_kwargs["password"] = password
    elif key_path:
        connect_kwargs["pkey"] = _load_private_key(key_path)
    client.connect(**connect_kwargs)

    stdin, stdout, stderr = client.exec_command(f"mkdir -p '{remote_dir}' && ls -la '{remote_dir}'")
    stdout.channel.recv_exit_status()
    print(stdout.read().decode("utf-8", errors="replace")[:500])

    sftp = client.open_sftp()

    remote_policy = f"{remote_dir}/version-policy.json"
    print(f"上传 version-policy.json -> {remote_policy}")
    with sftp.file(remote_policy, "wb") as remote_file:
        remote_file.write(policy_bytes)

    if setup_path and setup_path.exists():
        remote_setup = f"{remote_dir}/{installer_name}"
        size_mb = setup_path.stat().st_size / (1024 * 1024)
        print(f"上传 {setup_path.name} ({size_mb:.1f} MB) -> {remote_setup} ...")
        sftp.put(str(setup_path), remote_setup)
    else:
        print("本地未找到安装包，仅上传 version-policy.json（请稍后运行 publish-all 上传 exe）")

    sftp.close()
    client.close()

    print("\n完成。请浏览器验证:")
    print(f"  {base_url}/version-policy.json")
    print(f"  {base_url}/{installer_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
