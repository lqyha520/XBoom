/**
 * SchedulerManager - scheduled publishing tasks.
 */

class SchedulerManager {
    constructor() {
        this.tasks = [];
        this.logs = [];
        this.wechatCredentials = [];
        this.selectedTaskId = null;
        this.lastCreatedTaskId = null;
        this.refreshInterval = null;
        this._initialized = false;
        this._loading = false;
        this._pendingRefresh = false;
        this._lastError = '';
        this._onWechatCredentialsUpdated = () => {
            this.refreshData(false, true);
        };
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
        document.addEventListener('wechat-credentials-updated', this._onWechatCredentialsUpdated);
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
            await Promise.all([this.fetchTasks(), this.fetchLogs(), this.fetchWechatCredentials()]);
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
        ['scheduler-refresh-btn', 'scheduler-refresh-btn-lite'].forEach((id) => {
            const btn = document.getElementById(id);
            if (!btn) return;
            btn.disabled = loading;
            btn.textContent = loading ? '刷新中...' : (id === 'scheduler-refresh-btn' ? '刷新列表' : '刷新');
        });
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
        el.textContent = `任务列表加载失败：${msg}。请点击右上角“刷新”，或重新打开本页。`;
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
        return { 'X-App-Client-Token': token };
    }

    _getCookie(name) {
        const prefix = `${name}=`;
        const row = document.cookie.split(';').map((c) => c.trim()).find((c) => c.startsWith(prefix));
        return row ? decodeURIComponent(row.slice(prefix.length)) : '';
    }

    async _fetchJson(url, options = {}) {
        const response = await fetch(url, {
            headers: { ...this._authHeaders(), ...(options.headers || {}) },
            credentials: 'same-origin',
            ...options,
        });
        if (!response.ok) {
            let detail = response.statusText;
            try {
                const body = await response.json();
                detail = body.detail || body.message || detail;
            } catch {
                // ignore non-JSON errors
            }
            throw new Error(`${response.status} ${detail}`);
        }
        return response.json();
    }

    async fetchTasks() {
        this.tasks = await this._fetchJson('/api/scheduler/tasks');
        if (!Array.isArray(this.tasks)) this.tasks = [];
    }

    async fetchLogs() {
        try {
            this.logs = await this._fetchJson('/api/scheduler/logs?limit=50');
            if (!Array.isArray(this.logs)) this.logs = [];
        } catch (error) {
            console.error('Fetch logs failed:', error);
            this.logs = [];
        }
    }

    _normalizeWechatCredential(credential, index = 0, defaultAccountId = '') {
        if (!credential || typeof credential !== 'object') return null;
        const accountId = String(credential.account_id || '').trim();
        const appid = String(credential.appid || '').trim();
        const name = String(credential.name || credential.author || `公众号 ${index + 1}`).trim() || `公众号 ${index + 1}`;
        const hasSecret = credential.has_secret === true || Boolean(String(credential.appsecret || '').trim());
        return {
            account_id: accountId,
            appid,
            author: String(credential.author || name).trim() || name,
            name,
            draft_only: credential.draft_only === true,
            status: credential.status || 'unchecked',
            enabled: credential.enabled !== false,
            configured: credential.configured === true || Boolean(appid && hasSecret),
            is_default: credential.is_default === true || Boolean(accountId && accountId === defaultAccountId),
        };
    }

    _credentialsFromConfig(configPayload) {
        const config = configPayload?.data || configPayload || {};
        const wechat = config.wechat || {};
        const defaultAccountId = String(wechat.default_account_id || '').trim();
        const credentials = Array.isArray(wechat.credentials) ? wechat.credentials : [];
        return credentials
            .map((credential, index) => this._normalizeWechatCredential(credential, index, defaultAccountId))
            .filter(Boolean);
    }

    _mergeWechatCredentials(...sources) {
        const merged = [];
        for (const source of sources) {
            for (const credential of (Array.isArray(source) ? source : [])) {
                const existing = merged.find((item) =>
                    (item.account_id && credential.account_id && item.account_id === credential.account_id)
                    || (item.appid && credential.appid && item.appid === credential.appid)
                );
                if (!existing) {
                    merged.push({ ...credential });
                    continue;
                }
                const wasConfigured = existing.configured === true;
                const wasDefault = existing.is_default === true;
                Object.assign(existing, credential);
                existing.configured = wasConfigured || credential.configured === true;
                existing.is_default = wasDefault || credential.is_default === true;
            }
        }
        return merged;
    }

