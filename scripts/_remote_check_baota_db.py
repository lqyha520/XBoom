#!/usr/bin/env python3
import re
import sqlite3
import subprocess

con = sqlite3.connect("/www/server/panel/data/default.db")
rows = con.execute("select id,name,username,password,addtime from databases").fetchall()
print("PANEL_DB_LIST", rows)

text = open("/www/wwwroot/updates.bcxtech.cn/stats/config.php", encoding="utf-8").read()
user = re.search(r"'db_user'\s*=>\s*'([^']*)'", text).group(1)
pwd = re.search(r"'db_pass'\s*=>\s*'([^']*)'", text).group(1)
db = re.search(r"'db_name'\s*=>\s*'([^']*)'", text).group(1)

print("APP_USER", user, "DB", db)

for host in ("localhost", "127.0.0.1"):
    p = subprocess.run(
        [
            "/www/server/mysql/bin/mysql",
            f"-u{user}",
            f"-p{pwd}",
            f"-h{host}",
            "-e",
            f"SHOW DATABASES LIKE '{db}'; USE `{db}`; SHOW TABLES;",
        ],
        capture_output=True,
        timeout=20,
    )
    print(f"MYSQL_AS_{user}@{host}", "code", p.returncode)
    print(p.stdout.decode())
    print(p.stderr.decode()[:150])

p2 = subprocess.run(
    [
        "curl",
        "-s",
        "-X",
        "POST",
        "https://updates.bcxtech.cn/stats/report.php",
        "-H",
        "Content-Type: application/json",
        "-d",
        '{"install_id":"66666666-6666-4666-8666-666666666666","app_version":"1.0.2","os_platform":"check"}',
    ],
    capture_output=True,
    timeout=20,
)
print("HTTPS_REPORT", p2.stdout.decode()[:150])
