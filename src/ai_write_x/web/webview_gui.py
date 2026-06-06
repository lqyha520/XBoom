#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import webbrowser
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
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.utils.tray_manager import TrayManager
from src.ai_write_x.utils.icon_manager import WindowIconManager


class WebViewGUI:
    # 类级别单实例互斥锁
    _single_instance_mutex = None

    def __init__(self):
        # 单实例检测：如果已有实例运行，激活它并退出
        if not self._acquire_single_instance():
            log.print_log("检测到已有程序实例运行，激活现有窗口后退出", "warning")
            self._activate_existing_instance()
            sys.exit(0)

        self.server_thread = None
        self.server = None
        self.server_loop = None
        self.window = None
        self.main_ui_loaded = False
        self.server_port = self.find_free_port()
        with open("port.txt", "w") as f:
            f.write(str(self.server_port))
        self.tray_manager = TrayManager("小爆来咯")
        self.tray_thread = None

        # 设置托盘管理器的窗口管理器引用
        self.tray_manager.set_window_manager(self)
        self.icon_manager = WindowIconManager()

        self.is_shutting_down = False
        self._browser_gui_opened = False
        self._desktop_ui_ready = False

        # 【新增】生成客户端安全令牌
        self.client_token = secrets.token_hex(16)

        # 设置Windows应用用户模型ID
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.iniwap.AIWriteX")

    @classmethod
    def _acquire_single_instance(cls) -> bool:
        """尝试获取单实例互斥锁，返回True表示成功（无其他实例），False表示已有实例运行"""
        if sys.platform != "win32":
            return True
        try:
            import ctypes
            import ctypes.wintypes
            kernel32 = ctypes.windll.kernel32
            mutex_name = "Global\\XBoom_SingleInstance_Mutex"
            cls._single_instance_mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            # ERROR_ALREADY_EXISTS = 183
            if last_error == 183:
                cls._single_instance_mutex = None
                return False
            return True
        except Exception as e:
            log.print_log(f"单实例检测失败: {e}，跳过检测", "warning")
            return True

    @classmethod
    def _activate_existing_instance(cls):
        """激活已存在的程序窗口"""
        if sys.platform != "win32":
            return
        try:
            # 通过端口文件找到现有实例的端口
            port_file = Path("port.txt")
            if port_file.exists():
                port = port_file.read_text().strip()
                if port:
                    import urllib.request
                    try:
                        req = urllib.request.Request(
                            f"http://127.0.0.1:{port}/api/system/bring-to-front",
                            method="POST",
                            data=b"",
                        )
                        urllib.request.urlopen(req, timeout=3)
                    except Exception:
                        pass
        except Exception as e:
            log.print_log(f"激活现有实例失败: {e}", "warning")

    def find_free_port(self):
        """获取系统可用空闲端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # 允许系统自动分配可用端口
            s.bind(('', 0))
            return s.getsockname()[1]

    def _browser_gui_flag_path(self) -> Path:
        return PathManager.get_log_dir() / "use_browser_gui.flag"

    def _should_use_browser_gui(self) -> bool:
        forced_browser = os.environ.get("AIWRITEX_BROWSER_GUI", "").strip().lower()
        if forced_browser in ("1", "true", "yes", "on"):
            return True
        return False

    def _mark_browser_gui_preferred(self):
        if not self._browser_fallback_allowed():
            return
        try:
            self._browser_gui_flag_path().write_text("1", encoding="utf-8")
        except Exception:
            pass

    def _browser_fallback_allowed(self) -> bool:
        forced = os.environ.get("AIWRITEX_BROWSER_GUI", "").strip().lower()
        if forced in ("0", "false", "no", "off"):
            return False
        disabled = os.environ.get("AIWRITEX_DISABLE_BROWSER_FALLBACK", "").strip().lower()
        return disabled not in ("1", "true", "yes", "on")

    def _get_webview_storage_path(self) -> Path:
        if self._should_use_browser_gui():
            session_id = os.environ.get("AIWRITEX_SESSION") or str(os.getpid())
            storage = PathManager.get_app_data_dir() / "pywebview" / session_id
        else:
            storage = PathManager.get_app_data_dir() / "pywebview" / "desktop"
        storage.mkdir(parents=True, exist_ok=True)
        return storage

    def _prepare_windows_desktop_env(self):
        """缓解 WebView2 0x8007139F（DPI/用户数据目录冲突）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            try:
                # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except Exception:
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def _configure_webview2(self):
        storage = self._get_webview_storage_path()
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = str(storage)

        # 禁止 WebView2 后台节流：内容创作/定时任务执行时不会因窗口失焦而被暂停
        # --disable-background-timer-throttling: 禁止后台定时器节流
        # --disable-backgrounding-occluded-windows: 禁止被遮挡窗口降级
        # --disable-features=CalculateNativeWinOcclusion: 禁止Windows原生遮挡检测
        extra_args = (
            "--disable-background-timer-throttling "
            "--disable-backgrounding-occluded-windows "
            "--disable-features=CalculateNativeWinOcclusion"
        )
        existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        if existing:
            extra_args = existing + " " + extra_args
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = extra_args

    def _write_startup_url_file(self):
        try:
            log_dir = PathManager.get_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "startup.url").write_text(self.get_app_url(), encoding="utf-8")
        except Exception:
            pass

    def _inject_desktop_scripts(self):
        if not self.window or not self.main_ui_loaded:
            return
        try:
            self.window.evaluate_js(f"window.APP_CLIENT_TOKEN = '{self.client_token}';")
            self.window.evaluate_js("document.dispatchEvent(new Event('pywebviewready'))")
            self.window.evaluate_js(
                "if (window.updateChecker) { window.updateChecker.scheduleStartupPolicyCheck?.() "
                "|| window.updateChecker.checkStartupPolicy(); }"
            )
            self._desktop_ui_ready = True
        except Exception:
            pass

    def _switch_to_browser_fallback(self):
        """关闭空白桌面窗并改用系统浏览器。"""
        if not self._browser_fallback_allowed():
            log.print_log(
                "桌面窗口加载异常。已禁用浏览器回退，请安装/修复 WebView2 运行时后重试。",
                "error",
            )
            return
        self._mark_browser_gui_preferred()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
        self._open_system_browser()

    def _open_system_browser(self):
        if self._browser_gui_opened or self.is_shutting_down:
            return
        if not self.check_server_ready(max_attempts=120):
            log.print_log("本地 Web 服务未就绪，无法打开浏览器界面", "error")
            return
        self._browser_gui_opened = True
        url = self.get_app_url()
        self._write_startup_url_file()
        webbrowser.open(url)
        log.print_log(
            "WebView2 桌面窗口不可用，已在系统浏览器打开界面。"
            " 若需恢复桌面窗口，请删除 logs/use_browser_gui.flag 并修复 WebView2 运行环境。",
            "warning",
        )
        if self.tray_manager:
            self.tray_manager.show_notification(
                "小爆来咯",
                "已在系统浏览器中打开（WebView2 不可用）",
            )

    def _browser_fallback_watchdog(self, delay_seconds: float = 30.0):
        return

    def _start_server_thread(self):
        self.server_thread = threading.Thread(target=self.start_server, daemon=True)
        self.server_thread.start()

    def _start_tray_delayed(self):
        def delayed_tray_creation():
            time.sleep(2.0)
            if self.tray_manager.create_tray_icon():
                self.tray_thread = threading.Thread(
                    target=self.tray_manager.tray.run, daemon=True
                )
                self.tray_thread.start()
                self.tray_manager.update_tooltip("运行中")

        threading.Thread(target=delayed_tray_creation, daemon=True).start()

    def _run_browser_only_mode(self):
        """WebView2 不可用时：仅启动本地服务并用系统浏览器打开。"""
        self.setup_signal_handlers()
        self._start_server_thread()
        threading.Thread(target=self._open_system_browser, daemon=True).start()
        self._start_tray_delayed()
        log.print_log("以浏览器模式启动（跳过 WebView2 桌面窗口）", "info")
        self._keep_running_loop()

    def _keep_running_loop(self):
        try:
            while not self.is_shutting_down:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.quit_application()

    def _keep_running_with_browser_fallback(self):
        self._keep_running_loop()

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
  <title>小爆来咯</title>
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
    <div class="title">小爆来咯</div>
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
  <title>小爆来咯</title>
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
    <div class="title">小爆来咯 启动失败</div>
    <div class="sub">{safe_message}</div>
  </div>
