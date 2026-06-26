#!/bin/bash
# XBoom 服务重启脚本
cd /www/wwwroot/xboom

# 加载 .env.server 配置
if [ -f .env.server ]; then
    set -a
    source .env.server
    set +a
    echo "[Restart] 已加载 .env.server"
fi

# 杀掉旧进程
pkill -f "python server.py" 2>/dev/null
sleep 2
fuser -k 8001/tcp 2>/dev/null
sleep 1

# 启动新进程
source venv/bin/activate
nohup python server.py > server.log 2>&1 &
echo $! > server.pid
sleep 5

# 检查状态
if kill -0 $(cat server.pid) 2>/dev/null; then
    echo "[Restart] 服务启动成功 PID=$(cat server.pid)"
    echo "[Restart] Token: ${AIWRITEX_CLIENT_TOKEN}"
    echo "[Restart] 访问: http://81.71.94.132:39005/?token=${AIWRITEX_CLIENT_TOKEN}"
else
    echo "[Restart] 启动失败，查看日志:"
    tail -20 server.log
fi
