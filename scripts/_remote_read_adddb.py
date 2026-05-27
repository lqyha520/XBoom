import subprocess

panel_py = "/www/server/panel/pyenv/bin/python3"
proc = subprocess.run(
    [
        panel_py,
        "-c",
        """
import inspect
import sys
sys.path.insert(0,'/www/server/panel/class')
import database
src = inspect.getsource(database.database.AddDatabase)
print(src[:2500])
""",
    ],
    cwd="/www/server/panel",
    capture_output=True,
    text=True,
    timeout=30,
)
print(proc.stdout)
print(proc.stderr[:300])
