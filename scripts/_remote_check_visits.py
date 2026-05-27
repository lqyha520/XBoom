#!/usr/bin/env python3
import re
import subprocess

text = open("/www/wwwroot/updates.bcxtech.cn/stats/config.php", encoding="utf-8").read()
user = re.search(r"'db_user'\s*=>\s*'([^']*)'", text).group(1)
pwd = re.search(r"'db_pass'\s*=>\s*'([^']*)'", text).group(1)

p = subprocess.run(
    [
        "/www/server/mysql/bin/mysql",
        f"-u{user}",
        f"-p{pwd}",
        "-hlocalhost",
        "-e",
        "USE xboom; SELECT COUNT(*) AS total FROM usage_visits; "
        "SELECT * FROM usage_visits ORDER BY id DESC LIMIT 10; "
        "SELECT COUNT(*) AS users FROM usage_users;",
    ],
    capture_output=True,
    text=True,
    timeout=20,
)
print(p.stdout)
print(p.stderr[:200] if p.returncode else "")

p2 = subprocess.run(
    [
        "tail",
        "-n",
        "20",
        "/www/wwwlogs/updates.bcxtech.cn.log",
    ],
    capture_output=True,
    text=True,
    timeout=10,
)
print("NGINX_TAIL")
print(p2.stdout[-2000:])
