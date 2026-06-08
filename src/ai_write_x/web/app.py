#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import os
import secrets
import time
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles as StarletteStaticFiles

import uuid
import psutil
import threading
import uvicorn

from src.ai_write_x.version import get_version
from src.ai_write_x.version import get_version_with_prefix 
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.utils import utils

# 导入状态管理
from .state import app_state

# 导入API路由
from .api.config import router as config_router
from .api.templates import router as templates_router
from .api.articles import router as articles_router
from .api.generate import router as generate_router
from .api.spider import router as spider_router
from .api.quality import router as quality_router
from .api.knowledge import router as knowledge_router
from .api.mcp import router as mcp_router
from .api.newshub import router as newshub_router
from .api.scheduler import router as scheduler_router
from .api.updater import router as updater_router
from .api.menu_ip_whitelist import router as menu_ip_whitelist_router
from .api.batch import router as batch_router

# 添加全局状态
app_shutdown_event = asyncio.Event()

OPTIONAL_STARTUP_ENV = "AIWRITEX_SKIP_STARTUP_TASKS"
OPTIONAL_STARTUP_GROUPS = {
    "network": {"usage_stats", "menu_ip_access", "newshub"},
    "heavy": {"global_tools", "scavenger", "dashboard_render", "newshub"},
    "background": {
        "global_tools",
        "scavenger",
        "scheduler",
        "usage_stats",
        "menu_ip_access",
        "periodic_cleanup",
        "batch_processor",
        "websocket_manager",
        "dashboard_render",
        "newshub",
    },
}
_optional_startup_tasks: set[asyncio.Task] = set()


def _skip_optional_startup_task(name: str) -> bool:
    raw = os.environ.get(OPTIONAL_STARTUP_ENV, "")
    skipped = {item.strip().lower() for item in raw.split(",") if item.strip()}
    task_name = name.lower()
    if "all" in skipped or task_name in skipped:
        return True
    return any(task_name in OPTIONAL_STARTUP_GROUPS.get(group, set()) for group in skipped)


def _schedule_optional_startup_task(name: str, coro):
    if _skip_optional_startup_task(name):
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        return None
    task = asyncio.create_task(coro, name=f"startup:{name}")
    _optional_startup_tasks.add(task)

    def _consume_result(done_task: asyncio.Task):
        _optional_startup_tasks.discard(done_task)
        try:
            done_task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            try:
                from src.ai_write_x.utils import log
                log.print_log(f"[Startup] optional task {name} failed: {exc}", "warning")
            except Exception:
                pass

    task.add_done_callback(_consume_result)
    return task


