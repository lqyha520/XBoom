#!/usr/bin/env python3
"""写入宝塔 database.db（UI 列表读这个库，不是 default.db）"""
import re
import sqlite3
from datetime import datetime

DB_PATH = "/www/server/panel/data/db/database.db"
CONFIG_PHP = "/www/wwwroot/updates.bcxtech.cn/stats/config.php"

text = open(CONFIG_PHP, encoding="utf-8").read()
db_name = re.search(r"'db_name'\s*=>\s*'([^']*)'", text).group(1)
db_user = re.search(r"'db_user'\s*=>\s*'([^']*)'", text).group(1)
db_pass = re.search(r"'db_pass'\s*=>\s*'([^']*)'", text).group(1)

con = sqlite3.connect(DB_PATH)
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'").fetchall()]
print("tables", tables)

for t in tables:
    cols = [r[1] for r in con.execute(f"pragma table_info({t})").fetchall()]
    print("TABLE", t, "cols", cols)
    rows = con.execute(f"select * from {t}").fetchall()
    for row in rows:
        print("  ROW", row)

# 找 bcxtech 所在表
bcx = None
target_table = None
for t in tables:
    cols = [r[1] for r in con.execute(f"pragma table_info({t})").fetchall()]
    if "name" not in cols:
        continue
    for row in con.execute(f"select * from {t}"):
        d = dict(zip(cols, row))
        if d.get("name") == "bcxtech":
            bcx = d
            target_table = t
            break
    if bcx:
        break

if not bcx:
    print("ERROR: bcxtech not found in database.db")
    raise SystemExit(1)

print("BCX_TEMPLATE", bcx)
print("TARGET_TABLE", target_table)

# 删除旧 XBoom
cols = [r[1] for r in con.execute(f"pragma table_info({target_table})").fetchall()]
name_col = "name"
for c in cols:
    if c.lower() == "name":
        name_col = c
        break

con.execute(
    f"delete from {target_table} where {name_col} in ('XBoom','xboom')"
)

# 按 bcxtech 行结构插入
new = dict(bcx)
# 去掉 id 自增
if "id" in new:
    del new["id"]
new[name_col] = db_name
if "username" in new:
    new["username"] = db_user
elif "db_user" in new:
    new["db_user"] = db_user
if "password" in new:
    new["password"] = db_pass
if "ps" in new:
    new["ps"] = "小爆使用统计"
if "addtime" in new:
    new["addtime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

keys = list(new.keys())
vals = [new[k] for k in keys]
placeholders = ",".join("?" * len(keys))
colnames = ",".join(keys)
con.execute(f"insert into {target_table} ({colnames}) values ({placeholders})", vals)
con.commit()

print("INSERTED")
for row in con.execute(f"select * from {target_table}"):
    print("ALL", row)

# 清理 default.db 里重复（避免混淆）
try:
    d2 = sqlite3.connect("/www/server/panel/data/default.db")
    d2.execute("delete from databases where name in ('XBoom','xboom')")
    d2.commit()
    print("cleaned default.db old row")
except Exception as e:
    print("default.db clean skip", e)

print("DONE")
