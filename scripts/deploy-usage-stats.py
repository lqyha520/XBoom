#!/usr/bin/env python3
"""通过 SSH 部署使用统计（复用 update-mirror.env + xiaobao.pem）。"""

from __future__ import annotations

import sys
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


def merge_env() -> dict[str, str]:
    merged = load_env(ROOT / "scripts" / "update-mirror.env")
    merged.update(load_env(ROOT / "scripts" / "usage-stats.env"))
    return merged


def load_key(env: dict[str, str]) -> paramiko.PKey:
    candidates = []
    if env.get("SSH_KEY_PATH"):
        p = Path(env["SSH_KEY_PATH"])
        candidates.append(p if p.is_absolute() else ROOT / p)
    candidates.append(ROOT / "xiaobao.pem")
    for path in candidates:
        if path.exists():
            for cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                try:
                    return cls.from_private_key_file(str(path))
                except Exception:
                    continue
    raise FileNotFoundError("未找到 SSH 私钥 xiaobao.pem")


def main() -> int:
    env = merge_env()
    host = env.get("SSH_HOST", "")
    if not host:
        print("缺少 SSH_HOST（scripts/update-mirror.env）", file=sys.stderr)
        return 1

    user = env.get("SSH_USER", "root")
    port = int(env.get("SSH_PORT", "22"))
    key = load_key(env)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"连接 {user}@{host}:{port} ...")
    client.connect(hostname=host, port=port, username=user, pkey=key, timeout=30)

    sftp = client.open_sftp()
    uploads = [
        (ROOT / "scripts" / "_remote_deploy_all.py", "/tmp/deploy_usage_stats.py"),
        (ROOT / "services" / "usage-stats" / "schema.sql", "/tmp/xboom_schema.sql"),
        (ROOT / "services" / "usage-stats" / "report.php", "/www/wwwroot/updates.bcxtech.cn/stats/report.php"),
    ]
    for local, remote in uploads:
        print(f"上传 {local.name} -> {remote}")
        sftp.put(str(local), remote)
    sftp.close()

    stdin, stdout, stderr = client.exec_command("python3 /tmp/deploy_usage_stats.py", timeout=300)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()

    print(out)
    if err.strip():
        print(err, file=sys.stderr)
    if code != 0 or "ALL_OK" not in out:
        return 1
    print("\n部署成功。宝塔 → 数据库 → XBoom → usage_users / usage_visits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
