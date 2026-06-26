#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""系统托盘管理器 - 使用 win32gui 原生 API（兼容 PyInstaller 打包）"""

import os
import sys
import threading
import logging
from pathlib import Path

_tray_log = logging.getLogger("tray")


def _log(msg):
    """同时输出到 console 和 logger"""
    print(f"[Tray] {msg}")
    _tray_log.info(msg)


class TrayManager:
    """基于 win32gui 的系统托盘（公共接口不变，webview_gui.py 无需改动）"""

    _WM_TRAYICON = 0x0400 + 2000  # WM_APP + 2000
    _ID_TRAY = 1

    def __init__(self, app_name="AIWriteX"):
        self.app_name = app_name
        self.icon_path = self._get_icon_path()
        self.window_manager = None
        self.is_stopping = False
        self._hwnd = None
        self._hicon = None
        self._thread = None
        self._tooltip = f"{app_name} - 智能内容创作平台"
        self._notify_id = None

    # ---- 图标路径 ----

    def _get_icon_path(self):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base = sys._MEIPASS
            pkg_prefix = "src/ai_write_x/assets"
        else:
            base = Path(__file__).parent.parent / "assets"
            pkg_prefix = ""

        # 优先 ICO（LoadImage 原生支持），其次 PNG
        for name in ("app_icon.ico", "app_icon.png"):
            rel = f"{pkg_prefix}/branding/{name}" if pkg_prefix else f"branding/{name}"
            candidate = Path(base) / rel
            if candidate.exists():
                return candidate
        return None

    # ---- 公共接口 ----

    def set_window_manager(self, window_manager):
        self.window_manager = window_manager

    def create_tray_icon(self):
        """预加载图标句柄"""
        try:
            _log(f"图标路径: {self.icon_path}")
            hicon = self._load_hicon()
            if not hicon:
                _log("无法加载图标句柄，使用系统默认图标")
                hicon = self._load_default_hicon()
            self._hicon = hicon
            _log(f"图标句柄加载成功: {hicon}")
            return True
        except Exception as e:
            _log(f"创建托盘图标失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_tray(self):
        """启动托盘（在独立线程中创建窗口 + 注册图标 + 消息循环）"""
        if not self._hicon:
            _log("图标未就绪，跳过启动")
            return

        _log("启动托盘线程...")
        self._thread = threading.Thread(target=self._tray_main, daemon=False)
        self._thread.start()

    def stop_tray(self):
        self.is_stopping = True
        if self._hwnd:
            import win32con
            import win32gui
            win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._remove_icon()

    def update_tooltip(self, message):
        self._tooltip = f"{self.app_name} - {message}"
        if self._hwnd:
            self._modify_icon()

    def show_notification(self, title, message, timeout=3):
        if not self._hwnd:
            return
        try:
            import win32gui
            win32gui.Shell_NotifyIcon(
                win32gui.NIM_MODIFY,
                (
                    self._hwnd,
                    self._ID_TRAY,
                    win32gui.NIF_INFO,
                    0,
                    self._hicon,
                    self._tooltip,
                    message[:255],
                    timeout * 1000,
                    title[:63],
                    win32gui.NIIF_NONE,
                ),
            )
        except Exception as e:
            _log(f"显示通知失败: {e}")

    def set_icon_status(self, status="normal"):
        """切换图标状态"""
        try:
            if status == "working":
                hicon = self._create_status_hicon((0, 200, 0))
            elif status == "error":
                hicon = self._create_status_hicon((220, 0, 0))
            else:
                hicon = self._load_hicon() or self._load_default_hicon()

            if hicon and self._hwnd:
                old = self._hicon
                self._hicon = hicon
                self._modify_icon()
                if old:
                    import win32gui
                    try:
                        win32gui.DestroyIcon(old)
                    except Exception:
                        pass
        except Exception as e:
            _log(f"设置图标状态失败: {e}")

    # ---- 内部实现 ----

    def _load_hicon(self):
        """加载图标文件为 HICON"""
        import win32gui
        import win32con

        if not self.icon_path or not self.icon_path.exists():
            return None

        path_str = str(self.icon_path)

        # ICO 文件：LoadImage 直接支持
        if path_str.lower().endswith(".ico"):
            try:
                hicon = win32gui.LoadImage(
                    0, path_str,
                    win32con.IMAGE_ICON,
                    0, 0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
                )
                if hicon:
                    _log(f"LoadImage ICO 成功: {hicon}")
                    return hicon
            except Exception as e:
                _log(f"LoadImage ICO 失败: {e}")

        # PNG 或 ICO 回退：用 PIL 转为 ICO 再加载
        return self._png_to_hicon()

    def _png_to_hicon(self):
        """PNG -> 临时 ICO -> HICON"""
        import win32gui
        import win32con
        import tempfile

        try:
            from PIL import Image

            img_path = self.icon_path
            if not img_path or not img_path.exists():
                return None

            img = Image.open(img_path).convert("RGBA")
            # 保存为临时 ICO
            tmp_dir = tempfile.gettempdir()
            tmp_ico = os.path.join(tmp_dir, f"xb_tray_{os.getpid()}.ico")
            sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
            icons = [img.resize(s, Image.Resampling.LANCZOS) for s in sizes]
            icons[0].save(tmp_ico, format="ICO", sizes=sizes, append_images=icons[1:])

            hicon = win32gui.LoadImage(
                0, tmp_ico,
                win32con.IMAGE_ICON,
                0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
            if hicon:
                _log(f"PNG->ICO->HICON 成功: {hicon}")
                return hicon
            _log("LoadImage 临时 ICO 返回空")
        except Exception as e:
            _log(f"PNG 转 ICO 失败: {e}")
            import traceback
            traceback.print_exc()

        return None

    def _load_default_hicon(self):
        """加载系统默认应用图标"""
        import win32gui
        import win32con
        try:
            hicon = win32gui.LoadImage(
                0, win32con.OIC_SAMPLE,
                win32con.IMAGE_ICON,
                0, 0,
                win32con.LR_SHARED | win32con.LR_DEFAULTSIZE,
            )
            if hicon:
                _log(f"使用系统默认图标: {hicon}")
                return hicon
        except Exception:
            pass

        # 最终回退：用 PIL 创建简单图标
        return self._create_fallback_hicon()

    def _create_fallback_hicon(self):
        """用 PIL 创建一个简单的蓝色图标"""
        import tempfile
        import win32gui
        import win32con
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (32, 32), (37, 99, 235, 255))
            draw = ImageDraw.Draw(img)
            draw.text((4, 8), "XB", fill=(255, 255, 255, 255))

            tmp_ico = os.path.join(tempfile.gettempdir(), f"xb_default_{os.getpid()}.ico")
            img.save(tmp_ico, format="ICO", sizes=[(16, 16), (32, 32)])

            hicon = win32gui.LoadImage(
                0, tmp_ico,
                win32con.IMAGE_ICON,
                0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
            if hicon:
                _log(f"使用回退图标: {hicon}")
                return hicon
        except Exception as e:
            _log(f"创建回退图标失败: {e}")
        return None

    def _create_status_hicon(self, dot_color):
        """在基础图标上叠加状态圆点"""
        import tempfile
        import win32gui
        import win32con
        try:
            from PIL import Image, ImageDraw

            if self.icon_path and self.icon_path.exists():
                base = Image.open(self.icon_path).convert("RGBA").resize(
                    (32, 32), Image.Resampling.LANCZOS
                )
            else:
                base = Image.new("RGBA", (32, 32), (37, 99, 235, 255))

            draw = ImageDraw.Draw(base)
            draw.ellipse([22, 22, 31, 31], fill=dot_color + (255,))

            tmp_ico = os.path.join(tempfile.gettempdir(), f"xb_status_{os.getpid()}.ico")
            base.save(tmp_ico, format="ICO", sizes=[(16, 16), (32, 32)])

            hicon = win32gui.LoadImage(
                0, tmp_ico,
                win32con.IMAGE_ICON,
                0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
            return hicon if hicon else self._hicon
        except Exception:
            return self._hicon

    # ---- 窗口和消息循环 ----

    def _tray_main(self):
        """托盘主线程：注册窗口类 -> 创建隐藏窗口 -> 注册图标 -> 消息循环"""
        import win32gui
        import win32con
        import win32api

        wc_name = f"XBoomTray_{os.getpid()}"

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == self._WM_TRAYICON:
                if lparam == win32con.WM_LBUTTONDOWN or lparam == win32con.WM_LBUTTONDBLCLK:
                    self._show_window()
                elif lparam == win32con.WM_RBUTTONUP:
                    self._show_popup_menu(hwnd)
            elif msg == win32con.WM_CLOSE:
                self._remove_icon()
                win32gui.DestroyWindow(hwnd)
                win32gui.PostQuitMessage(0)
                return 0
            elif msg == win32con.WM_COMMAND:
                cmd = win32api.LOWORD(wparam)
                if cmd == 1001:
                    self._show_window()
                elif cmd == 1002:
                    self._quit_application()
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        try:
            # 注册窗口类
            wc = win32gui.WNDCLASS()
            wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = wc_name
            wc.lpfnWndProc = wnd_proc
            wc_class = win32gui.RegisterClass(wc)
            _log(f"窗口类注册成功: {wc_class}")
        except Exception as e:
            _log(f"窗口类注册失败: {e}")
            # 可能已注册，继续
            pass

        try:
            # 创建消息窗口（不可见）
            self._hwnd = win32gui.CreateWindow(
                wc_name, "XBoomTrayMsgWindow",
                0, 0, 0, 0, 0,
                0, 0, wc.hInstance, None,
            )
            if not self._hwnd:
                _log("CreateWindow 返回空!")
                return
            _log(f"消息窗口创建成功: hwnd={self._hwnd}")
        except Exception as e:
            _log(f"CreateWindow 失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 注册托盘图标
        self._add_icon()
        _log("托盘图标已注册到系统托盘!")

        # 消息循环
        try:
            win32gui.PumpMessages()
        except Exception as e:
            _log(f"消息循环异常: {e}")

        _log("托盘线程退出")

    def _add_icon(self):
        """添加托盘图标"""
        import win32gui
        try:
            win32gui.Shell_NotifyIcon(
                win32gui.NIM_ADD,
                (
                    self._hwnd,
                    self._ID_TRAY,
                    win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
                    self._WM_TRAYICON,
                    self._hicon,
                    self._tooltip[:127],
                ),
            )
            _log("Shell_NotifyIcon NIM_ADD 成功")
        except Exception as e:
            _log(f"Shell_NotifyIcon NIM_ADD 失败: {e}")
            import traceback
            traceback.print_exc()

    def _modify_icon(self):
        """修改托盘图标"""
        import win32gui
        try:
            win32gui.Shell_NotifyIcon(
                win32gui.NIM_MODIFY,
                (
                    self._hwnd,
                    self._ID_TRAY,
                    win32gui.NIF_ICON | win32gui.NIF_TIP,
                    0,
                    self._hicon,
                    self._tooltip[:127],
                ),
            )
        except Exception:
            pass

    def _remove_icon(self):
        """移除托盘图标"""
        import win32gui
        try:
            if self._hwnd:
                win32gui.Shell_NotifyIcon(
                    win32gui.NIM_DELETE,
                    (self._hwnd, self._ID_TRAY, 0, 0, 0, ""),
                )
                _log("托盘图标已移除")
        except Exception:
            pass
        if self._hicon:
            try:
                import win32gui
                win32gui.DestroyIcon(self._hicon)
            except Exception:
                pass
            self._hicon = None

    def _show_popup_menu(self, hwnd):
        """显示右键弹出菜单"""
        import win32gui
        import win32con
        import win32api

        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1001, f"显示 {self.app_name}")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1002, "退出")

        # 必须设置前台窗口，否则菜单可能无法正常关闭
        win32gui.SetForegroundWindow(hwnd)

        pos = win32api.GetCursorPos()
        cmd = win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD,
            pos[0], pos[1], 0, hwnd, None,
        )
        win32gui.PostMessage(hwnd, win32con.WM_COMMAND, cmd, 0)
        win32gui.DestroyMenu(menu)

    # ---- 回调 ----

    def _show_window(self, icon=None, item=None):
        if self.window_manager:
            self.window_manager.show_window()

    def _quit_application(self, icon=None, item=None):
        if self.window_manager:
            self.window_manager.quit_application()
        else:
            os._exit(0)
