#!/usr/bin/env python3
import glob
import os
import sqlite3

print("=== databases table ===")
con = sqlite3.connect("/www/server/panel/data/default.db")
for row in con.execute("select * from databases"):
    print(row)

print("\n=== grep bcxtech in panel data ===")
for path in glob.glob("/www/server/panel/data/**/*", recursive=True):
    if not os.path.isfile(path):
        continue
    try:
        if os.path.getsize(path) > 2_000_000:
            continue
        data = open(path, "rb").read()
        if b"bcxtech" in data:
            print("FOUND", path, "size", os.path.getsize(path))
    except Exception:
        pass

print("\n=== json under panel/data/db ===")
for path in glob.glob("/www/server/panel/data/**/*.json", recursive=True):
    try:
        t = open(path, encoding="utf-8", errors="ignore").read()
        if "bcxtech" in t or "database" in t.lower():
            print("JSON", path, t[:400])
    except Exception:
        pass
