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
import inspect
print('sig', inspect.signature(public.en_crypt))
p='4LBZ8n88Ijlyr6Lh'
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
