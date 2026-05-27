#!/usr/bin/env python3
"""通过宝塔官方 AddDatabase 添加 xboom，确保面板列表显示"""
import re
import sqlite3
import subprocess

CONFIG_PHP = "/www/wwwroot/updates.bcxtech.cn/stats/config.php"
text = open(CONFIG_PHP, encoding="utf-8").read()
db_pass = re.search(r"'db_pass'\s*=>\s*'([^']*)'", text).group(1)

script = f"""
import sys
sys.path.insert(0, '/www/server/panel/class')
import public
import database

class _Get:
    def __init__(self, data):
        self._d = data
        for k, v in data.items():
            setattr(self, k.replace('/', '_'), v)
    def __getitem__(self, k):
        return self._d[k]
    def get(self, k, default=0):
        return self._d.get(k, default)

# 先删手动插入的 XBoom 行（保留 bcxtech）
public.M('databases').where('name IN (?)', ('XBoom', 'xboom')).delete()

db = database.database()
get = _Get({{
    'name': 'xboom',
    'db_user': 'xboom',
    'password': '{db_pass}',
    'dataAccess': '127.0.0.1',
    'address': '127.0.0.1',
    'ps': '小爆使用统计',
    'sid': 0,
    'dtype': 'MySQL',
    'type': 'MySQL',
    'type_id': 0,
}})
result = db.AddDatabase(get)
print('RESULT', result)
rows = public.M('databases').select()
for r in rows:
    print('ROW', r)
"""

panel_py = "/www/server/panel/pyenv/bin/python3"
proc = subprocess.run(
    [panel_py, "-c", script],
    cwd="/www/server/panel",
    capture_output=True,
    text=True,
    timeout=120,
)
print(proc.stdout)
print(proc.stderr[:800] if proc.stderr else "")

# 若已存在库，AddDatabase 可能失败，检查列表
con = sqlite3.connect("/www/server/panel/data/db/database.db")
for row in con.execute("select id,name,username,ps from databases"):
    print("SQLITE", row)