def _schedule_optional_startup_sync_task(name: str, func, *args, **kwargs):
    async def _runner():
        return await asyncio.to_thread(func, *args, **kwargs)

    return _schedule_optional_startup_task(name, _runner())


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        import queue
        from src.ai_write_x.config.config import Config
        from src.ai_write_x.utils import comm, log

        # 初始化主进程日志队列
        app_state.log_queue = queue.Queue()
        app_state.is_running = True

        # 初始化 UI 模式
        log.init_ui_mode()

        # 连接 comm 到队列
        comm.set_log_queue(app_state.log_queue)

        # 其他初始化...
        app_state.config = Config.get_instance()
        if not app_state.config.load_config():
            log.print_log("配置加载失败，使用默认配置", "warning")

        # 注册 CrewAI 工具（含 news_hub_tool），自动化任务与内容生成共用
        async def warmup_global_tools():
            try:
                await asyncio.sleep(1.5)
                from src.ai_write_x.core.system_init import initialize_global_tools
                await asyncio.to_thread(initialize_global_tools)
                log.print_log("?????????? news_hub_tool?", "success")
            except Exception as tool_err:
                log.print_log(f"????????: {tool_err}", "error")

        _schedule_optional_startup_task("global_tools", warmup_global_tools())

        # 服务启动时清掉上次未跑完的生成任务登记（不自动续跑）
        try:
            from src.ai_write_x.core.task_manager import task_manager
            task_manager.prepare_for_new_task("main_generate")
        except Exception:
            pass
            
        # 启动宇宙清道夫 (V10.0 Cosmic Scavenger)
        from src.ai_write_x.core.scavenger import CosmicScavenger
        app_state.scavenger = CosmicScavenger()
        _schedule_optional_startup_task("scavenger", app_state.scavenger.start_daemon())
        
        # 启动定时任务调度服务 (V6 Scheduler)
        from src.ai_write_x.core.scheduler import scheduler_service
        if not _skip_optional_startup_task("scheduler"):
            _schedule_optional_startup_sync_task("scheduler", scheduler_service.start)

        # 使用统计：后台上报启动（IP 由统计服务端记录）
        try:
            from src.ai_write_x.core.usage_stats import schedule_usage_report
            if not _skip_optional_startup_task("usage_stats"):
                _schedule_optional_startup_sync_task("usage_stats", schedule_usage_report)
        except Exception as stats_err:
            log.print_log(f"[使用统计] 初始化跳过: {stats_err}", "warning")

        # 受限菜单白名单：启动时从 MySQL 拉取 menu_ip_whitelist 表
        try:
            from src.ai_write_x.core.menu_ip_access import refresh_menu_ip_access_on_startup
            if not _skip_optional_startup_task("menu_ip_access"):
                _schedule_optional_startup_sync_task("menu_ip_access", refresh_menu_ip_access_on_startup)
        except Exception as menu_ip_err:
            log.print_log(f"[菜单白名单] 初始化跳过: {menu_ip_err}", "warning")
        
        # V15.0: 初始化量子优化组件
        try:
            from src.ai_write_x.core.batch_processor import get_batch_processor
            from src.ai_write_x.core.semantic_cache_v2 import get_semantic_cache
            from src.ai_write_x.web.websocket_manager import get_websocket_manager
            
            # 初始化新的优化组件
            from src.ai_write_x.utils.cache_manager import cache_manager
            from src.ai_write_x.utils.cleanup_manager import cleanup_manager
            
            # 启动定期清理任务（每24小时）
            async def periodic_cleanup():
                while True:
                    await asyncio.sleep(86400)  # 24小时
                    try:
                        cleanup_manager.full_cleanup()
                        log.print_log('[清理] 定期清理完成', 'info')
                    except Exception as e:
                        log.print_log(f'[清理] 定期清理失败: {e}', 'warning')
            
            _schedule_optional_startup_task("periodic_cleanup", periodic_cleanup())
            
            # 启动批处理器
            batch_processor = get_batch_processor()
            _schedule_optional_startup_task("batch_processor", batch_processor.start())
            log.print_log("[V15.0] [START] 智能批处理引擎已启动", "success")
            
            # 初始化语义缓存
            semantic_cache = get_semantic_cache()
            log.print_log("[V15.0] [MEM] 语义缓存 V2 已初始化", "success")
            
            # 启动 WebSocket 管理器
            ws_manager = get_websocket_manager()
            _schedule_optional_startup_task("websocket_manager", ws_manager.start())
            log.print_log("[V15.0] [WS] WebSocket 连接治理已启动", "success")
            
        except Exception as v15_err:
            log.print_log(f"[V15.0] [WARN] 组件初始化警告: {v15_err}", "warning")
        
        # V13.0 Optimization: 将控制台大盘渲染和统计逻辑移至后台异步任务，防止阻塞服务器由于“就绪”检测导致的启动延迟
        async def render_dashboard_background():
            try:
                # 稍微延迟一下，确保其他核心组件已就绪，且不争抢启动瞬间的 CPU
                await asyncio.sleep(0.5)
                
                # V24.0: 延迟导入 rich，减少进程启动初期的加载负担
                from rich.console import Console
                from rich.panel import Panel
                from rich.table import Table
                from src.ai_write_x.database.db_manager import db_manager
                
                # 同步方法在线程池中执行，防止阻塞事件循环
                stats = await asyncio.to_thread(db_manager.get_system_stats)
                console = Console()
                
                table = Table(show_header=False, box=None)
                table.add_column("Metric", style="cyan", justify="right")
                table.add_column("Value", style="bold magenta")
                table.add_row("🚀 总收录话题 (Topics):", str(stats.get("total_topics", 0)))
                table.add_row("📚 沉淀自研文章 (Articles):", str(stats.get("total_articles", 0)))
                table.add_row("🧠 AI 长期记忆总计 (Memories):", str(stats.get("total_memories", 0)))
                table.add_row("⚠️ P0级失败血泪教训 (Lessons):", str(stats.get("lessons_learned", 0)))
                
                panel = Panel(
                    table,
                    title=f"[bold green]AIWriteX V{get_version()} Core Dash[/bold green]",
                    subtitle="[italic]Powered by Phase 4 UI Engine[/italic]",
                    border_style="deep_sky_blue1",
                    expand=False
                )
                console.print(panel)
            except Exception as dash_err:
                log.print_log(f"控制台看板后台渲染失败: {dash_err}", "warning")

        _schedule_optional_startup_task("dashboard_render", render_dashboard_background())
        
        # V13.0 Optimization: 后台预热新闻聚合管理器 (NewsHub)
        async def warmup_newshub():
            try:
                await asyncio.sleep(1.0) # 进一步推迟，优先级最低
                from src.ai_write_x.web.api.newshub import get_hub_manager
                await asyncio.to_thread(get_hub_manager)
                log.print_log("[NewsHub] 后台预热完成", "info")
            except Exception as e:
                log.print_log(f"[NewsHub] 后台预热失败: {e}", "warning")
                
        _schedule_optional_startup_task("newshub", warmup_newshub())

    except Exception as e:
        log.print_log(f"Web服务启动失败: {str(e)}", "error")

    yield

    # 关闭时执行
    app_state.is_running = False
    for task in list(_optional_startup_tasks):
        task.cancel()
    if _optional_startup_tasks:
        await asyncio.gather(*list(_optional_startup_tasks), return_exceptions=True)
    
    if hasattr(app_state, 'scavenger') and app_state.scavenger:
        app_state.scavenger.stop_daemon()
    
    # V15.0: 停止量子优化组件
    try:
        from src.ai_write_x.core.batch_processor import get_batch_processor
        from src.ai_write_x.web.websocket_manager import get_websocket_manager
        
        batch_processor = get_batch_processor()
        await batch_processor.stop()
        
        ws_manager = get_websocket_manager()
        await ws_manager.stop()
        
        log.print_log("[V15.0] 量子优化组件已停止", "info")
    except Exception:
        pass
        
    log.print_log("AIWriteX Web服务正在关闭", "info")


