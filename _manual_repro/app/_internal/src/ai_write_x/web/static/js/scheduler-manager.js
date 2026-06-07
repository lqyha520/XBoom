/**
 * SchedulerManager - 自动化任务（定时发布）
 */

class SchedulerManager {
    constructor() {
        this.tasks = [];
        this.logs = [];
        this.selectedTaskId = null;
        this.lastCreatedTaskId = null;
        this.refreshInterval = null;
        this._initialized = false;
        this._loading = false;
        this._pendingRefresh = false;
        this._lastError = '';
        this.platformLabels = {
            wechat: '微信公众号',
            xiaohongshu: '小红书',
            zhihu: '知乎',
            toutiao: '今日头条',
        };
    }

    init() {
        if (this._initialized) return;
        this._initialized = true;
        this.refreshData(true);
        if (this.refreshInterval) clearInterval(this.refreshInterval);
        this.refreshInterval = setInterval(() => {
            const view = document.getElementById('scheduler-view');
            if (view && view.classList.contains('active')) {
                this.refreshData(false);
            }
        }, 30000);
    }

    async refreshData(showToast = false, force = false) {
        if (this._loading && !force) {
            this._pendingRefresh = true;
            return;
        }
        this._loading = true;
        this._setRefreshButtonState(true);

        try {
            await Promise.all([this.fetchTasks(), this.fetchLogs()]);
            this._lastError = '';
            this.renderTasks();
            this.renderSidebarTasks();
            this.renderLogs();
            this.updateStats();
            this._updateLastRefreshLabel();
            this._hideLoadError();
            if (showToast && window.showNotification) {
                window.showNotification(`已刷新，共 ${this.tasks.length} 个任务`, 'success');
            }
        } catch (e) {
            this._lastError = e.message || String(e);
            this._showLoadError(this._lastError);
        } finally {
            this._loading = false;
            this._setRefreshButtonState(false);
            if (this._pendingRefresh) {
                this._pendingRefresh = false;
                this.refreshData(false, true);
            }
        }
    }

    _setRefreshButtonState(loading) {
        const btn = document.getElementById('scheduler-refresh-btn');
        if (btn) {
            btn.disabled = loading;
            btn.textContent = loading ? '刷新中…' : '刷新';
        }
        const btnLite = document.getElementById('scheduler-refresh-btn-lite');
        if (btnLite) {
            btnLite.disabled = loading;
            btnLite.textContent = loading ? '刷新中…' : '刷新';
        }
    }

    _updateLastRefreshLabel() {
        const el = document.getElementById('scheduler-last-refresh');
        if (!el) return;
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const ts = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
        el.textContent = `更新于 ${ts} · 共 ${this.tasks.length} 项`;
    }

    _showLoadError(msg) {
        const el = document.getElementById('scheduler-load-error');
        if (!el) return;
        el.style.display = 'block';
        el.textContent = `任务列表加载失败：${msg}（请点右上角「刷新」，或重新打开本页）`;
    }

    _hideLoadError() {
        const el = document.getElementById('scheduler-load-error');
        if (el) el.style.display = 'none';
    }

    _authHeaders() {
        const token =
            window.APP_CLIENT_TOKEN ||
            window.appConfig?.token ||
            this._getCookie('app_client_token') ||
            localStorage.getItem('app_client_token') ||
            '';
        return {
            'X-App-Client-Token': token,
        };
    }

    _getCookie(name) {
        const prefix = `${name}=`;
        const row = document.cookie.split(';').map((c) => c.trim()).find((c) => c.startsWith(prefix));
        return row ? decodeURIComponent(row.slice(prefix.length)) : '';
    }

    async _fetchJson(url) {
        const response = await fetch(url, {
            headers: this._authHeaders(),
            credentials: 'same-origin',
        });
        if (!response.ok) {
            let detail = response.statusText;
            try {
                const body = await response.json();
                detail = body.detail || body.message || detail;
            } catch {
                /* ignore */
            }
            throw new Error(`${response.status} ${detail}`);
        }
        return response.json();
    }

    async fetchTasks() {
        try {
            this.tasks = await this._fetchJson('/api/scheduler/tasks');
            if (!Array.isArray(this.tasks)) {
                this.tasks = [];
            }
        } catch (error) {
            console.error('Fetch tasks failed:', error);
            this.tasks = [];
            throw error;
        }
    }

    async fetchLogs() {
        try {
            this.logs = await this._fetchJson('/api/scheduler/logs?limit=50');
            if (!Array.isArray(this.logs)) {
                this.logs = [];
            }
        } catch (error) {
            console.error('Fetch logs failed:', error);
            this.logs = [];
        }
    }

