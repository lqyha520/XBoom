#!/usr/bin/env python3
"""创建 XBoom 专用库账号，并更新 stats/config.php"""
import secrets
import sqlite3
import string
import subprocess
import sys
import time
from pathlib import Path

DB_NAME = "XBoom"
DB_USER = "xboom"
NEW_ROOT = sys.argv[1] if len(sys.argv) > 1 else ""
DB_PASS = sys.argv[2] if len(sys.argv) > 2 else ""

if not NEW_ROOT:
    NEW_ROOT = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(16)
    )
if not DB_PASS:
    DB_PASS = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(16)
    )

MYSQL = "/www/server/mysql/bin/mysql"
MYSQLD_SAFE = "/www/server/mysql/bin/mysqld_safe"
PANEL_DB = "/www/server/panel/data/default.db"
CONFIG_PHP = Path("/www/wwwroot/updates.bcxtech.cn/stats/config.php")


def run(cmd, check=True, timeout=90, **kw):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=check, **kw)


def reset_root(password: str) -> None:
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
            return
    raise RuntimeError("mysql root not ready")


def setup_db(root_pwd: str, app_pwd: str) -> None:
    sql = f"""
CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '{DB_USER}'@'localhost' IDENTIFIED BY '{app_pwd}';
CREATE USER IF NOT EXISTS '{DB_USER}'@'127.0.0.1' IDENTIFIED BY '{app_pwd}';
ALTER USER '{DB_USER}'@'localhost' IDENTIFIED BY '{app_pwd}';
ALTER USER '{DB_USER}'@'127.0.0.1' IDENTIFIED BY '{app_pwd}';
GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO '{DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO '{DB_USER}'@'127.0.0.1';
FLUSH PRIVILEGES;
"""
    run([MYSQL, "-uroot", f"-p{root_pwd}"], input=sql.encode(), timeout=60)

    schema = Path("/tmp/xboom_schema.sql")
    if schema.is_file():
        body = schema.read_text(encoding="utf-8")
        if "CREATE DATABASE" in body:
            body = body.split("USE `XBoom`;", 1)[-1]
            body = f"USE `{DB_NAME}`;\n" + body
        run([MYSQL, "-uroot", f"-p{root_pwd}"], input=body.encode(), timeout=60)


def write_config(app_pwd: str) -> None:
    esc = app_pwd.replace("\\", "\\\\").replace("'", "\\'")
    CONFIG_PHP.write_text(
        f"""<?php
return [
    'db_host' => 'localhost',
    'db_port' => 3306,
    'db_name' => '{DB_NAME}',
    'db_user' => '{DB_USER}',
    'db_pass' => '{esc}',
    'report_token' => '',
    'rate_limit_per_hour' => 30,
];
""",
        encoding="utf-8",
    )


def panel_register(root_pwd: str, app_pwd: str) -> None:
    import datetime

    con = sqlite3.connect(PANEL_DB)
    con.execute("update config set mysql_root=? where id=1", (root_pwd,))
    exists = con.execute(
        "select id from databases where name=?", (DB_NAME,)
    ).fetchone()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if exists:
        con.execute(
            "update databases set username=?, password=? where name=?",
            (DB_USER, app_pwd, DB_NAME),
        )
    else:
        con.execute(
            "insert into databases (pid, name, username, password, accept, ps, addtime) "
            "values (0, ?, ?, ?, '127.0.0.1', '小爆使用统计', ?)",
            (DB_NAME, DB_USER, app_pwd, now),
        )
    con.commit()


def main() -> int:
    print("RESET_ROOT", NEW_ROOT)
    print("DB_NAME", DB_NAME)
    print("DB_USER", DB_USER)
    print("DB_PASS", DB_PASS)
    reset_root(NEW_ROOT)
    setup_db(NEW_ROOT, DB_PASS)
    write_config(DB_PASS)
    panel_register(NEW_ROOT, DB_PASS)
    p = run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            "http://127.0.0.1/stats/report.php",
            "-H",
            "Host: updates.bcxtech.cn",
            "-H",
            "Content-Type: application/json",
            "-d",
            '{"install_id":"55555555-5555-4555-8555-555555555555","app_version":"1.0.2","os_platform":"ok"}',
        ],
        check=False,
        timeout=20,
    )
    print("REPORT", p.stdout.decode()[:120])
    return 0


if __name__ == "__main__":
    main()