# 创建FastAPI应用，使用lifespan
app = FastAPI(
    title="AIWriteX Web API",
    version=get_version(),
    description="智能内容创作平台Web接口",
    lifespan=lifespan,
)

# 获取Web模块路径
# 获取Web模块路径
if utils.get_is_release_ver():
    web_path = Path(utils.get_res_path("web"))
    if not (web_path / "templates").exists():
        candidate = Path(utils.get_res_path("src/ai_write_x/web"))
        if (candidate / "templates").exists():
            web_path = candidate
else:
    web_path = Path(__file__).parent

static_path = web_path / "static"
templates_path = web_path / "templates"

# 确保静态文件目录存在
os.makedirs(static_path, exist_ok=True)
os.makedirs(templates_path, exist_ok=True)

# 确保图片目录存在
image_dir = PathManager.get_image_dir()
os.makedirs(image_dir, exist_ok=True)


# 自定义 StaticFiles 类，处理文件不存在的情况
class SafeStaticFiles(StarletteStaticFiles):
    """安全的 StaticFiles 类，文件不存在时返回 404 而不是抛出异常"""
    
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except (HTTPException, FileNotFoundError) as e:
            # 文件不存在时返回 404
            return Response(
                content=f"File not found: {path}",
                status_code=404,
                media_type="text/plain"
            )
        except Exception as e:
            # 其他错误也返回 404，避免抛出异常
            return Response(
                content=f"Error: {str(e)}",
                status_code=404,
                media_type="text/plain"
            )


# 挂载静态文件和图片（使用安全的 StaticFiles）
app.mount("/static", SafeStaticFiles(directory=str(static_path)), name="static")
app.mount("/images", SafeStaticFiles(directory=str(image_dir)), name="images")
app.mount("/output", SafeStaticFiles(directory=str(PathManager.get_output_dir())), name="output")

