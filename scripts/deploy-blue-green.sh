#!/usr/bin/env bash
set -Eeuo pipefail

BASE_DIR="${XBOOM_BASE_DIR:-/www/wwwroot/xboom}"
RELEASES_DIR="${XBOOM_RELEASES_DIR:-/www/wwwroot/xboom-releases}"
CURRENT_LINK="${XBOOM_CURRENT_LINK:-/www/wwwroot/xboom-current}"
RUNTIME_DIR="${XBOOM_RUNTIME_DIR:-/www/wwwroot/xboom-runtime}"
CONFIG_RUNTIME_DIR="${XBOOM_CONFIG_RUNTIME_DIR:-$BASE_DIR/config-runtime}"
VENV_DIR="${XBOOM_VENV_DIR:-$BASE_DIR/venv}"
NGINX_CONF="${XBOOM_NGINX_CONF:-/www/server/panel/vhost/nginx/xboom.conf}"
NGINX_BIN="${XBOOM_NGINX_BIN:-/www/server/nginx/sbin/nginx}"
PUBLIC_PORT="${XBOOM_PUBLIC_PORT:-39005}"
BLUE_PORT="${XBOOM_BLUE_PORT:-8001}"
GREEN_PORT="${XBOOM_GREEN_PORT:-8002}"
HEALTH_TIMEOUT="${XBOOM_HEALTH_TIMEOUT:-90}"
DRAIN_WAIT_SECONDS="${XBOOM_DRAIN_WAIT_SECONDS:-30}"
SCHEDULER_IDLE_TIMEOUT="${XBOOM_SCHEDULER_IDLE_TIMEOUT:-3600}"
KEEP_RELEASES="${XBOOM_KEEP_RELEASES:-5}"

STARTED_PID=""
STARTED_PORT=""
NGINX_SWITCHED=0
TEMP_DIR_TO_CLEAN=""

