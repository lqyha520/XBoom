#!/usr/bin/env python3
"""对照 bcxtech，把 XBoom 按宝塔规则写入面板并可显示"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime

PANEL_DB = "/www/server/panel/data/default.db"
CONFIG_PHP = "/www/wwwroot/updates.bcxtech.cn/stats/config.php"


def panel_rows():
    con = sqlite3.connect(PANEL_DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("select * from databases").fetchall()]
    return con, rows


def read_stats_creds():
    text = open(CONFIG_PHP, encoding="utf-8").read()
    return {
        "user": re.search(r"'db_user'\s*=>\s*'([^']*)'", text).group(1),
        "pass": re.search(r"'db_pass'\s*=>\s*'([^']*)'", text).group(1),
        "name": re.search(r"'db_name'\s*=>\s*'([^']*)'", text).group(1),
    }


def mysql_root_pwd():
    con = sqlite3.connect(PANEL_DB)
    return con.execute("select mysql_root from config where id=1").fetchone()[0].strip()


def try_bt_add(name: str, user: str, pwd: str, pid: int) -> bool:
    """尝试用宝塔 panel API 添加数据库"""
    panel_py = "/www/server/panel/pyenv/bin/python3"
    if not os.path.isfile(panel_py):
        panel_py = "python3"
    script = f"""
import sys
sys.path.insert(0, '/www/server/panel/class')
import public
try:
    import database
    db = database.database()
    # AddDatabase 参数因版本而异，尝试常见签名
    if hasattr(db, 'AddDatabase'):
        r = db.AddDatabase({{
            'name': '{name}',
            'db_user': '{user}',
            'password': '{pwd}',
            'dataAccess': '127.0.0.1',
            'address': '127.0.0.1',
            'ps': '小爆使用统计',
            'pid': {pid},
        }})
        print('AddDatabase', r)
    else:
        print('no AddDatabase')
except Exception as e:
    print('ERR', e)
"""
    proc = subprocess.run(
        [panel_py, "-c", script],
        cwd="/www/server/panel",
        capture_output=True,
        timeout=60,
        text=True,
    )
    print(proc.stdout)
    print(proc.stderr[:500] if proc.stderr else "")
    return "AddDatabase" in proc.stdout and "ERR" not in proc.stdout


def main():
    creds = read_stats_creds()
    print("STATS", creds["name"], creds["user"])

    con, rows = panel_rows()
    print("ALL_ROWS")
    for r in rows:
        print(dict(r))

    bcx = next((r for r in rows if r.get("name") == "bcxtech"), None)
    xboom = next((r for r in rows if r.get("name") in ("XBoom", "xboom")), None)

    if not bcx:
        print("WARN no bcxtech template row")
        pid = 1
        accept = "127.0.0.1"
    else:
        pid = bcx["pid"]
        accept = bcx.get("accept") or "127.0.0.1"
        print("TEMPLATE bcxtech pid=", pid, "accept=", accept)

    # 删除可能错误的 XBoom 记录后按 bcxtech 同 pid 重建
    con.execute("delete from databases where name in ('XBoom','xboom')")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con.execute(
        "insert into databases (pid, name, username, password, accept, ps, addtime) "
        "values (?, ?, ?, ?, ?, ?, ?)",
        (pid, creds["name"], creds["user"], creds["pass"], accept, "小爆使用统计", now),
    )
    con.commit()
    print("SQLITE_REINSERTED")

    _, rows2 = panel_rows()
    for r in rows2:
        print("AFTER", dict(r))

    # 尝试官方 API
    try_bt_add(creds["name"], creds["user"], creds["pass"], pid)

    _, rows3 = panel_rows()
    print("FINAL_COUNT", len(rows3))
    for r in rows3:
        print("FINAL", dict(r))

    # MySQL 侧确认
    root = mysql_root_pwd()
    for rp in (root, creds["pass"]):
        pass
    p = subprocess.run(
        [
            "/www/server/mysql/bin/mysql",
            f"-u{creds['user']}",
            f"-p{creds['pass']}",
            "-hlocalhost",
            "-e",
            f"SHOW DATABASES LIKE '%Boom%'; USE `{creds['name']}`; SHOW TABLES;",
        ],
        capture_output=True,
        timeout=20,
        text=True,
    )
    print("MYSQL_APP", p.stdout, p.stderr[:120])

    return 0


if __name__ == "__main__":
    sys.exit(main())