</body>
</html>
"""

    def wait_for_server_and_load(self):
        if self.check_server_ready(max_attempts=120):
            self.main_ui_loaded = True
            self._write_startup_url_file()
            if self.window:
                try:
                    self.window.load_url(self.get_app_url())
                    time.sleep(0.5)
                    self._inject_desktop_scripts()
                except Exception as e:
                    self.write_crash_log("load_url", e)
                    if self.window:
                        self.window.load_html(self.build_error_html(f"Failed to load URL: {e}"))
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
            self.tray_manager.show_notification("小爆来咯", "已最小化到系统托盘")

    def on_window_closing(self):
        """窗口关闭事件处理"""
        self.quit_application()
        return True

    def start(self):
        """启动WebView应用"""
        try:
            # 将自身注册到全局状态，供API端点访问
            from src.ai_write_x.web.state import get_app_state
            get_app_state().window_manager = self

            if self._should_use_browser_gui():
                self._run_browser_only_mode()
                return

            if sys.platform == "win32":
                self._prepare_windows_desktop_env()

            # 设置信号处理器
            self.setup_signal_handlers()

            # 启动后端服务器
            self._start_server_thread()

            # 读取窗口模式设置（首次启动时使用默认值）
            window_config = self.get_window_config()

            # 先显示轻量加载页，等本地服务就绪后再切换到主界面
            window_kwargs = {
                "title": "小爆来咯",
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
                        self._inject_desktop_scripts()
                        self.icon_manager.set_window_icon_windows()
                    except Exception:
                        pass

                window.events.loaded += on_loaded

            # 设置窗口关闭事件
            if hasattr(self.window, "events"):
                self.window.events.closing += self.on_window_closing

            threading.Thread(target=self.wait_for_server_and_load, daemon=True).start()
            threading.Thread(
                target=self._browser_fallback_watchdog, daemon=True
            ).start()
            self._start_tray_delayed()

            # 启动WebView
            self._configure_webview2()
            log.print_log("正在启动用户界面...", "info", False)
            try:
                storage_path = str(self._get_webview_storage_path())
                start_kwargs = {
                    "debug": False,
                    "storage_path": storage_path,
                    "private_mode": False,
                }
                gui_engine = os.environ.get("AIWRITEX_WEBVIEW_GUI", "").strip()
                if gui_engine:
                    start_kwargs["gui"] = gui_engine
                webview.start(**start_kwargs)
            except Exception as e:
                self.write_crash_log("webview_start", e)
                self._mark_browser_gui_preferred()
                self._keep_running_with_browser_fallback()
        except KeyboardInterrupt:
            self.quit_application()
        except Exception as e:
            self.write_crash_log("start", e)
            log.print_log(f"GUI启动失败: {str(e)}", "error")
            try:
                self._mark_browser_gui_preferred()
                if self.server_thread and self.server_thread.is_alive():
                    self._keep_running_with_browser_fallback()
                else:
                    self._run_browser_only_mode()
            except Exception:
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
            self.tray_manager.show_notification("小爆来咯", "内容生成完成")

    def on_task_error(self, error_msg):
        """任务出错时的托盘状态更新"""
        if self.tray_manager:
            self.tray_manager.set_icon_status("error")
            self.tray_manager.update_tooltip("任务执行出错")
            self.tray_manager.show_notification("小爆来咯", f"任务执行出错: {error_msg}")

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