log() { printf '[xboom-deploy] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

cleanup_on_exit() {
    local status=$?
    if (( status != 0 )); then
        if [[ "$NGINX_SWITCHED" == "0" && -n "$STARTED_PID" ]]; then
            kill -TERM "$STARTED_PID" 2>/dev/null || true
        fi
        if [[ -n "$TEMP_DIR_TO_CLEAN" && -d "$TEMP_DIR_TO_CLEAN" ]]; then
            case "$(readlink -f "$TEMP_DIR_TO_CLEAN")" in
                "$RELEASES_DIR"/*) rm -rf -- "$TEMP_DIR_TO_CLEAN" ;;
            esac
        fi
    fi
}
trap cleanup_on_exit EXIT

mkdir -p "$RELEASES_DIR" "$RUNTIME_DIR"
exec 9>"$RUNTIME_DIR/deploy-v2.lock"
flock -n 9 || fail "another deployment is already running"

[[ -x "$VENV_DIR/bin/python" ]] || fail "missing Python environment: $VENV_DIR"
[[ -f "$BASE_DIR/.env.server" ]] || fail "missing server environment: $BASE_DIR/.env.server"
[[ -f "$NGINX_CONF" ]] || fail "missing Nginx configuration: $NGINX_CONF"
[[ -x "$NGINX_BIN" ]] || fail "missing Nginx binary: $NGINX_BIN"

active_port() {
    local port
    port="$(grep -oE 'proxy_pass[[:space:]]+http://127\.0\.0\.1:[0-9]+' "$NGINX_CONF" | head -n1 | grep -oE '[0-9]+$' || true)"
    case "$port" in
        "$BLUE_PORT"|"$GREEN_PORT") printf '%s\n' "$port" ;;
        *) printf '%s\n' "$BLUE_PORT" ;;
    esac
}

standby_port() {
    if [[ "$1" == "$BLUE_PORT" ]]; then
        printf '%s\n' "$GREEN_PORT"
    else
        printf '%s\n' "$BLUE_PORT"
    fi
}

pid_for_port() {
    fuser -n tcp "$1" 2>/dev/null | awk '{print $1}' || true
}

assert_port_available() {
    local port="$1" pid cmd
    pid="$(pid_for_port "$port")"
    [[ -z "$pid" ]] && return 0
    cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
    fail "standby port $port is still owned by pid=$pid ($cmd)"
}

wait_for_health() {
    local port="$1" deployment_id="$2" deadline response
    deadline=$((SECONDS + HEALTH_TIMEOUT))
    while (( SECONDS < deadline )); do
        response="$(curl -fsS --max-time 5 "http://127.0.0.1:$port/health" 2>/dev/null || true)"
        if [[ "$response" == *'"status":"healthy"'* && "$response" == *"\"deployment_id\":\"$deployment_id\""* ]]; then
            return 0
        fi
        sleep 2
    done
    return 1
}

scheduled_task_count() {
    "$VENV_DIR/bin/python" -c '
import sqlite3
import sys

path = sys.argv[1]
try:
    with sqlite3.connect(path, timeout=5) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM scheduled_tasks WHERE status IN (?, ?)",
            ("running", "cancel_requested"),
        ).fetchone()
    print(int(row[0] if row else 0))
except (sqlite3.Error, OSError):
    print(0)
' "$BASE_DIR/data/aiwritex_v6.db"
}

wait_for_scheduler_idle() {
    local deadline count
    deadline=$((SECONDS + SCHEDULER_IDLE_TIMEOUT))
    while true; do
        count="$(scheduled_task_count)"
        if [[ "$count" == "0" ]]; then
            return 0
        fi
        if (( SECONDS >= deadline )); then
            fail "scheduler still has $count active task(s) after ${SCHEDULER_IDLE_TIMEOUT}s"
        fi
        log "waiting for $count scheduled task(s) to finish before cutover"
        sleep 10
    done
}

prepare_runtime_links() {
    local release_dir="$1" path source_path
    for path in data logs output secrets cache temp image; do
        mkdir -p "$BASE_DIR/$path"
        rm -rf -- "$release_dir/$path"
        ln -s "$BASE_DIR/$path" "$release_dir/$path"
    done
    rm -rf -- "$release_dir/venv" "$release_dir/.env.server"
    ln -s "$VENV_DIR" "$release_dir/venv"
    ln -s "$BASE_DIR/.env.server" "$release_dir/.env.server"

    # The server runs from source, so PathManager normally writes user settings
    # inside src/ai_write_x/config. Keep every writable settings file outside the
    # versioned release and link it back into each new release.
    install -d -m 0700 "$CONFIG_RUNTIME_DIR"
    for path in \
        config.yaml \
        aiforge.toml \
        dimensional_creative_config.yaml \
        ui_config.json \
        mcp_services.json \
        install_id.txt \
        aesthetic_profile.json
    do
        if [[ ! -e "$CONFIG_RUNTIME_DIR/$path" ]]; then
            source_path=""
            if [[ -f "$CURRENT_LINK/src/ai_write_x/config/$path" ]]; then
                source_path="$CURRENT_LINK/src/ai_write_x/config/$path"
            elif [[ -f "$release_dir/src/ai_write_x/config/$path" ]]; then
                source_path="$release_dir/src/ai_write_x/config/$path"
            fi
            if [[ -n "$source_path" ]]; then
                cp -aL -- "$source_path" "$CONFIG_RUNTIME_DIR/$path"
                chmod 0600 "$CONFIG_RUNTIME_DIR/$path"
                log "preserved runtime setting: $path"
            fi
        fi
        rm -f -- "$release_dir/src/ai_write_x/config/$path"
        ln -s "$CONFIG_RUNTIME_DIR/$path" "$release_dir/src/ai_write_x/config/$path"
    done

    mkdir -p "$release_dir/knowledge"
    for path in newshub_cache.json; do
        if [[ -e "$BASE_DIR/knowledge/$path" ]]; then
            rm -f -- "$release_dir/knowledge/$path"
            ln -s "$BASE_DIR/knowledge/$path" "$release_dir/knowledge/$path"
        fi
    done
    for path in knowledge_graph.json topic_memory.json ui_config.json; do
        if [[ -e "$BASE_DIR/$path" ]]; then
            rm -f -- "$release_dir/$path"
            ln -s "$BASE_DIR/$path" "$release_dir/$path"
        fi
    done
}

start_web() {
    local release_dir="$1" port="$2" deployment_id="$3"
    local log_file="$RUNTIME_DIR/server-$port.log"
    assert_port_available "$port"
    : >"$log_file"
    (
        # The web process must not inherit the deployment flock descriptor.
        exec 9>&-
        cd "$release_dir"
        set -a
        # shellcheck disable=SC1091
        source "$BASE_DIR/.env.server"
        set +a
        export AIWRITEX_PORT="$port"
        export AIWRITEX_DEPLOYMENT_ID="$deployment_id"
        if [[ -n "${AIWRITEX_SKIP_STARTUP_TASKS:-}" ]]; then
            export AIWRITEX_SKIP_STARTUP_TASKS="${AIWRITEX_SKIP_STARTUP_TASKS},scheduler"
        else
            export AIWRITEX_SKIP_STARTUP_TASKS="scheduler"
        fi
        exec "$VENV_DIR/bin/python" server.py --host 0.0.0.0 --port "$port" --workers 1
    ) >>"$log_file" 2>&1 < /dev/null &
    local pid=$!
    STARTED_PID="$pid"
    STARTED_PORT="$port"
    printf '%s\n' "$pid" >"$RUNTIME_DIR/server-$port.pid"
    if ! wait_for_health "$port" "$deployment_id"; then
        tail -n 80 "$log_file" >&2 || true
        kill -TERM "$pid" 2>/dev/null || true
        fail "new instance failed health check on port $port"
    fi
    log "new instance healthy: pid=$pid port=$port deployment=$deployment_id"
}

switch_nginx() {
    local old_port="$1" new_port="$2" deployment_id="$3"
    local candidate backup response
    candidate="$(mktemp "$RUNTIME_DIR/nginx.XXXXXX")"
    backup="$RUNTIME_DIR/nginx-before-$deployment_id.conf"
    cp -a "$NGINX_CONF" "$backup"
    sed -E "s#http://127\.0\.0\.1:($BLUE_PORT|$GREEN_PORT)#http://127.0.0.1:$new_port#g" "$NGINX_CONF" >"$candidate"
    grep -q "proxy_pass http://127.0.0.1:$new_port" "$candidate" || fail "could not update Nginx upstream"
    cp "$candidate" "$NGINX_CONF"
    rm -f "$candidate"
    if ! "$NGINX_BIN" -t; then
        cp "$backup" "$NGINX_CONF"
        fail "Nginx validation failed; previous configuration restored"
    fi
    "$NGINX_BIN" -s reload
    sleep 1
    response="$(curl -fsS --max-time 10 "http://127.0.0.1:$PUBLIC_PORT/health" 2>/dev/null || true)"
    if [[ "$response" != *"\"deployment_id\":\"$deployment_id\""* ]]; then
        cp "$backup" "$NGINX_CONF"
        "$NGINX_BIN" -t && "$NGINX_BIN" -s reload
        fail "public health check did not reach the new deployment; Nginx rolled back"
    fi
    NGINX_SWITCHED=1
    log "Nginx switched: $old_port -> $new_port"
}

set_current_release() {
    local release_dir="$1"
    ln -sfn "$release_dir" "$CURRENT_LINK.next"
    mv -Tf "$CURRENT_LINK.next" "$CURRENT_LINK"
}

stop_old_web() {
    local port="$1" pid deadline cmd
    pid="$(pid_for_port "$port")"
    [[ -z "$pid" ]] && return 0
    cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
    if [[ "$cmd" != *"server.py"* ]]; then
        log "refusing to stop non-XBoom pid=$pid on port=$port"
        return 0
    fi
    kill -TERM "$pid" 2>/dev/null || return 0
    deadline=$((SECONDS + DRAIN_WAIT_SECONDS))
    while kill -0 "$pid" 2>/dev/null && (( SECONDS < deadline )); do sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then
        log "old pid=$pid is still draining; it was left running safely"
    else
        rm -f "$RUNTIME_DIR/server-$port.pid"
        log "old pid=$pid stopped gracefully"
    fi
}

install_scheduler_service() {
    local release_dir="$1"
    "$VENV_DIR/bin/python" "$release_dir/scripts/run_scheduler.py" --check
    install -m 0644 "$release_dir/scripts/xboom-scheduler.service" /etc/systemd/system/xboom-scheduler.service
    systemctl daemon-reload
    systemctl enable xboom-scheduler.service >/dev/null
    if systemctl is-active --quiet xboom-scheduler.service; then
        systemctl restart --no-block xboom-scheduler.service
        log "scheduler restart requested (running tasks drain before takeover)"
    else
        systemctl start xboom-scheduler.service
        systemctl is-active --quiet xboom-scheduler.service || fail "scheduler service failed to start"
        log "scheduler service started"
    fi
}

cleanup_releases() {
    local current_real candidate count=0
    current_real="$(readlink -f "$CURRENT_LINK" || true)"
    while IFS= read -r candidate; do
        [[ -z "$candidate" ]] && continue
        count=$((count + 1))
        if (( count > KEEP_RELEASES )) && [[ "$(readlink -f "$candidate")" != "$current_real" ]]; then
            case "$(readlink -f "$candidate")" in
                "$RELEASES_DIR"/*) rm -rf -- "$candidate" ;;
                *) fail "refusing to remove unexpected release path: $candidate" ;;
            esac
        fi
    done < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
}

deploy_release() {
    local release_dir="$1" deployment_id="$2" old_port new_port
    wait_for_scheduler_idle
    old_port="$(active_port)"
    new_port="$(standby_port "$old_port")"
    start_web "$release_dir" "$new_port" "$deployment_id"
    switch_nginx "$old_port" "$new_port" "$deployment_id"
    set_current_release "$release_dir"
    printf '%s\n' "$new_port" >"$RUNTIME_DIR/active-port"
    stop_old_web "$old_port"
    install_scheduler_service "$release_dir"
    cleanup_releases
    STARTED_PID=""
    TEMP_DIR_TO_CLEAN=""
    log "deployment complete: release=$deployment_id active_port=$new_port"
}

mode="${1:-}"
case "$mode" in
    deploy)
        archive="${2:-}"
        release_id="${3:-}"
        [[ -f "$archive" ]] || fail "archive not found: $archive"
        [[ "$release_id" =~ ^[A-Za-z0-9._-]{7,80}$ ]] || fail "invalid release id: $release_id"
        release_dir="$RELEASES_DIR/$release_id"
        temp_dir="$release_dir.tmp.$$"
        TEMP_DIR_TO_CLEAN="$temp_dir"
        [[ ! -e "$release_dir" ]] || fail "release already exists: $release_id"
        rm -rf -- "$temp_dir"
        mkdir -p "$temp_dir"
        tar -xzf "$archive" -C "$temp_dir"
        [[ -f "$temp_dir/server.py" && -f "$temp_dir/requirements.txt" ]] || fail "invalid XBoom archive"
        prepare_runtime_links "$temp_dir"
        "$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -q -r "$temp_dir/requirements.txt"
        "$VENV_DIR/bin/python" -m pip check
        "$VENV_DIR/bin/python" -m compileall -q "$temp_dir/src" "$temp_dir/server.py"
        mv "$temp_dir" "$release_dir"
        deploy_release "$release_dir" "$release_id"
        rm -f -- "$archive"
        ;;
    rollback)
        requested="${2:-}"
        if [[ -n "$requested" ]]; then
            release_dir="$RELEASES_DIR/$requested"
        else
            current_real="$(readlink -f "$CURRENT_LINK" || true)"
            release_dir=""
            while IFS= read -r candidate; do
                if [[ "$(readlink -f "$candidate")" != "$current_real" ]]; then
                    release_dir="$candidate"
                    break
                fi
            done < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
        fi
        [[ -n "$release_dir" && -d "$release_dir" ]] || fail "rollback release not found"
        case "$(readlink -f "$release_dir")" in
            "$RELEASES_DIR"/*) ;;
            *) fail "rollback target is outside releases directory" ;;
        esac
        deploy_release "$release_dir" "$(basename "$release_dir")"
        ;;
    *)
        fail "usage: $0 deploy <archive.tar.gz> <release-id> | rollback [release-id]"
        ;;
esac
