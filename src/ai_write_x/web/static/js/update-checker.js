class UpdateChecker {
    constructor() {
        if (window.__aiwritexUpdateCheckerInstance) {
            return window.__aiwritexUpdateCheckerInstance;
        }

        this.policy = null;
        this.progressTimer = null;
        this.forceMode = false;
        this.silentAutoMode = false;
        this.autoRestartTriggered = false;
        this.currentStepId = 'check';
        this.elements = {};

        this.STEPS = [
            { id: 'check', label: '检查版本', desc: '正在连接更新服务器…' },
            { id: 'download', label: '下载安装包', desc: '准备下载…' },
            { id: 'install', label: '安装更新', desc: '静默解压安装包（约 1～3 分钟）' },
            { id: 'restart', label: '重启应用', desc: '窗口关闭后请稍候，正在启动新版本' },
        ];

        window.__aiwritexUpdateCheckerInstance = this;

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init(), { once: true });
        } else {
            this.init();
        }
    }

    init() {
        this.cacheElements();
        this.renderStepList();
        this.ensureForceOverlay();
        this.scheduleStartupPolicyCheck();
    }

    scheduleStartupPolicyCheck() {
        const run = () => this.checkStartupPolicy();
        if (window.APP_CLIENT_TOKEN || this.getCookie('app_client_token')) {
            run();
            return;
        }
        document.addEventListener('pywebviewready', run, { once: true });
        setTimeout(run, 2500);
    }

    cacheElements() {
        this.elements.modal = document.getElementById('update-modal-overlay');
        this.elements.stepList = document.getElementById('update-step-list');
        this.elements.versionRow = document.getElementById('update-version-row');
        this.elements.currentVersion = document.getElementById('update-current-version');
        this.elements.latestVersion = document.getElementById('update-latest-version');
        this.elements.releaseNotes = document.getElementById('update-release-notes');
        this.elements.progressBlock = document.getElementById('update-progress-block');
        this.elements.progressBar = document.getElementById('update-progress-inner');
        this.elements.progressText = document.getElementById('update-progress-percent');
        this.elements.progressLabel = document.getElementById('update-progress-label');
        this.elements.logTerminal = document.getElementById('update-log-terminal');
        this.elements.logToggle = document.getElementById('update-log-toggle');
        this.elements.footerHint = document.getElementById('update-footer-hint');
        this.elements.footerRight = document.querySelector('#update-modal-overlay .update-footer-actions');
        this.elements.closeButton = document.querySelector('#update-modal-overlay .update-close-btn');
    }

    renderStepList() {
        if (!this.elements.stepList) return;
        this.elements.stepList.innerHTML = this.STEPS.map((step, index) => `
            <li class="update-step-item is-pending" data-step="${step.id}" id="update-step-${step.id}">
                <div class="update-step-icon">${index + 1}</div>
                <div class="update-step-content">
                    <div class="update-step-label">${step.label}</div>
                    <div class="update-step-desc" id="update-step-desc-${step.id}">${step.desc}</div>
                </div>
            </li>
        `).join('');
    }

    setStep(stepId, state, desc) {
        this.currentStepId = stepId;
        const order = this.STEPS.map((s) => s.id);
        const activeIndex = order.indexOf(stepId);

        order.forEach((id, index) => {
            const el = document.getElementById(`update-step-${id}`);
            const descEl = document.getElementById(`update-step-desc-${id}`);
            if (!el) return;

            el.classList.remove('is-pending', 'is-active', 'is-done', 'is-error');
            if (state === 'error' && id === stepId) {
                el.classList.add('is-error');
                if (descEl && desc) descEl.textContent = desc;
                return;
            }
            if (index < activeIndex) {
                el.classList.add('is-done');
                const icon = el.querySelector('.update-step-icon');
                if (icon) icon.textContent = '✓';
            } else if (index === activeIndex) {
                el.classList.add(state === 'done' ? 'is-done' : 'is-active');
                if (state === 'done') {
                    const icon = el.querySelector('.update-step-icon');
                    if (icon) icon.textContent = '✓';
                }
                if (descEl && desc) descEl.textContent = desc;
            } else {
                el.classList.add('is-pending');
            }
        });
    }

    setFooterHint(text) {
        if (this.elements.footerHint) {
            this.elements.footerHint.textContent = text;
        }
    }

    showProgressBlock(show) {
        if (this.elements.progressBlock) {
            this.elements.progressBlock.classList.toggle('is-hidden', !show);
        }
    }

    showVersionRow(show) {
        if (this.elements.versionRow) {
            this.elements.versionRow.style.display = show ? 'flex' : 'none';
        }
    }

    showReleaseNotes(show) {
        if (this.elements.releaseNotes) {
            this.elements.releaseNotes.classList.toggle('is-hidden', !show);
        }
    }

    ensureForceOverlay() {
        let overlay = document.getElementById('force-update-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'force-update-overlay';
            overlay.style.cssText = 'position:fixed;inset:0;z-index:20000;display:none;align-items:center;justify-content:center;background:rgba(15,10,30,0.5);backdrop-filter:blur(8px);padding:24px;';
            overlay.innerHTML = `
                <div class="force-card">
                    <div class="force-title">需要更新 小爆来咯</div>
                    <div id="force-update-message" class="force-msg"></div>
                    <div id="force-update-notes" class="force-notes"></div>
                    <button id="force-update-button" type="button">立即更新（自动安装并重启）</button>
                </div>
            `;
            document.body.appendChild(overlay);
        }
        this.elements.forceOverlay = overlay;
        this.elements.forceMessage = document.getElementById('force-update-message');
        this.elements.forceNotes = document.getElementById('force-update-notes');
        this.elements.forceButton = document.getElementById('force-update-button');
        this.elements.forceButton.onclick = () => this.beginAutoUpdateFlow(true);
    }

    normalizeError(message) {
        let text = String(message || '').trim();
        text = text.replace(/^检查更新失败[:：]\s*/i, '');
        text = text.replace(/^更新失败[:：]\s*/i, '');
        if (/all connection attempts failed/i.test(text)) {
            return '无法连接更新服务器，请检查网络或配置系统代理后重试';
        }
        return text || '未知错误';
    }

    fillVersionInfo(policy) {
        if (this.elements.currentVersion) {
            this.elements.currentVersion.textContent = `v${policy.current_version || '--'}`;
        }
        if (this.elements.latestVersion) {
            this.elements.latestVersion.textContent = `v${policy.latest_version || '--'}`;
        }
        if (this.elements.releaseNotes) {
            this.elements.releaseNotes.textContent = policy.release_notes || '暂无更新说明';
        }
    }

    renderFooter(buttonsHtml) {
        if (this.elements.footerRight) {
            this.elements.footerRight.innerHTML = buttonsHtml;
        }
    }

    bindLogToggle() {
        if (!this.elements.logToggle || this.elements.logToggle.dataset.bound) return;
        this.elements.logToggle.dataset.bound = '1';
        this.elements.logToggle.addEventListener('click', () => {
            this.elements.logTerminal?.classList.toggle('is-visible');
            this.elements.logToggle.textContent = this.elements.logTerminal?.classList.contains('is-visible')
                ? '▲ 收起日志'
                : '▼ 查看详细日志';
        });
    }

    appendLog(message) {
        if (!this.elements.logTerminal) return;
        const line = document.createElement('div');
        line.className = 'log-line';
        line.textContent = message;
        this.elements.logTerminal.appendChild(line);
        this.elements.logTerminal.scrollTop = this.elements.logTerminal.scrollHeight;
    }

    renderLogs(lines = []) {
        if (!this.elements.logTerminal) return;
        this.elements.logTerminal.innerHTML = '';
        lines.forEach((line) => this.appendLog(line));
    }

    getHeaders(extra = {}) {
        const headers = { ...extra };
        const token = window.APP_CLIENT_TOKEN || this.getCookie('app_client_token');
        if (token) {
            headers['X-App-Client-Token'] = token;
        }
        return headers;
    }

    getCookie(name) {
        const key = `${name}=`;
        for (const part of decodeURIComponent(document.cookie).split(';')) {
            const trimmed = part.trim();
            if (trimmed.startsWith(key)) {
                return trimmed.substring(key.length);
            }
        }
        return '';
    }

    async fetchPolicy(retries = 3) {
        const response = await fetch('/api/system/update-policy', {
            headers: this.getHeaders(),
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 403 && retries > 0) {
            await new Promise((r) => setTimeout(r, 600));
            return this.fetchPolicy(retries - 1);
        }
        if (!response.ok) {
            throw new Error(this.normalizeError(data.detail || '检查更新失败'));
        }
        this.policy = data;
        return data;
    }

    resetUiForFlow() {
        this.autoRestartTriggered = false;
        this.renderStepList();
        this.showProgressBlock(false);
        this.showVersionRow(true);
        this.showReleaseNotes(true);
        this.resetProgress();
        this.bindLogToggle();
        if (this.elements.logTerminal) {
            this.elements.logTerminal.classList.remove('is-visible');
        }
        if (this.elements.logToggle) {
            this.elements.logToggle.textContent = '▼ 查看详细日志';
        }
    }

    async checkStartupPolicy() {
        try {
            const policy = await this.fetchPolicy();
            if (!policy.enabled || !policy.startup_check) {
                return;
            }
            if (policy.should_auto_update) {
                this.policy = policy;
                await this.beginAutoUpdateFlow(true);
                return;
            }
            if (policy.has_update && policy.can_update && policy.auto_update_silent) {
                this.policy = policy;
                await this.beginAutoUpdateFlow(true);
                return;
            }
            if (policy.force_update) {
                if (policy.auto_update_silent && policy.can_update) {
                    this.policy = policy;
                    await this.beginAutoUpdateFlow(true);
                } else {
                    this.showForceOverlay(policy);
                }
            }
        } catch (error) {
            console.error('Startup update check failed:', error);
            if (window.footerMarquee?.addMessage) {
                window.footerMarquee.addMessage(`检查更新失败：${this.normalizeError(error.message)}`, 'warning', false, 1);
            }
        }
    }

    async triggerAutoRestart() {
        if (this.autoRestartTriggered) {
            return;
        }
        this.autoRestartTriggered = true;
        this.setStep('install', 'done', '安装包已就绪');
        this.setStep('restart', 'active', '正在退出并静默安装…');
        this.setFooterHint(
            '窗口会关闭 1～3 分钟属正常（安装包约 128MB 需解压）。若弹出 UAC 请点「是」；完成后会自动打开新版本。'
        );
        this.renderFooter('');
        await this.restartAndInstall(true);
    }

    async beginAutoUpdateFlow(forceMode = false) {
        this.forceMode = forceMode;
        this.silentAutoMode = forceMode;
        this.openModal(forceMode);
        this.resetUiForFlow();
        this.fillVersionInfo(this.policy);
        this.setStep('check', 'done', '已发现新版本');
        this.setFooterHint('正在自动更新，请勿关闭程序');
        this.renderFooter('');
        await this.startUpdate(true);
    }

    showForceOverlay(policy) {
        this.policy = policy;
        this.forceMode = true;
        this.elements.forceOverlay.style.display = 'flex';
        this.elements.forceMessage.textContent =
            `当前 v${policy.current_version} 需升级至 v${policy.latest_version} 后才能继续使用。`;
        this.elements.forceNotes.textContent = policy.release_notes || '';
        this.elements.forceButton.disabled = !policy.can_update;
    }

    hideForceOverlay() {
        if (this.elements.forceOverlay) {
            this.elements.forceOverlay.style.display = 'none';
        }
    }

    openModal(forceMode = false) {
        this.forceMode = forceMode;
        if (this.elements.modal) {
            this.elements.modal.style.display = 'flex';
        }
        if (this.elements.closeButton) {
            this.elements.closeButton.style.display = forceMode ? 'none' : '';
        }
    }

    closeModal() {
        if (this.forceMode) {
            return;
        }
        if (this.elements.modal) {
            this.elements.modal.style.display = 'none';
        }
    }

    resetProgress() {
        if (this.elements.progressBar) {
            this.elements.progressBar.style.width = '0%';
        }
        if (this.elements.progressText) {
            this.elements.progressText.textContent = '0%';
        }
        if (this.elements.progressLabel) {
            this.elements.progressLabel.textContent = '下载进度';
        }
    }

    async openManualCheck(forceMode = false) {
        this.openModal(forceMode);
        this.resetUiForFlow();
        this.setStep('check', 'active', '正在检查更新…');
        this.setFooterHint('');
        this.fillVersionInfo({ current_version: '--', latest_version: '--', release_notes: '' });
        this.showReleaseNotes(false);
        this.renderFooter('<button type="button" class="update-btn update-btn-ghost" disabled>检查中…</button>');

        try {
            const policy = await this.fetchPolicy();
            this.policy = policy;
            this.fillVersionInfo(policy);
            this.showReleaseNotes(true);
            this.setStep('check', 'done', `当前 v${policy.current_version}，最新 v${policy.latest_version}`);

            if (policy.force_update) {
                this.showForceOverlay(policy);
            }

            if (policy.has_update && policy.can_update) {
                this.setFooterHint('点击更新后将自动下载、安装并重启');
                const cancelBtn = forceMode
                    ? ''
                    : '<button type="button" class="update-btn update-btn-ghost" onclick="window.updateChecker.closeModal()">稍后再说</button>';
                this.renderFooter(`
                    ${cancelBtn}
                    <button type="button" class="update-btn update-btn-primary" onclick="window.updateChecker.beginAutoUpdateFlow(false)">立即更新</button>
                `);
            } else if (policy.has_update) {
                this.setStep('download', 'error', '无法获取安装包地址');
                this.setFooterHint('');
                this.renderFooter('<button type="button" class="update-btn update-btn-ghost" onclick="window.updateChecker.closeModal()">关闭</button>');
            } else {
                this.setFooterHint('已是最新版本');
                this.renderFooter('<button type="button" class="update-btn update-btn-ghost" onclick="window.updateChecker.closeModal()">关闭</button>');
            }
        } catch (error) {
            this.renderError(error.message);
        }
    }

    renderError(message) {
        const detail = this.normalizeError(message);
        this.setStep(this.currentStepId, 'error', detail);
        this.showProgressBlock(false);
        this.setFooterHint('');
        this.appendLog(detail);
        this.elements.logTerminal?.classList.add('is-visible');

        const manualUrl = this.policy?.download_url || '';
        const manualBtn = manualUrl
            ? `<a class="update-btn update-btn-link" href="${manualUrl}" target="_blank" rel="noopener">浏览器下载</a>`
            : '';
        const retryBtn = '<button type="button" class="update-btn update-btn-primary" onclick="window.updateChecker.openManualCheck(false)">重试</button>';
        const closeBtn = this.forceMode
            ? ''
            : '<button type="button" class="update-btn update-btn-ghost" onclick="window.updateChecker.closeModal()">关闭</button>';

        this.renderFooter(`${closeBtn}${manualBtn}${retryBtn}`);
    }

    async startUpdate(silentAuto = false) {
        if (silentAuto) {
            this.silentAutoMode = true;
        }
        this.forceMode = true;
        this.hideForceOverlay();
        this.openModal(true);
        this.showProgressBlock(true);
        this.setStep('download', 'active', '正在连接下载服务器…');
        this.setFooterHint('下载完成后将自动安装并重启；若弹出 UAC 请点「是」');
        this.renderFooter('');

        if (this.progressTimer) {
            clearInterval(this.progressTimer);
        }
        this.progressTimer = setInterval(() => this.pollProgress(), 300);

        try {
            const response = await fetch('/api/system/update', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ download_url: this.policy?.download_url || '' }),
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(body.detail || '更新准备失败');
            }
            if (body.status === 'ready_to_install') {
                await this.pollProgress();
            }
        } catch (error) {
            clearInterval(this.progressTimer);
            this.progressTimer = null;
            this.renderError(error.message);
        }
    }

    applyProgressUi(progress, status) {
        const raw = Number(progress) || 0;
        const display = status === 'downloading' ? Math.max(raw, raw > 0 ? raw : 4) : raw;
        if (this.elements.progressBar) {
            this.elements.progressBar.style.width = `${display}%`;
            this.elements.progressBar.classList.toggle('is-indeterminate', status === 'downloading' && raw <= 1);
        }
        if (this.elements.progressText) {
            this.elements.progressText.textContent = status === 'downloading' && raw <= 1
                ? '下载中…'
                : `${raw}%`;
        }
    }

    async pollProgress() {
        try {
            const response = await fetch('/api/system/update-progress', {
                headers: this.getHeaders(),
            });
            const data = await response.json();

            if (Array.isArray(data.logs) && data.logs.length) {
                this.renderLogs(data.logs);
            }

            const progress = data.progress || 0;
            this.applyProgressUi(progress, data.status);

            if (data.status === 'downloading') {
                this.setStep('download', 'active', data.message || `正在下载… ${progress}%`);
                if (this.elements.progressLabel) {
                    this.elements.progressLabel.textContent = '下载安装包';
                }
            } else if (data.status === 'ready_to_install') {
                if (this.progressTimer) {
                    clearInterval(this.progressTimer);
                    this.progressTimer = null;
                }
                this.applyProgressUi(100, 'ready_to_install');
                this.setStep('download', 'done', '下载完成');
                this.setStep('install', 'active', '准备安装…');
                this.showProgressBlock(false);
                await this.triggerAutoRestart();
            } else if (data.status === 'error') {
                if (this.progressTimer) {
                    clearInterval(this.progressTimer);
                    this.progressTimer = null;
                }
                this.renderError(data.error || data.message || '更新失败');
            }
        } catch (error) {
            console.error('Poll update progress failed:', error);
        }
    }

    async restartAndInstall(exitingAfterRequest = false) {
        this.setStep('restart', 'active', '正在启动安装助手…');

        try {
            const response = await fetch('/api/system/restart-and-update', {
                method: 'POST',
                headers: this.getHeaders(),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.detail || '启动安装失败');
            }
            this.setStep('restart', 'done', '已发送安装指令');
            const logHint = data.log_file ? `（日志：${data.log_file}）` : '';
            this.setFooterHint(
                `程序即将关闭并完成安装（约 1～3 分钟，请勿重复打开）。完成后会自动启动。${logHint}`
            );
        } catch (error) {
            if (exitingAfterRequest) {
                this.setFooterHint('程序即将关闭并完成安装…');
                return;
            }
            this.renderError(error.message);
        }
    }

    copyLogs() {
        const text = this.elements.logTerminal?.innerText || '';
        if (text) {
            navigator.clipboard.writeText(text);
        }
    }

    startUpdateWithUrl(downloadUrl) {
        if (downloadUrl) {
            this.policy = { ...(this.policy || {}), download_url: downloadUrl };
        }
        return this.beginAutoUpdateFlow(false);
    }
}

window.UpdateChecker = UpdateChecker;
window.updateChecker = window.updateChecker || new UpdateChecker();
