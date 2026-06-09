#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import platform
import threading
from pathlib import Path
from . import utils


class WindowIconManager:
    """Manage desktop window icon and native window chrome details."""

    def __init__(self):
        self.icon_path = self._get_icon_path()

    def _get_icon_path(self):
        gui_dir = Path(__file__).parent.parent / "assets"

        if platform.system() == "Windows":
            return utils.get_res_path("branding/app_icon.ico", str(gui_dir))
        if platform.system() == "Darwin":
            return utils.get_res_path("branding/app_icon.png", str(gui_dir))
        return utils.get_res_path("branding/app_icon.png", str(gui_dir))

    def _find_window_handle(self, window_title="小爆来咯"):
        if platform.system() != "Windows":
            return None

        try:
            import win32gui

            windows = []

            def enum_windows_proc(hwnd, lParam):
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if window_title in window_text:
                        lParam.append(hwnd)
                return True

            win32gui.EnumWindows(enum_windows_proc, windows)
            return windows[0] if windows else None
        except Exception:
            return None

    def apply_windows_titlebar_theme(self, window_title="小爆来咯"):
        """Tint the native Windows title bar to match the warm paper UI theme."""
        hwnd = self._find_window_handle(window_title)
        if not hwnd:
            return

        try:
            import ctypes
            import win32con
            import win32gui

            # COLORREF is 0x00bbggrr. These map to #fbf7e8, #1f2b36, #d8cfaa.
            titlebar_color = ctypes.c_int(0x00E8F7FB)
            text_color = ctypes.c_int(0x00362B1F)
            border_color = ctypes.c_int(0x00AACFD8)

            dwmapi = ctypes.windll.dwmapi
            # Windows 11 attributes. Older hosts safely ignore failures.
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(titlebar_color), ctypes.sizeof(titlebar_color))
            dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
            dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_color), ctypes.sizeof(border_color))

            win32gui.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER
                | win32con.SWP_FRAMECHANGED,
            )
            win32gui.InvalidateRect(hwnd, None, True)
            win32gui.UpdateWindow(hwnd)
        except Exception:
            pass

    def set_window_icon_windows(self, window_title="小爆来咯"):
        if platform.system() != "Windows":
            return

        try:
            import win32gui
            import win32con

            hwnd = self._find_window_handle(window_title)
            if not hwnd:
                return

            self.apply_windows_titlebar_theme(window_title)
            if not Path(self.icon_path).exists():
                return

            icon = win32gui.LoadImage(
                0,
                str(self.icon_path),
                win32con.IMAGE_ICON,
                0,
                0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )

            if icon:
                win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, icon)
                win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, icon)

            win32gui.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER
                | win32con.SWP_FRAMECHANGED,
            )
            win32gui.InvalidateRect(hwnd, None, True)
            win32gui.UpdateWindow(hwnd)
        except Exception:
            pass

    def setup_icon_async(self, window_title="小爆来咯"):
        if platform.system() == "Windows":
            threading.Thread(
                target=self.set_window_icon_windows, args=(window_title,), daemon=True
            ).start()