    _shortId(id) {
        if (!id) return '—';
        const s = String(id);
        return s.length > 8 ? s.slice(0, 8) : s;
    }

    _taskLabel(task) {
        const topic = (task.topic || '').trim();
        if (topic) return topic;
        return '（到点自动抓热点）';
    }

    renderSidebarTasks() {
        const box = document.getElementById('scheduler-sidebar-task-list');
        if (!box) return;

        if (this.tasks.length === 0) {
            box.innerHTML =
                '<p class="text-secondary" style="font-size:12px;margin:8px 0;line-height:1.5;">暂无任务<br>点「新建任务」创建</p>';
            return;
        }

        box.innerHTML = this.tasks
            .map((task) => {
                const active = this.lastCreatedTaskId === task.id ? ' is-new' : '';
                return `
            <div class="scheduler-sidebar-task-item${active}" data-task-id="${this.escapeAttr(task.id)}"
                onclick="window.schedulerManager.highlightTask('${this.escapeAttr(task.id)}')" title="任务编号 ${task.id}">
                <div class="scheduler-sidebar-task-title">${this.escapeHtml(this.truncate(this._taskLabel(task), 22))}</div>
                <div class="scheduler-sidebar-task-meta">
                    <span class="status-badge status-${task.status}" style="font-size:10px;padding:1px 6px;">
                        ${this.getStatusText(task.status)}
                    </span>
                    <span>${task.execution_time || ''}</span>
                </div>
                <div class="scheduler-sidebar-task-id">#${this.escapeHtml(this._shortId(task.id))}</div>
            </div>`;
            })
            .join('');
    }