# 注入 Swarm 拓扑 API (V18.0)
@app.get('/api/swarm/topology') # Use app.get for FastAPI
async def get_swarm_topology():
    """获取蜂群实时拓扑数据 (V18.0)"""
    state_manager = SwarmStateManager()
    visualizer = SwarmVisualizer(state_manager)
    # 注入一些模拟 Agent 以供预览展示 (真实运行时由 AgentFactory 注册)
    hub = get_collaboration_hub()
    if not hub.allocator.agent_registry:
        hub.allocator.register_agent("量子研究员-01", [SwarmCapabilities.RESEARCH, SwarmCapabilities.REASONING])
        hub.allocator.register_agent("内容架构师-02", [SwarmCapabilities.CREATIVE_WRITING])
        hub.allocator.register_agent("流量优化师-03", [SwarmCapabilities.SEO_OPTIMIZATION])
        
    data = await visualizer.get_topology_data()
    return JSONResponse(content=data)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# V15.0: 添加性能优化中间件
try:
    from src.ai_write_x.web.middleware.performance import (
        ResponseCacheMiddleware,
        PerformanceMetricsMiddleware,
        RequestLoggingMiddleware
    )
    from src.ai_write_x.web.middleware.rate_limit import (
        RateLimitMiddleware,
        CircuitBreakerMiddleware
    )
    
    # 响应缓存中间件 (缓存 GET 请求)
    app.add_middleware(
        ResponseCacheMiddleware,
        cache_duration=60,
        max_cache_size=1000,
        exclude_paths=["/api/generate", "/api/generate/stop", "/ws/", "/health"]
    )
    
    # 性能指标收集中间件
    app.add_middleware(PerformanceMetricsMiddleware)
    
    # 请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)
    
    # 熔断器中间件 (内层)
    app.add_middleware(CircuitBreakerMiddleware)
    
    # 限流中间件 (外层)
    app.add_middleware(
        RateLimitMiddleware,
        default_rate=50.0,
        default_burst=100,
        path_configs={
            "/api/generate": type('Config', (), {'requests_per_second': 10.0, 'burst_size': 20})(),
        }
    )
    
    print("[V15.0] [OK] 性能优化中间件已加载")
except Exception as e:
    print(f"[V15.0] [WARN] 中件点加载警告: {e}")

# 模板引擎
templates = Jinja2Templates(directory=str(templates_path))

# 注册API路由
app.include_router(config_router)
app.include_router(templates_router)
app.include_router(articles_router)
app.include_router(generate_router)
app.include_router(spider_router)
app.include_router(quality_router)
app.include_router(knowledge_router)
app.include_router(mcp_router)
app.include_router(newshub_router)
app.include_router(scheduler_router)
app.include_router(updater_router)
app.include_router(menu_ip_whitelist_router)
app.include_router(batch_router)


# 全局允许的客户端令牌集合
allowed_tokens = {
    token.strip()
    for token in os.environ.get("AIWRITEX_CLIENT_TOKEN", "").split(",")
    if token.strip()
}


def _is_restricted_menu_visible(request: Request) -> bool:
    """
    受限菜单可见性（工作台/知识库/任务监控/素材中心）：
    启动时已从 MySQL menu_ip_whitelist 表加载并比对本机公网 IP。
    """
    try:
        from src.ai_write_x.core.menu_ip_access import is_restricted_menu_visible
        return is_restricted_menu_visible()
    except Exception:
        return False


