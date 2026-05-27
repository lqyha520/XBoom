import subprocess

panel_py = "/www/server/panel/pyenv/bin/python3"
proc = subprocess.run(
    [
        panel_py,
        "-c",
        """
import sys
sys.path.insert(0,'/www/server/panel/class')
import public
p='4LBZ8n88Ijlyr6Lh'
for key in ('BT-0x', 'bt', 'database', 'mysql', 'db', ''):
    try:
        e = public.en_crypt(key, p)
        if e and e != p.encode():
            print('key', repr(key), '->', e[:80] if isinstance(e,bytes) else e)
    except Exception as ex:
        pass
# 尝试 M 模型
try:
    import database as dbmod
    db = dbmod.database()
    print('methods', [x for x in dir(db) if 'pass' in x.lower() or 'crypt' in x.lower()][:20])
except Exception as e:
    print('dbmod', e)
""",
    ],
    cwd="/www/server/panel",
    capture_output=True,
    text=True,
    timeout=30,
)
print(proc.stdout)