    highlightTask(taskId) {
        const row = document.querySelector(`#scheduler-task-list tr[data-task-id="${taskId}"]`);
        if (row) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('scheduler-row-highlight');
            setTimeout(() => row.classList.remove('scheduler-row-highlight'), 2500);
        }
    }

    renderTasks() {
        const container = document.getElementById('scheduler-task-list');
        const hint = document.getElementById('scheduler-list-hint');
        if (!container) return;

        if (hint) {
            hint.textContent =
                this.tasks.length > 0 ? `共 ${this.tasks.length} 条，按下次执行时间排序` : '';
        }

        if (this.tasks.length === 0) {
            container.innerHTML =
                '<tr><td colspan="7" class="text-center py-5">暂无任务。点右上角「＋ 新建任务」创建，保存后会显示在这里</td></tr>';
            return;
        }

        container.innerHTML = this.tasks
            .map((task) => {
                const rowClass =
                    this.lastCreatedTaskId === task.id ? ' class="scheduler-row-new"' : '';
                const id = this.escapeAttr(task.id);
                return `
            <tr${rowClass} data-task-id="${id}">
                <td class="scheduler-id-cell" title="${this.escapeAttr(task.id)}">#${this.escapeHtml(this._shortId(task.id))}</td>
                <td class="font-medium" title="${this.escapeAttr(this._taskLabel(task))}">${this.escapeHtml(this.truncate(this._taskLabel(task), 36))}</td>
                <td><span class="tag tag-outline">${this.platformLabels[task.platform] || task.platform}</span></td>
                <td style="white-space:nowrap;font-size:13px;">${task.execution_time || '—'}</td>
                <td>${task.is_recurring ? `每 ${task.interval_hours} 小时` : '单次'}</td>
                <td>
                    <span class="status-badge status-${task.status}">
                        ${this.getStatusText(task.status)}
                    </span>
                </td>
                <td>
                    <div class="table-actions">
                        <button class="btn btn-icon btn-sm" onclick="window.schedulerManager.toggleTask('${id}', '${task.status}')" title="${task.status === 'enabled' ? '暂停' : '启用'}">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                ${task.status === 'enabled' ? '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>' : '<polygon points="5 3 19 12 5 21 5 3"/>'}
                            </svg>
                        </button>
                        <button class="btn btn-icon btn-sm" onclick="window.schedulerManager.deleteTask('${id}')" title="删除">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>`;
            })
            .join('');

        if (this.lastCreatedTaskId) {
            setTimeout(() => this.highlightTask(this.lastCreatedTaskId), 300);
        }
    }

    renderLogs() {
        const container = document.getElementById('scheduler-log-list');
        if (!container) return;

        if (this.logs.length === 0) {
            container.innerHTML = '<tr><td colspan="4" class="text-center py-5">暂无执行记录</td></tr>';
            return;
        }

        container.innerHTML = this.logs
            .map((log) => {
                const task = this.tasks.find((t) => t.id === log.task_id);
                const taskHint = task
                    ? `<span class="text-secondary" style="font-size:11px;">#${this._shortId(task.id)} ${this.escapeHtml(this.truncate(this._taskLabel(task), 12))}</span><br>`
                    : log.task_id
                      ? `<span class="text-secondary" style="font-size:11px;">#${this._shortId(log.task_id)}</span><br>`
                      : '';
                return `
            <tr>
                <td class="text-secondary" style="font-size:12px;white-space:nowrap;">${log.run_time}</td>
                <td>
                    <span class="status-badge status-${log.status}" style="padding:2px 6px;font-size:11px;">
                        ${log.status === 'success' ? '成功' : log.status === 'failed' ? '失败' : '运行中'}
                    </span>
                </td>
                <td style="font-size:13px;">${taskHint}${this.escapeHtml(log.message || '')}</td>
                <td>
                    ${log.article_id ? `<button class="btn btn-link btn-sm" onclick="window.articleManager.viewArticle('${this.escapeAttr(log.article_id)}')">查看</button>` : '—'}
                </td>
            </tr>`;
            })
            .join('');
    }

    escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    escapeAttr(str) {
        return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    }

    updateStats() {
        const activeCount = this.tasks.filter((t) => t.status === 'enabled' || t.status === 'running').length;
        const totalCount = this.tasks.length;
        const today = new Date().toISOString().split('T')[0];
        const todayLogs = this.logs.filter((l) => l.run_time && l.run_time.startsWith(today)).length;

        const elActive = document.getElementById('scheduler-active-count');
        const elTotal = document.getElementById('scheduler-total-count');
        const elLogs = document.getElementById('scheduler-log-count');

        if (elActive) elActive.innerText = activeCount;
        if (elTotal) elTotal.innerText = totalCount;
        if (elLogs) elLogs.innerText = todayLogs;
    }

    openAddTaskModal() {
        this.selectedTaskId = null;
        document.getElementById('task-modal-title').innerText = '新建定时任务';
        document.getElementById('task-topic').value = '';
        document.getElementById('task-platform').value = 'wechat';
        document.getElementById('task-exec-time').value = this.getDefaultExecTime();
        document.getElementById('task-recurring').checked = false;
        document.getElementById('task-beautify').checked = true;
        document.getElementById('task-article-count').value = '1';
        document.getElementById('task-collection-mode').checked = false;
        document.getElementById('task-interval').value = '24';
        document.getElementById('task-interval-group').style.display = 'none';
        const tip = document.getElementById('platform-verify-tip');
        if (tip) tip.style.display = 'none';
        document.getElementById('task-edit-modal').style.display = 'flex';
        this.checkPlatformConnection('wechat');
    }

    closeModal() {
        document.getElementById('task-edit-modal').style.display = 'none';
    }

    toggleInterval(checked) {
        document.getElementById('task-interval-group').style.display = checked ? 'block' : 'none';
    }

    setDelayTime(seconds) {
        const t = new Date(Date.now() + seconds * 1000);
        document.getElementById('task-exec-time').value = this.toLocalDatetimeInput(t);
    }

    setPresetDaily(hour) {
        const t = new Date();
        t.setHours(hour, 0, 0, 0);
        if (t.getTime() <= Date.now()) {
            t.setDate(t.getDate() + 1);
        }
        document.getElementById('task-exec-time').value = this.toLocalDatetimeInput(t);
    }

    toLocalDatetimeInput(date) {
        const pad = (n) => String(n).padStart(2, '0');
        return (
            `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T` +
            `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
        );
    }

    formatExecTimeForApi(value) {
        if (!value) return '';
        const normalized = value.includes('T') ? value.replace('T', ' ') : value;
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(normalized)) {
            return `${normalized}:00`;
        }
        return normalized;
    }

    async checkPlatformConnection(platform) {
        const tipEl = document.getElementById('platform-verify-tip');
        if (!tipEl) return;

        if (platform !== 'wechat') {
            tipEl.style.display = 'block';
            tipEl.className = 'scheduler-verify-tip text-secondary';
            tipEl.innerText = '该平台暂不支持定时自动发布';
            return;
        }

        tipEl.style.display = 'block';
        tipEl.className = 'scheduler-verify-tip text-secondary';
        tipEl.innerText = '正在校验公众号 AppID / AppSecret…';

        try {
            const data = await this._fetchJson(`/api/scheduler/verify-platform?platform=${platform}`);
            if (data.success) {
                tipEl.className = 'scheduler-verify-tip text-success';
                tipEl.innerText = '公众号连接正常，可定时发布';
            } else {
                tipEl.className = 'scheduler-verify-tip text-error';
                tipEl.innerHTML = `校验未通过：${this.escapeHtml(data.message || '')} <a href="#" onclick="window.app.showView('config-manager');return false;">去配置</a>`;
            }
        } catch {
            tipEl.className = 'scheduler-verify-tip text-error';
            tipEl.innerText = '检测失败，请稍后重试';
        }
    }

    async saveTask() {
        const topic = document.getElementById('task-topic').value.trim();
        const execTime = document.getElementById('task-exec-time').value;
        const platform = document.getElementById('task-platform').value;
        const isRecurring = document.getElementById('task-recurring').checked;
        const interval = document.getElementById('task-interval').value;
        const articleCount = document.getElementById('task-article-count').value;
        const useAIBeautify = document.getElementById('task-beautify').checked;
        const collectionMode = document.getElementById('task-collection-mode').checked;

        if (!execTime) {
            window.showNotification ? window.showNotification('请选择执行时间', 'warning') : alert('请选择执行时间');
            return;
        }

        if (platform !== 'wechat') {
            window.showNotification
                ? window.showNotification('当前仅支持微信公众号定时发布', 'warning')
                : alert('当前仅支持微信公众号定时发布');
            return;
        }

        const formattedTime = this.formatExecTimeForApi(execTime);

        try {
            const response = await fetch('/api/scheduler/tasks', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this._authHeaders(),
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    topic,
                    execution_time: formattedTime,
                    platform,
                    is_recurring: isRecurring,
                    interval_hours: parseInt(interval, 10) || 24,
                    article_count: parseInt(articleCount, 10) || 1,
                    use_ai_beautify: useAIBeautify,
                    collection_mode: collectionMode,
                }),
            });

            if (response.ok) {
                const result = await response.json();
                this.lastCreatedTaskId = result.id ? String(result.id) : null;
                this.closeModal();
                await this.refreshData(false);
                const label = topic || '自动热点任务';
                window.showNotification
                    ? window.showNotification(`任务已保存：${label}`, 'success')
                    : alert('任务已保存');
            } else {
                const err = await response.json();
                alert('保存失败: ' + (err.detail || '未知错误'));
            }
        } catch (error) {
            console.error('Save task failed:', error);
            alert('保存失败，请检查网络后重试');
        }
    }

    async toggleTask(id, currentStatus) {
        const newStatus = currentStatus === 'enabled' ? 'disabled' : 'enabled';
        try {
            const response = await fetch(`/api/scheduler/tasks/${id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...this._authHeaders(),
                },
                credentials: 'same-origin',
                body: JSON.stringify({ status: newStatus }),
            });
            if (response.ok) await this.refreshData(false);
        } catch (error) {
            console.error('Toggle task failed:', error);
        }
    }

    async deleteTask(id) {
        if (!confirm('确定删除该定时任务？')) return;
        const prevTasks = [...this.tasks];
        this.tasks = this.tasks.filter((t) => t.id !== id);
        this.renderTasks();
        this.renderSidebarTasks();
        this.updateStats();
        try {
            const response = await fetch(`/api/scheduler/tasks/${id}`, {
                method: 'DELETE',
                headers: this._authHeaders(),
                credentials: 'same-origin',
            });
            if (response.ok) {
                if (this.lastCreatedTaskId === id) this.lastCreatedTaskId = null;
                await this.refreshData(false, true);
            } else {
                this.tasks = prevTasks;
                this.renderTasks();
                this.renderSidebarTasks();
                this.updateStats();
                const err = await response.json().catch(() => ({}));
                const msg = err.detail || '删除失败';
                if (window.showNotification) {
                    window.showNotification(msg, 'error');
                } else {
                    alert(msg);
                }
            }
        } catch (error) {
            console.error('Delete task failed:', error);
            this.tasks = prevTasks;
            this.renderTasks();
            this.renderSidebarTasks();
            this.updateStats();
            if (window.showNotification) {
                window.showNotification('删除失败，请检查网络后重试', 'error');
            }
        }
    }

    getStatusText(status) {
        const map = {
            enabled: '等待中',
            disabled: '已暂停',
            running: '执行中',
            completed: '已完成',
            failed: '失败',
        };
        return map[status] || status;
    }

    truncate(str, len) {
        if (!str) return '';
        return str.length > len ? str.substring(0, len) + '…' : str;
    }

    getDefaultExecTime() {
        const t = new Date(Date.now() + 5 * 60 * 1000);
        t.setMilliseconds(0);
        return this.toLocalDatetimeInput(t);
    }
}

window.schedulerManager = new SchedulerManager();
document.addEventListener('DOMContentLoaded', () => {
    window.schedulerManager.init();
});