    async fetchWechatCredentials() {
        let endpointCredentials = [];
        let endpointError = null;
        try {
            const response = await this._fetchJson(`/api/scheduler/wechat-credentials?_=${Date.now()}`, { cache: 'no-store' });
            endpointCredentials = Array.isArray(response)
                ? response.map((credential, index) => this._normalizeWechatCredential(credential, index)).filter(Boolean)
                : [];
        } catch (error) {
            console.error('Fetch wechat credentials failed:', error);
            endpointError = error;
        }

        const localConfig = window.configManager?.getConfig?.() || window.configManager?.config || {};
        let configCredentials = this._credentialsFromConfig(localConfig);
        if (endpointCredentials.length === 0 && configCredentials.length === 0) {
            try {
                const configResponse = await this._fetchJson(`/api/config?_=${Date.now()}`, { cache: 'no-store' });
                configCredentials = this._credentialsFromConfig(configResponse);
            } catch (error) {
                console.error('Fetch config credentials fallback failed:', error);
                endpointError ||= error;
            }
        }

        this.wechatCredentials = this._mergeWechatCredentials(endpointCredentials, configCredentials);
        this.renderWechatCredentials();
        return this.wechatCredentials.length > 0 || !endpointError;
    }

    async refreshWechatCredentials(showToast = false) {
        const button = document.getElementById('task-refresh-wechat');
        const tip = document.getElementById('task-account-refresh-tip');
        if (button) {
            button.disabled = true;
            button.textContent = '刷新中...';
        }
        if (tip) tip.textContent = '正在读取最新公众号配置...';

        const success = await this.fetchWechatCredentials();
        const accountSelect = document.getElementById('task-target-appid');
        if (tip && accountSelect?.dataset.staleBinding !== 'true') {
            tip.textContent = success
                ? (this.wechatCredentials.length > 0
                    ? `已同步 ${this.wechatCredentials.length} 个公众号，可分别固定绑定到不同任务`
                    : '未读取到公众号，请先在设置中添加并保存公众号')
                : '刷新失败，请检查网络后重试';
        }
        if (button) {
            button.disabled = false;
            button.textContent = '刷新';
        }
        if (showToast) {
            this._notify(
                success
                    ? (this.wechatCredentials.length > 0
                        ? `公众号列表已刷新，共 ${this.wechatCredentials.length} 个，可为不同任务分别选择`
                        : '没有已保存的公众号，请先前往设置添加')
                    : '公众号列表刷新失败',
                success ? 'success' : 'error'
            );
        }
        return success;
    }

    renderWechatCredentials() {
        const select = document.getElementById('task-target-appid');
        if (!select) return;
        const current = select.value;
        select.innerHTML = '<option value="__default__">跟随默认公众号</option><option value="__none__">不绑定公众号</option>';
        for (const [index, cred] of this.wechatCredentials.entries()) {
            const displayName = String(cred.name || cred.author || `公众号 ${index + 1}`).trim() || `公众号 ${index + 1}`;
            const defaultBadge = cred.is_default ? ' · 默认' : '';
            const label = cred.appid ? `${displayName}${defaultBadge} (${cred.appid})` : `${displayName}（未配置 AppID）`;
            const opt = document.createElement('option');
            opt.value = cred.account_id || cred.appid;
            opt.dataset.appid = cred.appid;
            opt.disabled = cred.enabled === false || cred.configured === false;
            opt.textContent = label;
            select.appendChild(opt);
        }
        if (current) select.value = current;
        const selectedTask = this.selectedTaskId && this.tasks.find(item => String(item.id) === String(this.selectedTaskId));
        const selectedTaskMatch = selectedTask && this.wechatCredentials.find((cred) =>
            cred.account_id === selectedTask.target_account_id ||
            (selectedTask.target_appid && cred.appid === selectedTask.target_appid)
        );
        if (current && select.value !== current) {
            if (selectedTaskMatch) select.value = selectedTaskMatch.account_id || selectedTaskMatch.appid;
        }
        const tip = document.getElementById('task-account-refresh-tip');
        if (selectedTask?.account_binding_mode === 'default') {
            select.value = '__default__';
        } else if (selectedTask?.account_binding_mode === 'none') {
            select.value = '__none__';
        }
        if (selectedTask && selectedTask.account_binding_mode === 'fixed' && !selectedTaskMatch) {
            select.dataset.staleBinding = 'true';
            if (tip) tip.textContent = '原绑定公众号已删除，请刷新后重新选择公众号';
        } else {
            delete select.dataset.staleBinding;
        }
    }

