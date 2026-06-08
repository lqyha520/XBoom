import subprocess

from ops_secrets import require_env

panel_py = "/www/server/panel/pyenv/bin/python3"
db_password = require_env("XBOOM_DB_PASSWORD")

proc = subprocess.run(
    [
        panel_py,
        "-c",
        f"""
import sys
sys.path.insert(0,'/www/server/panel/class')
import public
import inspect
print('sig', inspect.signature(public.en_crypt))
p={db_password!r}
try:
    e = public.en_crypt(p, 'bcrypt')
    print('enc1', e)
except Exception as ex:
    print('e1', ex)
try:
    e = public.en_crypt('bcrypt', p)
    print('enc2', e)
except Exception as ex:
    print('e2', ex)
""",
    ],
    cwd="/www/server/panel",
    capture_output=True,
    text=True,
    timeout=30,
)
print(proc.stdout)
print(proc.stderr[:300])
