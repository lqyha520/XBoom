#!/usr/bin/env python3
"""一键：修 MySQL、建 XBoom、开 PHP、测上报"""
import os
import secrets
import sqlite3
import string
import subprocess
import sys
import time
from pathlib import Path

NEW_PWD = sys.argv[1] if len(sys.argv) > 1 else ""
if not NEW_PWD:
    NEW_PWD = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(16)
    )

MYSQL = "/www/server/mysql/bin/mysql"
MYSQLD_SAFE = "/www/server/mysql/bin/mysqld_safe"
PANEL_DB = "/www/server/panel/data/default.db"
SCHEMA = Path("/tmp/xboom_schema.sql")
STATS_DIR = Path("/www/wwwroot/updates.bcxtech.cn/stats")
EXT_CONF = Path(
    "/www/server/panel/vhost/nginx/extension/updates.bcxtech.cn/stats-php.conf"
)


def run(cmd, check=True, timeout=90, **kw):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=check, **kw)


def reset_mysql_root(password: str) -> None:
    run(["/etc/init.d/mysqld", "stop"], check=False)
    time.sleep(2)
    subprocess.run(["pkill", "-9", "mysqld_safe"], check=False)
    subprocess.run(["pkill", "-9", "mysqld"], check=False)
    time.sleep(2)
    subprocess.Popen(
        [MYSQLD_SAFE, "--skip-grant-tables", "--skip-networking"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(6)
    sql = (
        "FLUSH PRIVILEGES;\n"
        f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{password}';\n"
        "FLUSH PRIVILEGES;\n"
    )
    run([MYSQL, "-uroot"], input=sql.encode(), timeout=30)
    subprocess.run(["pkill", "-9", "mysqld_safe"], check=False)
    subprocess.run(["pkill", "-9", "mysqld"], check=False)
    time.sleep(2)
    subprocess.Popen(
        ["/etc/init.d/mysqld", "start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(2)
        p = run(
            [MYSQL, "-uroot", f"-p{password}", "-e", "SELECT 1"],
            check=False,
            timeout=15,
        )
        if p.returncode == 0:
            break
    else:
        raise RuntimeError("mysql not up after reset")
    con = sqlite3.connect(PANEL_DB)
    con.execute("update config set mysql_root=? where id=1", (password,))
    con.commit()


def apply_schema(password: str) -> None:
    run(
        [MYSQL, "-uroot", f"-p{password}"],
        input=SCHEMA.read_bytes(),
        timeout=60,
    )


def write_config_php(password: str) -> None:
    pwd_esc = password.replace("\\", "\\\\").replace("'", "\\'")
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    (STATS_DIR / "config.php").write_text(
        f"""<?php
return [
    'db_host' => 'localhost',
    'db_port' => 3306,
    'db_name' => 'XBoom',
    'db_user' => 'root',
    'db_pass' => '{pwd_esc}',
    'report_token' => '',
    'rate_limit_per_hour' => 30,
];
""",
        encoding="utf-8",
    )


def enable_stats_php() -> None:
    EXT_CONF.parent.mkdir(parents=True, exist_ok=True)
    EXT_CONF.write_text(
        """# 仅 /stats/ 目录执行 PHP（使用已安装的 PHP 8.2）
location ~ ^/stats/.+\\.php$ {
    try_files $uri =404;
    fastcgi_pass unix:/tmp/php-cgi-82.sock;
    fastcgi_index index.php;
    include fastcgi.conf;
    include pathinfo.conf;
}
""",
        encoding="utf-8",
    )
    run(["/etc/init.d/nginx", "reload"], check=False)


def test_report() -> None:
    p = run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            "https://updates.bcxtech.cn/stats/report.php",
            "-H",
            "Content-Type: application/json",
            "-d",
            '{"install_id":"11111111-1111-4111-8111-111111111111","app_version":"deploy","os_platform":"test"}',
        ],
        check=False,
        timeout=30,
    )
    print("curl_response", p.stdout.decode()[:300])


def main() -> int:
    if not SCHEMA.is_file():
        print("missing schema", file=sys.stderr)
        return 1
    print("reset_mysql ...")
    reset_mysql_root(NEW_PWD)
    print("apply_schema ...")
    apply_schema(NEW_PWD)
    print("write_config ...")
    write_config_php(NEW_PWD)
    print("enable_php ...")
    enable_stats_php()
    print("test ...")
    test_report()
    print("ALL_OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("FAILED", exc, file=sys.stderr)
        sys.exit(1)
