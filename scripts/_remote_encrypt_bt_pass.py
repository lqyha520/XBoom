#!/usr/bin/env python3
import sqlite3
import subprocess

plain = open("/www/wwwroot/updates.bcxtech.cn/stats/config.php", encoding="utf-8").read()
import re
pwd = re.search(r"'db_pass'\s*=>\s*'([^']*)'", plain).group(1)

script = f"""
import sys
sys.path.insert(0, '/www/server/panel/class')
import public
enc = public.en_crypt(pwd, 'bcrypt') if hasattr(public, 'en_crypt') else None
if not enc and hasattr(public, 'encrypt'):
    enc = public.encrypt(pwd)
if not enc:
    # 常见宝塔加密
    import PluginLoader
    enc = PluginLoader.db_encrypt(pwd)
print('ENC', enc)
"""
# simpler - call panel database sync
panel_py = "/www/server/panel/pyenv/bin/python3"
proc = subprocess.run(
    [panel_py, "-c", """
import sys
sys.path.insert(0,'/www/server/panel/class')
import public
p='4LBZ8n88Ijlyr6Lh'
for fn in ('en_crypt','encrypt','db_encrypt'):
    if hasattr(public, fn):
        try:
            print(fn, getattr(public, fn)(p))
        except Exception as e:
            print(fn,'err',e)
"""],
    cwd="/www/server/panel",
    capture_output=True,
    text=True,
    timeout=30,
)
print(proc.stdout)
print(proc.stderr[:400])

# 读 bcxtech 密码格式确认
con = sqlite3.connect("/www/server/panel/data/db/database.db")
for row in con.execute("select id,name,password from databases"):
    print("ROW", row)
