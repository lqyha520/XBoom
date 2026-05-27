# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

udf = Path(os.environ.get("LOCALAPPDATA", ".")) / "AIWriteX" / "WebView2"
udf.mkdir(parents=True, exist_ok=True)
os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(udf)
print("UDF:", udf)

import webview

w = webview.create_window("test", html="<h1>OK</h1>", width=400, height=300)
webview.start(debug=False)
print("ok")
