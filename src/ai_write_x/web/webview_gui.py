#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import webview
import threading
import time
import uvicorn
import asyncio
import platform
from pathlib import Path
import signal
import sys
import os
import secrets
import json
import traceback
from datetime import datetime

from src.ai_write_x.utils import log
from src.ai_write_x.utils.tray_manager import TrayManager
from src.ai_write_x.utils.icon_manager import WindowIconManager


class WebViewGUI:
    def __init__(self):
        self.server_thread = None
        self.server = None
        self.server_loop = None
        self.window = None
        self.main_ui_loaded = False
        self.server_port = self.find_free_port()
        with open("port.txt", "w") as f:
            f.write(str(self.server_port))
        self.tray_manager = TrayManager("AIWriteX")
        self.tray_thread = None

        # 设置托盘管理器的窗口管理器引用
        self.tray_manager.set_window_manager(self)
        self.icon_manager = WindowIconManager()

        self.is_shutting_down = False
        
        # 【新增】生成客户端安全令牌
        self.client_token = secrets.token_hex(16)

        # 设置Windows应用用户模型ID
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.iniwap.AIWriteX")

    def find_free_port(self):
        """获取系统可用空闲端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # 允许系统自动分配可用端口
            s.bind(('', 0))
            return s.getsockname()[1]

    def signal_handler(self, signum, frame):
        """处理系统信号"""
        print(f"接收到信号 {signum}，开始退出...")
        self.quit_application()
        sys.exit(0)

    def setup_signal_handlers(self):
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        if platform.system() == "Windows":
            signal.signal(signal.SIGBREAK, self.signal_handler)

    def write_crash_log(self, stage, error):
        try:
            base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
            log_dir = base_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            crash_file = log_dir / "desktop_crash.log"
            content = (
                f"[{datetime.now().isoformat(timespec='seconds')}] stage={stage}\n"
                f"error={repr(error)}\n"
                f"traceback=\n{traceback.format_exc()}\n"
                f"python={sys.version}\n"
                f"executable={sys.executable}\n"
                f"cwd={os.getcwd()}\n"
                f"platform={platform.platform()}\n"
                "-" * 80 + "\n"
            )
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    def quit_application(self):
        """完整的退出流程"""
        if self.is_shutting_down:
            return

        self.is_shutting_down = True
        
        # 0. 清理测试图片
        self.cleanup_test_images()

        try:
            # 1. 停止托盘
            if self.tray_manager:
                self.tray_manager.stop_tray()

            # 2. 停止后端服务和子进程
            self.stop_background_services()

            # 3. 关闭WebView窗口
            if self.window:
                try:
                    self.window.destroy()
                except Exception:
                    pass

        except Exception as e:
            print(f"退出时出错: {e}")
        finally:
            # 兜底强制退出
            os._exit(0)

    def stop_background_services(self):
        """停止后台线程、服务和子进程"""
        try:
            from src.ai_write_x.core.scheduler import scheduler_service

            scheduler_service.stop()
        except Exception:
            pass

        try:
            from src.ai_write_x.tools.mcp_manager import MCPManager

            MCPManager.get_instance().stop_all()
        except Exception:
            pass

        try:
            if self.server:
                self.server.should_exit = True
                self.server.force_exit = True
        except Exception:
            pass

        try:
            if self.server_loop and self.server_loop.is_running():
                self.server_loop.call_soon_threadsafe(lambda: None)
        except Exception:
            pass

        try:
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5.0)
        except Exception:
            pass

    def cleanup_test_images(self):
        """退出前清理测试生成的图片 (文件名以 test_ 开头)"""
        try:
            from src.ai_write_x.utils.path_manager import PathManager
            image_dir = PathManager.get_image_dir()
            if image_dir.exists():
                count = 0
                for file in image_dir.glob("test_*"):
                    try:
                        file.unlink()
                        count += 1
                    except:
                        pass
                if count > 0:
                    log.print_log(f"[Cleanup] 已自动清理 {count} 张测试预览图", "info")
        except Exception as e:
            print(f"清理测试图片出错: {e}")

    def start_server(self):
        """启动FastAPI服务器"""
        try:
            from src.ai_write_x.web.app import app

            config = uvicorn.Config(
                app, host="127.0.0.1", port=self.server_port, log_level="warning", access_log=False
            )
            self.server = uvicorn.Server(config)

            loop = asyncio.new_event_loop()
            self.server_loop = loop
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.server.serve())

        except Exception as e:
            self.write_crash_log("start_server", e)
            log.print_log(f"服务器启动失败: {str(e)}", "error")

    def check_server_ready(self, max_attempts=30):
        """检查服务器是否就绪"""
        import requests

        for attempt in range(max_attempts):
            try:
                response = requests.get(f"http://127.0.0.1:{self.server_port}/health", timeout=1)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def get_app_url(self):
        return f"http://127.0.0.1:{self.server_port}/?token={self.client_token}"

    def build_loading_html(self):
        return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AIWriteX</title>
  <style>
    html, body {
      margin: 0;
      height: 100%;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }
    body {
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .wrap {
      width: 100%;
      max-width: 420px;
      padding: 32px;
      text-align: center;
    }
    .title {
      font-size: 28px;
      font-weight: 600;
      margin-bottom: 12px;
    }
    .sub {
      font-size: 14px;
      color: #94a3b8;
      margin-bottom: 24px;
    }
    .bar {
      height: 4px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(148, 163, 184, 0.18);
    }
    .bar > div {
      width: 35%;
      height: 100%;
      background: linear-gradient(90deg, #38bdf8, #818cf8);
      animation: slide 1.1s ease-in-out infinite;
    }
    @keyframes slide {
      0% { transform: translateX(-130%); }
      100% { transform: translateX(360%); }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">AIWriteX</div>
    <div class="sub">正在启动桌面工作台...</div>
    <div class="bar"><div></div></div>
  </div>
</body>
</html>
"""

    def build_error_html(self, message):
        safe_message = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AIWriteX</title>
  <style>
    html, body {{
      margin: 0;
      height: 100%;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #111827;
      color: #e5e7eb;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .panel {{
      max-width: 520px;
      padding: 24px;
      border-radius: 12px;
      background: #1f2937;
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.28);
    }}
    .title {{
      font-size: 22px;
      font-weight: 600;
      margin-bottom: 10px;
    }}
    .sub {{
      color: #9ca3af;
      line-height: 1.6;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <div class="panel">
    <div class="title">AIWriteX 启动失败</div>
    <div class="sub">{safe_message}</div>
  </div>
</body>
</html>
"""

    def wait_for_server_and_load(self):
        if self.check_server_ready(max_attempts=120):
            self.main_ui_loaded = True
            if self.window:
                self.window.load_url(self.get_app_url())
        else:
            error_message = "本地 Web 服务启动超时，请检查 logs 目录中的错误日志。"
            self.write_crash_log("wait_for_server_and_load", RuntimeError(error_message))
            if self.window:
                self.window.load_html(self.build_error_html(error_message))

    def show_window(self):
        """显示主窗口"""
        try:
            if self.window:
                # 如果窗口存在，显示它
                try:
                    self.window.restore()
                except Exception:
                    pass
                self.window.show()
                # 更新托盘提示
                if self.tray_manager:
                    self.tray_manager.update_tooltip("运行中")
        except Exception as e:
            log.print_log(f"显示窗口时出错: {e}", "error")

    def hide_window(self):
        """隐藏窗口到托盘"""
        if self.is_shutting_down:
            return  # 退出过程中不显示通知

        if self.window:
            try:
                self.window.minimize()
            except Exception:
                pass

        # 通知用户已最小化到托盘
        if self.tray_manager:
            self.tray_manager.show_notification("AIWriteX", "已最小化到系统托盘")

    def on_window_closing(self):
        """窗口关闭事件处理"""
        self.quit_application()
        return True

    def start(self):
        """启动WebView应用"""
        try:
            # 设置信号处理器
            self.setup_signal_handlers()

            # 启动后端服务器
            self.server_thread = threading.Thread(target=self.start_server, daemon=True)
            self.server_thread.start()

            # 读取窗口模式设置（首次启动时使用默认值）
            window_config = self.get_window_config()

            # 先显示轻量加载页，等本地服务就绪后再切换到主界面
            window_kwargs = {
                "title": "AIWriteX",
                "html": self.build_loading_html(),
                "width": window_config["width"],
                "height": window_config["height"],
                "min_size": (1000, 700),
                "resizable": True,
                "maximized": window_config["maximized"],
                "fullscreen": False,  # 可选：如果需要真正全屏
            }

            # 创建WebView窗口
            # Linux 平台直接设置图标
            if platform.system() == "Linux" and Path(self.icon_manager.icon_path).exists():
                window_kwargs["icon"] = str(self.icon_manager.icon_path)

            self.window = webview.create_window(**window_kwargs)

            # Windows 平台异步设置图标
            if webview.windows:
                window = webview.windows[0]

                # 监听窗口加载完成事件
                def on_loaded():
                    if not self.main_ui_loaded:
                        return
                    time.sleep(0.05)
                    try:
                        # 可保证启动在最前面显示，但这样会有个缩放动画，非全屏
                        """
                        import win32gui
                        import win32con

                        hwnd = win32gui.FindWindow(None, "AIWriteX - 智能内容创作平台")
                        if hwnd:
                            win32gui.SetForegroundWindow(hwnd)
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.SetWindowPos(
                                hwnd,
                                win32con.HWND_TOPMOST,
                                0,
                                0,
                                0,
                                0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
                            )
                            win32gui.SetWindowPos(
                                hwnd,
                                win32con.HWND_NOTOPMOST,
                                0,
                                0,
                                0,
                                0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
                            )
                        """
                        # 触发自定义就绪事件
                        window.evaluate_js(f"window.APP_CLIENT_TOKEN = '{self.client_token}';")
                        window.evaluate_js("document.dispatchEvent(new Event('pywebviewready'))")
                        # Windows 图标设置
                        self.icon_manager.set_window_icon_windows()
                    except Exception:
                        pass

                window.events.loaded += on_loaded

            # 设置窗口关闭事件
            if hasattr(self.window, "events"):
                self.window.events.closing += self.on_window_closing

            threading.Thread(target=self.wait_for_server_and_load, daemon=True).start()

            # 延迟创建托盘图标
            def delayed_tray_creation():
                time.sleep(2.0)  # 等待窗口完全显示
                if self.tray_manager.create_tray_icon():
                    self.tray_thread = threading.Thread(
                        target=self.tray_manager.tray.run, daemon=True
                    )
                    self.tray_thread.start()

                    # 设置初始状态
                    self.tray_manager.update_tooltip("运行中")

            # 启动延迟托盘创建线程
            threading.Thread(target=delayed_tray_creation, daemon=True).start()

            # 启动WebView
            log.print_log("正在启动用户界面...", "info", False)
            webview.start(debug=False)
        except KeyboardInterrupt:
            self.quit_application()
        except Exception as e:
            self.write_crash_log("start", e)
            log.print_log(f"GUI启动失败: {str(e)}", "error")
            return

    def on_task_start(self):
        """任务开始时的托盘状态更新"""
        if self.tray_manager:
            self.tray_manager.set_icon_status("working")
            self.tray_manager.update_tooltip("正在生成内容...")

    def on_task_complete(self):
        """任务完成时的托盘状态更新"""
        if self.tray_manager:
            self.tray_manager.set_icon_status("normal")
            self.tray_manager.update_tooltip("运行中")
            self.tray_manager.show_notification("AIWriteX", "内容生成完成")

    def on_task_error(self, error_msg):
        """任务出错时的托盘状态更新"""
        if self.tray_manager:
            self.tray_manager.set_icon_status("error")
            self.tray_manager.update_tooltip("任务执行出错")
            self.tray_manager.show_notification("AIWriteX", f"任务执行出错: {error_msg}")

    def get_window_mode_from_js(self):
        """从前端 localStorage 读取窗口模式设置"""
        try:
            if self.window:
                # 执行 JavaScript 代码读取 localStorage
                mode = self.window.evaluate_js(
                    """
                    try {
                        return localStorage.getItem('aiwritex_window_mode') || 'STANDARD';
                    } catch (e) {
                        return 'STANDARD';
                    }
                """
                )
                return mode
        except Exception:
            return "STANDARD"

    def get_window_config(self):
        """获取窗口配置"""
        try:
            from src.ai_write_x.utils.path_manager import PathManager
            import json

            ui_config_file = PathManager.get_config_dir() / "ui_config.json"
            if ui_config_file.exists():
                config = json.loads(ui_config_file.read_text(encoding="utf-8"))
                mode = config.get("windowMode", "STANDARD")

                if mode == "MAXIMIZED":
                    return {"width": 1400, "height": 900, "maximized": True}
                else:
                    return {"width": 1400, "height": 900, "maximized": False}
        except Exception as e:
            log.print_log(f"读取 UI 配置失败: {e}", "warning")

        return {"width": 1400, "height": 900, "maximized": False}


def gui_start():
    """启动WebView GUI的入口函数"""
    try:
        gui = WebViewGUI()
        gui.start()
    except KeyboardInterrupt:
        log.print_log("用户中断程序", "info")
    except Exception as e:
        try:
            base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
            log_dir = base_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            crash_file = log_dir / "desktop_crash.log"
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now().isoformat(timespec='seconds')}] stage=gui_start\\n"
                    f"error={repr(e)}\\n"
                    f"traceback=\\n{traceback.format_exc()}\\n"
                    + "-" * 80 + "\\n"
                )
        except Exception:
            pass
        log.print_log(f"GUI启动失败: {str(e)}", "error")


if __name__ == "__main__":
    gui_start()
