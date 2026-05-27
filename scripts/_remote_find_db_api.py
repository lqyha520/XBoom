import os
import glob

for path in glob.glob("/www/server/panel/class/*.py"):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    if "AddDatabase" in text or "create_database" in text.lower():
        print(path)