    _getCredentialLabel(accountRef, appid = '') {
        if (!accountRef) return '全部';
        const cred = this.wechatCredentials.find(c =>
            c.account_id === accountRef || c.appid === accountRef || (appid && c.appid === appid)
        );
        return cred ? (cred.name || cred.author || cred.appid) : '已删除公众号（请重新选择）';
    }

    _bindingLabel(task) {
        const name = task.resolved_account_name || '';
        if (task.account_binding_mode === 'default') {
            return name ? `跟随默认 · ${name}` : '跟随默认 · 未设置';
        }
        if (task.account_binding_mode === 'none') return '不绑定公众号';
        if (task.binding_status === 'missing_account') return '原公众号已删除';
        if (task.binding_status === 'disabled') return `${name || '固定公众号'} · 已暂停`;
        if (task.binding_status === 'unconfigured') return `${name || '固定公众号'} · 配置不完整`;
        return `固定绑定 · ${name || this._getCredentialLabel(task.target_account_id || task.target_appid, task.target_appid)}`;
    }

    _shortId(id) {
        if (!id) return '-';
        const s = String(id);
        return s.length > 8 ? s.slice(0, 8) : s;
    }

    _taskLabel(task) {
        const topic = (task.topic || '').trim();
        return topic || '（到点自动抓热点）';
    }

    _isRunningStatus(status) {
        return status === 'running' || status === 'cancel_requested';
    }

    renderSidebarTasks() {
        const box = document.getElementById('scheduler-sidebar-task-list');
        if (!box) return;

        if (this.tasks.length === 0) {
            box.innerHTML = '<p class="text-secondary" style="font-size:12px;margin:8px 0;line-height:1.5;">暂无任务<br>点“新建任务”创建</p>';
            return;
        }

        box.innerHTML = this.tasks.map((task) => {
            const active = this.lastCreatedTaskId === task.id ? ' is-new' : '';
            const id = this.escapeAttr(task.id);
            return `
            <div class="scheduler-sidebar-task-item${active}" data-task-id="${id}"
                onclick="window.schedulerManager.highlightTask('${id}')" title="任务编号 ${this.escapeAttr(task.id)}">
                <div class="scheduler-sidebar-task-title">${this.escapeHtml(this.truncate(this._taskLabel(task), 22))}</div>
                <div class="scheduler-sidebar-task-meta">
                    <span class="status-badge status-${this.escapeAttr(task.status)}" style="font-size:10px;padding:1px 6px;">
                        ${this.getStatusText(task.status)}
                    </span>
                    <span>${this.escapeHtml(task.execution_time || '')}</span>
                </div>
                <div class="scheduler-sidebar-task-id">#${this.escapeHtml(this._shortId(task.id))}</div>
            </div>`;
        }).join('');
    }

