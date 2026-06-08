#!/usr/bin/env python3
import subprocess

from ops_secrets import require_env

panel_py = "/www/server/panel/pyenv/bin/python3"
db_password = require_env("XBOOM_DB_PASSWORD")

script = """
import sys
sys.path.insert(0, '/www/server/panel/class')
import public

# 与 bcxtech 完全一致字段，仅改名称/用户/备注；密码用面板加密
pwd = {db_password!r}
sql = public.M('databases')
sql.where('name in (?)', ('XBoom', 'xboom')).delete()

# 复制 bcxtech
bcx = sql.where('name=?', ('bcxtech',)).find()
if not bcx:
    print('no bcxtech'); raise SystemExit(1)

import time
data = dict(bcx)
del data['id']
data['name'] = 'xboom'
data['username'] = 'xboom'
data['password'] = pwd
data['ps'] = '小爆使用统计'
data['addtime'] = time.strftime('%Y-%m-%d %H:%M:%S')
# 插入
new_id = sql.insert(data)
print('insert_id', new_id)

# 列表（面板 API 同源）
for r in sql.select():
    print('LIST', r.get('name'), r.get('username'), r.get('ps'))
""".format(db_password=db_password)

proc = subprocess.run(
    [panel_py, "-c", script],
    cwd="/www/server/panel",
    capture_output=True,
    text=True,
    timeout=60,
)
print(proc.stdout)
print(proc.stderr[:500] if proc.stderr else "")
