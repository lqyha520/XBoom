#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
XBoom 服务器部署入口（宝塔/纯 Web 模式）
不依赖 pywebview，直接启动 FastAPI 供浏览器访问

用法:
    python server.py                    # 默认端口 8000
    python server.py --port 8080        # 指定端口
    python server.py --host 0.0.0.0     # 指定监听地址（默认 0.0.0.0）

环境变量:
    AIWRITEX_PORT           监听端口（优先于 --port）
    AIWRITEX_HOST           监听地址（优先于 --host）
    AIWRITEX_CLIENT_TOKEN   访问令牌（不设置则自动生成，启动时打印）
    AIWRITEX_WORKERS        uvicorn worker 数量（默认 1）
"""

import argparse
import os
import sys
import secrets


def _load_env_file():
    """加载 .env.server 文件中的环境变量（未设置的才写入）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.server")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


# 确保项目根目录在路径中
script_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(script_dir, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 加载 .env.server 配置（必须在设置默认值之前）
_load_env_file()

os.environ["PYTHONIOENCODING"] = "utf-8"
# 标记为服务器模式，跳过 pywebview / 托盘等桌面组件
os.environ.setdefault("AIWRITEX_SERVER_MODE", "1")
# 生产模式：需要 token 认证
os.environ.setdefault("APP_ENV", "production")


def main():
    parser = argparse.ArgumentParser(description="XBoom 服务器模式")
    parser.add_argument("--host", default=None, help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认 8000）")
    parser.add_argument("--workers", type=int, default=None, help="worker 数量（默认 1）")
    args = parser.parse_args()

    host = args.host or os.environ.get("AIWRITEX_HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("AIWRITEX_PORT", "8000"))
    workers = args.workers or int(os.environ.get("AIWRITEX_WORKERS", "1"))

    # 设置或生成访问令牌
    token = os.environ.get("AIWRITEX_CLIENT_TOKEN", "")
    if not token:
        token = secrets.token_urlsafe(32)
        os.environ["AIWRITEX_CLIENT_TOKEN"] = token
        print("=" * 60)
        print(f"  XBoom Server Mode")
        print(f"  访问令牌: {token}")
        print(f"  请保存此令牌，用于首次访问: http://{host}:{port}/?token={token}")
        print("=" * 60)
    else:
        print(f"[Server] 使用环境变量中的访问令牌")

    print(f"[Server] 启动中... http://{host}:{port}")
    print(f"[Server] Workers: {workers}")
    print(f"[Server] 按 Ctrl+C 停止")

    import uvicorn
    from src.ai_write_x.web.app import app

    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=workers,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
