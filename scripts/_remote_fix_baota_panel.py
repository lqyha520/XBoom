#!/usr/bin/env python3
"""修复宝塔 databases 表 pid，使 XBoom 在面板列表显示"""
import json
import os
import sqlite3

PANEL_DB = "/www/server/panel/data/default.db"
con = sqlite3.connect(PANEL_DB)

# 常见：pid 为 MySQL 实例 ID，0 时部分版本不展示
rows = con.execute("select id,pid,name from databases").fetchall()
print("before", rows)

pid = 0
# 从 panel 数据目录找 mysql 实例 id
for path in (
    "/www/server/panel/data/db/mysql.json",
    "/www/server/panel/data/db.json",
):
    if os.path.isfile(path):
        try:
            data = json.loads(open(path, encoding="utf-8").read())
            print("json_file", path, str(data)[:300])
            if isinstance(data, list) and data:
                pid = data[0].get("id", data[0].get("pid", 0))
            elif isinstance(data, dict):
                pid = data.get("id", data.get("pid", 0))
        except Exception as e:
            print("json_err", e)

# 宝塔 8.x：databases.pid 常指向本机 MySQL，无其它库时用 1
if pid == 0:
    pid = 1

con.execute("update databases set pid=? where name='XBoom'", (pid,))
con.commit()
rows2 = con.execute("select id,pid,name,username,addtime from databases").fetchall()
print("after", rows2)
print("FIXED_PID", pid)