    highlightTask(taskId) {
        const row = document.querySelector(`#scheduler-task-list tr[data-task-id="${CSS.escape(taskId)}"]`);
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

        if (hint) hint.textContent = this.tasks.length > 0 ? `共 ${this.tasks.length} 条，按下次执行时间排序` : '';

        if (this.tasks.length === 0) {
            container.innerHTML = '<tr><td colspan="7" class="text-center py-5">暂无任务。点右上角“+ 新建任务”创建，保存后会显示在这里</td></tr>';
            return;
        }

        container.innerHTML = this.tasks.map((task) => {
            const rowClass = this.lastCreatedTaskId === task.id ? ' class="scheduler-row-new"' : '';
            const id = this.escapeAttr(task.id);
            const isRunning = this._isRunningStatus(task.status);
            const bindingError = ['missing_account', 'missing_default', 'unconfigured', 'disabled'].includes(task.binding_status);
            const bindingColor = bindingError ? 'var(--danger-color)' : 'var(--text-secondary)';
            const preflightText = task.preflight_status === 'error' && task.preflight_message
                ? `<br><span style="font-size:10px;color:var(--danger-color);">${this.escapeHtml(task.preflight_message)}</span>`
                : '';
            const toggleTitle = isRunning ? '运行中不可切换，请先取消本次执行' : (task.status === 'enabled' ? '暂停' : '启用');
            return `
            <tr${rowClass} data-task-id="${id}">
                <td class="scheduler-id-cell" title="${this.escapeAttr(task.id)}">#${this.escapeHtml(this._shortId(task.id))}</td>
                <td class="font-medium" title="${this.escapeAttr(this._taskLabel(task))}">${this.escapeHtml(this.truncate(this._taskLabel(task), 36))}</td>
                <td><span class="tag tag-outline">${this.escapeHtml(this.platformLabels[task.platform] || task.platform)}</span><br><span class="text-secondary" style="font-size:11px;">${this.escapeHtml(({none:'只生成文章',save:'存草稿',publish:'正式发布'})[task.post_action] || '正式发布')}</span><br><span style="font-size:11px;color:${bindingColor};">→ ${this.escapeHtml(this._bindingLabel(task))}</span>${preflightText}</td>
                <td style="white-space:nowrap;font-size:13px;">${this.escapeHtml(task.execution_time || '-')}</td>
                <td>${this.getRepeatText(task)}</td>
                <td><span class="status-badge status-${this.escapeAttr(task.status)}">${this.getStatusText(task.status)}</span></td>
                <td>
                    <div class="table-actions">
                        ${isRunning ? this._cancelButton(id) : ''}
                        ${bindingError
                            ? `<button class="btn btn-icon btn-sm" onclick="window.schedulerManager.repairTaskBinding('${id}')" title="修复公众号绑定"${isRunning ? ' disabled' : ''}>↻</button>`
                            : task.preflight_status === 'error'
                                ? `<button class="btn btn-icon btn-sm" onclick="window.schedulerManager.preflightTask('${id}')" title="重新预检"${isRunning ? ' disabled' : ''}>✓</button>`
                                : ''}
                        <button class="btn btn-icon btn-sm" onclick="window.schedulerManager.openEditTaskModal('${id}')" title="编辑"${isRunning ? ' disabled' : ''}>
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                        </button>
                        <button class="btn btn-icon btn-sm" onclick="window.schedulerManager.toggleTask('${id}', '${this.escapeAttr(task.status)}')" title="${toggleTitle}"${isRunning ? ' disabled' : ''}>
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                ${task.status === 'enabled' ? '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>' : '<polygon points="5 3 19 12 5 21 5 3"></polygon>'}
                            </svg>
                        </button>
                        <button class="btn btn-icon btn-sm" onclick="window.schedulerManager.deleteTask('${id}')" title="删除"${isRunning ? ' disabled' : ''}>
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>`;
        }).join('');

        if (this.lastCreatedTaskId) setTimeout(() => this.highlightTask(this.lastCreatedTaskId), 300);
    }

    _cancelButton(id) {
        return `
        <button class="btn btn-icon btn-sm" onclick="window.schedulerManager.cancelTask('${id}')" title="取消本次执行">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="9"></circle>
                <line x1="9" y1="9" x2="15" y2="15"></line>
                <line x1="15" y1="9" x2="9" y2="15"></line>
            </svg>
        </button>`;
    }

    renderLogs() {
        const container = document.getElementById('scheduler-log-list');
        if (!container) return;

        if (this.logs.length === 0) {
            container.innerHTML = '<tr><td colspan="4" class="text-center py-5">暂无执行记录</td></tr>';
            return;
        }

        container.innerHTML = this.logs.map((entry) => {
            const taskId = String(entry.task_id || '');
            const task = this.tasks.find((t) => String(t.id) === taskId);
            const taskHint = task
                ? `<span class="text-secondary" style="font-size:11px;">#${this.escapeHtml(this._shortId(task.id))} ${this.escapeHtml(this.truncate(this._taskLabel(task), 12))}</span><br>`
                : taskId
                  ? `<span class="text-secondary" style="font-size:11px;">#${this.escapeHtml(this._shortId(taskId))}</span><br>`
                  : '';
            return `
            <tr>
                <td class="text-secondary" style="font-size:12px;white-space:nowrap;">${this.escapeHtml(entry.run_time || '')}</td>
                <td><span class="status-badge status-${this.escapeAttr(entry.status)}" style="padding:2px 6px;font-size:11px;">${this.getLogStatusText(entry.status)}</span></td>
                <td style="font-size:13px;">${taskHint}${this.escapeHtml(entry.message || '')}</td>
                <td>${entry.article_id ? `<button class="btn btn-link btn-sm" onclick="window.articleManager.viewArticle('${this.escapeAttr(entry.article_id)}')">查看</button>` : '-'}</td>
            </tr>`;
        }).join('');
    }

    escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    escapeAttr(str) {
        return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }

    updateStats() {
        const activeCount = this.tasks.filter((t) => ['enabled', 'running', 'cancel_requested'].includes(t.status)).length;
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
        document.getElementById('task-target-appid').value = '__default__';
        document.getElementById('task-post-action').value = 'save';
        document.getElementById('task-image-style').value = 'auto';
        document.getElementById('task-exec-time').value = this.getDefaultExecTime();
        document.getElementById('task-repeat-mode').value = 'once';
        document.getElementById('task-beautify').checked = true;
        document.getElementById('task-article-count').value = '1';
        document.getElementById('task-collection-mode').checked = false;
        document.getElementById('task-interval').value = '24';
        document.getElementById('task-interval-group').style.display = 'none';
        const tip = document.getElementById('platform-verify-tip');
        if (tip) tip.style.display = 'none';
        document.getElementById('task-edit-modal').style.display = 'flex';
        document.querySelector('#task-edit-modal .modal-body')?.scrollTo(0, 0);
        this.checkPlatformConnection('wechat');
        this.renderWechatCredentials();
        this.fetchWechatCredentials();
    }

    openEditTaskModal(id) {
        const task = this.tasks.find(t => String(t.id) === String(id));
        if (!task) return;
        if (this._isRunningStatus(task.status)) {
            this._notify('任务正在执行，无法编辑', 'warning');
            return;
        }
        this.selectedTaskId = id;
        document.getElementById('task-modal-title').innerText = '编辑定时任务';
        document.getElementById('task-topic').value = task.topic || '';
        document.getElementById('task-platform').value = task.platform || 'wechat';
        document.getElementById('task-target-appid').value = task.account_binding_mode === 'default'
            ? '__default__'
            : task.account_binding_mode === 'none'
                ? '__none__'
                : (task.target_account_id || task.target_appid || '');
        document.getElementById('task-post-action').value = task.post_action || 'publish';
        document.getElementById('task-image-style').value = task.image_style || 'auto';
        // execution_time 格式: "2026-06-24 08:00:00" -> "2026-06-24T08:00:00"
        const execTime = (task.execution_time || '').replace(' ', 'T');
        document.getElementById('task-exec-time').value = execTime;
        const repeatMode = task.repeat_mode || (task.is_recurring ? 'interval' : 'once');
        document.getElementById('task-repeat-mode').value = repeatMode;
        document.getElementById('task-beautify').checked = task.use_ai_beautify !== false;
        document.getElementById('task-article-count').value = task.article_count || 1;
        document.getElementById('task-collection-mode').checked = !!task.collection_mode;
        document.getElementById('task-interval').value = task.interval_hours || 24;
        this.toggleRepeatMode(repeatMode);
        const tip = document.getElementById('platform-verify-tip');
        if (tip) tip.style.display = 'none';
        document.getElementById('task-edit-modal').style.display = 'flex';
        document.querySelector('#task-edit-modal .modal-body')?.scrollTo(0, 0);
        this.checkPlatformConnection(task.platform || 'wechat');
        this.renderWechatCredentials();
        this.fetchWechatCredentials();
    }

    closeModal() {
        document.getElementById('task-edit-modal').style.display = 'none';
    }

    toggleRepeatMode(mode) {
        document.getElementById('task-interval-group').style.display = mode === 'interval' ? 'block' : 'none';
    }

    setDelayTime(seconds) {
        const target = new Date(Date.now() + seconds * 1000);
        document.getElementById('task-exec-time').value = this.toLocalDatetimeInput(target);
    }

    setPresetDaily(hour) {
        const target = new Date();
        target.setHours(hour, 0, 0, 0);
        if (target.getTime() <= Date.now()) target.setDate(target.getDate() + 1);
        document.getElementById('task-exec-time').value = this.toLocalDatetimeInput(target);
        document.getElementById('task-repeat-mode').value = 'daily';
        this.toggleRepeatMode('daily');
    }

