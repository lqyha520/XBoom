# -*- coding: utf-8 -*-
import webview
import sys

print("python:", sys.version)
print("platform:", sys.platform)

try:
    w = webview.create_window("WebView2 test", html="<h1>OK</h1>", width=400, height=300)
    webview.start(debug=False)
    print("webview exited normally")
except Exception as e:
    print("FAILED:", type(e).__name__, e)
    sys.exit(1)