@app.middleware("http")
async def structured_request_logging(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    # 增加 req_id 到 state
    request.state.req_id = req_id
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        response.headers["X-Request-ID"] = req_id
        
        path = request.url.path
        if not path.startswith("/static") and not path.startswith("/images"):
            # V19.2: 抑制高频心跳请求的日志输出，防止终端刷屏
            ignored_paths = [
                "/api/swarm/topology",
                "/api/scheduler/tasks",
                "/api/scheduler/logs",
                "/health"
            ]
            
            from src.ai_write_x.utils import log
            msg = f"[REQ:{req_id}] {request.method} {path} | Status: {response.status_code} | Time: {process_time:.3f}s"
            
            if response.status_code >= 500:
                log.print_log(msg, "error")
            elif response.status_code >= 400:
                log.print_log(msg, "warning")
            elif any(path.startswith(p) for p in ignored_paths):
                # 心跳逻辑仅在 DEBUG 模式下输出（如果有的话）或完全忽略
                pass
            else:
                log.print_log(msg, "info")
                
        return response
    except Exception as e:
        process_time = time.time() - start_time
        from src.ai_write_x.utils import log
        log.print_log(f"[REQ:{req_id}] {request.method} {request.url.path} | Error: {str(e)} | Time: {process_time:.3f}s", "error")
        raise

@app.middleware("http")
async def verify_client_token(request: Request, call_next):
    # 静态资源、健康检查和主页（带Token进入）跳过验证
    # V14.1: 加强本地访问认证，添加环境判断，只在开发环境允许免密访问
    path = request.url.path
    import os
    is_dev_mode = os.environ.get("APP_ENV", "production") != "production"
    is_localhost = request.client.host in ["127.0.0.1", "::1", "localhost"]
    
    if (
        path.startswith("/static")
        or path.startswith("/images")
        or path == "/health"
        or path.startswith("/api/system/update")
        or (is_dev_mode and is_localhost)
    ):
        return await call_next(request)
    
    # 获取查询参数中的token（用于首次加载同步到allowed_tokens）
    url_token = request.query_params.get("token")
    if path == "/" and url_token:
        if allowed_tokens and url_token not in allowed_tokens:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access Denied: invalid client token."}
            )
        allowed_tokens.add(url_token)
        # 将token存入cookie，方便后续JS读取或通过JS设置到全局
        response = await call_next(request)
        response.set_cookie(
            key="app_client_token",
            value=url_token,
            httponly=False, # JS需要读取
            samesite="strict",
        )
        return response

    # 验证 header / cookie 中的 token（服务重启后 allowed_tokens 会清空，需从 cookie 恢复）
    header_token = request.headers.get("X-App-Client-Token")
    cookie_token = request.cookies.get("app_client_token")
    effective_token = header_token or cookie_token
    if effective_token and any(secrets.compare_digest(effective_token, token) for token in allowed_tokens):
        return await call_next(request)

    # 如果是访问主页但没带token，或者接口没带token且不在白名单，拒绝
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=403,
        content={"detail": "Access Denied: Standard browser access is disabled. Please use AIWriteX Client."}
    )

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """返回主界面"""
    show_restricted_menu = _is_restricted_menu_visible(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "version": get_version_with_prefix(),
            "show_restricted_menu": show_restricted_menu,
        },
    )


@app.get("/health")
async def health_check():
    """健康检查接口 (V5 增强)"""
    try:
        process = psutil.Process()
        memory_mb = round(process.memory_info().rss / 1024 / 1024, 2)
    except:
        memory_mb = -1
        
    status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": get_version(),
        "memory_mb": memory_mb,
        "active_threads": threading.active_count(),
        "components": {
            "config_loaded": hasattr(app_state, 'config') and app_state.config is not None,
            "scavenger_running": hasattr(app_state, 'scavenger') and getattr(app_state.scavenger, 'is_running', False),
            "log_queue_ready": hasattr(app_state, 'log_queue') and app_state.log_queue is not None
        }
    }
    return status


@app.get("/health/v15")
async def health_check_v15():
    """V15.0 增强健康检查"""
    try:
        from src.ai_write_x.core.batch_processor import get_batch_processor
        from src.ai_write_x.core.semantic_cache_v2 import get_semantic_cache
        from src.ai_write_x.core.adaptive_router import get_adaptive_router
        from src.ai_write_x.web.websocket_manager import get_websocket_manager
        from src.ai_write_x.core.metrics import get_metrics_collector
        
        v15_status = {
            "status": "healthy",
            "version": "15.0.0",
            "components": {
                "batch_processor": "active",
                "semantic_cache": "active",
                "adaptive_router": "active",
                "websocket_manager": "active",
                "metrics_collector": "active",
            },
            "stats": {
                "batch_processor": get_batch_processor().get_stats(),
                "semantic_cache": get_semantic_cache().get_stats(),
                "adaptive_router": get_adaptive_router().get_stats(),
                "websocket_manager": get_websocket_manager().get_stats(),
            }
        }
        return v15_status
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/metrics")
async def get_metrics():
    """Prometheus 格式指标导出"""
    try:
        from src.ai_write_x.core.metrics import get_metrics_collector
        collector = get_metrics_collector()
        return collector.export_prometheus()
    except Exception as e:
        return f"# Error: {e}"


# 添加关闭接口
@app.post("/shutdown")
async def shutdown():
    """关闭服务器"""
    try:
        from src.ai_write_x.web.api.updater import start_prepared_update
        start_prepared_update("shutdown")
    except Exception as exc:
        from src.ai_write_x.utils import log
        log.print_log(f"[Updater] ?????????: {exc}", "warning")
    app_shutdown_event.set()
    return {"status": "shutting down"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7000, log_level="info")
