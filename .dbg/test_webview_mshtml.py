# -*- coding: utf-8 -*-
import webview
w = webview.create_window("test", html="<h1>mshtml</h1>", width=400, height=300)
webview.start(debug=False, gui="mshtml")
print("ok")