    getRepeatText(task) {
        const mode = task.repeat_mode || (task.is_recurring ? 'interval' : 'once');
        if (mode === 'daily') {
            const match = String(task.execution_time || '').match(/\b(\d{2}:\d{2})/);
            return `每天 ${this.escapeHtml(match ? match[1] : '--:--')}`;
        }
        if (mode === 'interval') return `每 ${this.escapeHtml(task.interval_hours || 24)} 小时`;
        return '单次';
    }

    toLocalDatetimeInput(date) {
        const pad = (n) => String(n).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }

    formatExecTimeForApi(value) {
        if (!value) return '';
        const normalized = value.includes('T') ? value.replace('T', ' ') : value;
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(normalized)) return `${normalized}:00`;
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
        tipEl.innerText = '正在校验公众号 AppID / AppSecret...';

        try {
            const data = await this._fetchJson(`/api/scheduler/verify-platform?platform=${encodeURIComponent(platform)}`);
            if (data.success) {
                tipEl.className = 'scheduler-verify-tip text-success';
                tipEl.innerText = '公众号连接正常，可定时发布';
            } else {
                tipEl.className = 'scheduler-verify-tip text-error';
                tipEl.textContent = `校验未通过：${data.message || ''}。请前往配置页面检查公众号凭据。`;
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
        const targetAccountId = document.getElementById('task-target-appid').value;
        const accountSelect = document.getElementById('task-target-appid');
        const bindingMode = targetAccountId === '__default__' ? 'default' : targetAccountId === '__none__' ? 'none' : 'fixed';
        const targetCredential = this.wechatCredentials.find(c => (c.account_id || c.appid) === targetAccountId);
        const repeatMode = document.getElementById('task-repeat-mode').value;
        const interval = document.getElementById('task-interval').value;
        const articleCount = document.getElementById('task-article-count').value;
        const useAIBeautify = document.getElementById('task-beautify').checked;
        const imageStyle = document.getElementById('task-image-style').value;
        const collectionMode = document.getElementById('task-collection-mode').checked;
        const postAction = document.getElementById('task-post-action').value;

        if (!execTime) {
            this._notify('请选择执行时间', 'warning');
            return;
        }
        if (platform !== 'wechat') {
            this._notify('当前仅支持微信公众号定时发布', 'warning');
            return;
        }
        if (accountSelect?.dataset.staleBinding === 'true' && bindingMode === 'fixed' && !targetCredential) {
            this._notify('原绑定公众号已删除，请重新选择一个公众号', 'warning');
            return;
        }
        if (bindingMode === 'none' && postAction !== 'none') {
            this._notify('存草稿或正式发布必须选择公众号', 'warning');
            return;
        }

        try {
            const body = {
                topic,
                execution_time: this.formatExecTimeForApi(execTime),
                platform,
                is_recurring: repeatMode !== 'once',
                repeat_mode: repeatMode,
                interval_hours: repeatMode === 'daily' ? 24 : (parseInt(interval, 10) || 24),
                article_count: parseInt(articleCount, 10) || 1,
                use_ai_beautify: useAIBeautify,
                image_style: imageStyle,
                collection_mode: collectionMode,
                post_action: postAction,
                account_binding_mode: bindingMode,
            };
            body.target_account_id = bindingMode === 'fixed' ? targetAccountId : null;
            body.target_appid = bindingMode === 'fixed' ? (targetCredential?.appid || null) : null;

            let result;
            if (this.selectedTaskId) {
                // 编辑模式：PUT 更新
                result = await this._fetchJson(`/api/scheduler/tasks/${encodeURIComponent(this.selectedTaskId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
            } else {
                // 新建模式：POST 创建
                result = await this._fetchJson('/api/scheduler/tasks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                this.lastCreatedTaskId = result.id ? String(result.id) : null;
            }
            this.closeModal();
            await this.refreshData(false);
            this._notify(`任务已${this.selectedTaskId ? '更新' : '保存'}：${topic || '自动热点任务'}`, 'success');
        } catch (error) {
            console.error('Save task failed:', error);
            this._notify(`保存失败：${error.message || '请检查网络后重试'}`, 'error');
        }
    }

    async toggleTask(id, currentStatus) {
        if (this._isRunningStatus(currentStatus)) {
            this._notify('任务正在执行，请使用取消本次执行', 'warning');
            return;
        }
        const task = this.tasks.find(item => String(item.id) === String(id));
        if (currentStatus !== 'enabled' && task?.preflight_status === 'error') {
            await this.preflightTask(id);
            return;
        }
        const newStatus = currentStatus === 'enabled' ? 'disabled' : 'enabled';
        try {
            await this._fetchJson(`/api/scheduler/tasks/${encodeURIComponent(id)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
            await this.refreshData(false);
        } catch (error) {
            console.error('Toggle task failed:', error);
            this._notify(`操作失败：${error.message}`, 'error');
        }
    }

    async preflightTask(id) {
        try {
            this._notify('正在检查公众号、模型和图片配置...', 'info');
            const result = await this._fetchJson(`/api/scheduler/tasks/${encodeURIComponent(id)}/preflight`, {
                method: 'POST',
            });
            await this.refreshData(false, true);
            this._notify(result.message || '执行前检查通过', result.status === 'success' ? 'success' : 'error');
        } catch (error) {
            await this.refreshData(false, true);
            this._notify(`预检失败：${error.message}`, 'error');
        }
    }

    repairTaskBinding(id) {
        this.openEditTaskModal(id);
        window.setTimeout(() => {
            const select = document.getElementById('task-target-appid');
            if (!select) return;
            select.scrollIntoView({ behavior: 'smooth', block: 'center' });
            select.focus();
            select.classList.add('scheduler-field-attention');
            window.setTimeout(() => select.classList.remove('scheduler-field-attention'), 1800);
        }, 50);
    }

    async cancelTask(id) {
        const task = this.tasks.find((t) => String(t.id) === String(id));
        if (!task || !this._isRunningStatus(task.status)) {
            this._notify('当前没有正在执行的定时任务', 'info');
            return;
        }
        if (task.status === 'cancel_requested') {
            this._notify('已经请求取消，正在等待当前步骤收尾', 'info');
            return;
        }

        try {
            await this._fetchJson(`/api/scheduler/tasks/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
            task.status = 'cancel_requested';
            this.renderTasks();
            this.renderSidebarTasks();
            this.updateStats();
            this._notify('已请求取消本次定时任务', 'success');
            await this.refreshData(false, true);
        } catch (error) {
            console.error('Cancel task failed:', error);
            this._notify(`取消失败：${error.message}`, 'error');
        }
    }

    async deleteTask(id) {
        const task = this.tasks.find((t) => String(t.id) === String(id));
        if (task && this._isRunningStatus(task.status)) {
            this._notify('任务正在执行，请先取消本次执行', 'warning');
            return;
        }
        if (!confirm('确定删除该定时任务？')) return;

        const prevTasks = [...this.tasks];
        this.tasks = this.tasks.filter((t) => String(t.id) !== String(id));
        this.renderTasks();
        this.renderSidebarTasks();
        this.updateStats();

        try {
            await this._fetchJson(`/api/scheduler/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
            if (this.lastCreatedTaskId === id) this.lastCreatedTaskId = null;
            await this.refreshData(false, true);
        } catch (error) {
            console.error('Delete task failed:', error);
            this.tasks = prevTasks;
            this.renderTasks();
            this.renderSidebarTasks();
            this.updateStats();
            this._notify(`删除失败：${error.message}`, 'error');
        }
    }

    getStatusText(status) {
        const map = {
            enabled: '等待中',
            disabled: '已暂停',
            running: '执行中',
            cancel_requested: '取消中',
            cancelled: '已取消',
            completed: '已完成',
            failed: '失败',
        };
        return map[status] || status;
    }

    getLogStatusText(status) {
        const map = {
            success: '成功',
            failed: '失败',
            running: '运行中',
            cancel_requested: '取消中',
            cancelled: '已取消',
        };
        return map[status] || status;
    }

    truncate(str, len) {
        if (!str) return '';
        return str.length > len ? `${str.substring(0, len)}...` : str;
    }

    getDefaultExecTime() {
        const target = new Date(Date.now() + 5 * 60 * 1000);
        target.setMilliseconds(0);
        return this.toLocalDatetimeInput(target);
    }

    _notify(message, type = 'info') {
        if (window.showNotification) {
            window.showNotification(message, type);
        } else if (type === 'error' || type === 'warning') {
            alert(message);
        }
    }
}

window.schedulerManager = new SchedulerManager();
document.addEventListener('DOMContentLoaded', () => {
    window.schedulerManager.init();
});
