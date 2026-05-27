#!/usr/bin/env python3
import subprocess

panel_py = "/www/server/panel/pyenv/bin/python3"
script = """
import sys
sys.path.insert(0, '/www/server/panel/class')
import public
sql = public.M('databases')
# 删除重复，只保留小写 xboom 一条
sql.where('name=?', ('XBoom',)).delete()
rows = sql.select()
for r in rows:
    print('KEEP', r.get('id'), r.get('name'), r.get('username'), r.get('ps'))
"""

subprocess.run([panel_py, "-c", script], cwd="/www/server/panel", timeout=30)
subprocess.run(["/etc/init.d/bt", "restart"], timeout=60, capture_output=True)
print("panel_restarted")
