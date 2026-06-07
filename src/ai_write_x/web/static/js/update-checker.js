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
        this.installAfterDownload = false;
        this.backgroundProgressTimer = null;
        this.currentStepId = 'check';
        this.elements = {};
        this._displayProgress = 0;   // 当前显示的平滑进度
        this._targetProgress = 0;    // 后端报告的实际进度
        this._smoothTimer = null;    // 平滑动画定时器

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
        // 防止重复调用
        if (this._startupCheckStarted) return;
        this._startupCheckStarted = true;

        const run = () => {
            if (this._startupCheckDone) return;
            this._startupCheckDone = true;
            this.checkStartupPolicy();
        };
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
            if (!policy.enabled || !policy.startup_check || !policy.has_update) {
                return;
            }

            this.policy = policy;
            if (this._isCreativeBusy()) {
                if (window.footerMarquee?.addMessage) {
                    window.footerMarquee.addMessage(
                        `????? v${policy.latest_version}???????????`,
                        'info', false, 0
                    );
                }
                return;
            }

            if (policy.force_update || policy.should_auto_update || policy.install_mode === 'immediate') {
                if (policy.can_update && (policy.auto_install || policy.force_update || policy.should_auto_update)) {
                    await this.beginAutoUpdateFlow(true);
                } else {
                    this.showForceOverlay(policy);
                }
                return;
            }

            if (policy.can_update && policy.auto_download !== false) {
                await this.prepareUpdateInBackground(policy);
            } else if (policy.can_update && window.footerMarquee?.addMessage) {
                window.footerMarquee.addMessage(
                    `????? v${policy.latest_version}????????????`,
                    'info', false, 0
                );
            }
        } catch (error) {
            console.error('Startup update check failed:', error);
            if (window.footerMarquee?.addMessage) {
                window.footerMarquee.addMessage(`???????${this.normalizeError(error.message)}`, 'warning', false, 1);
            }
        }
    }

    async prepareUpdateInBackground(policy) {
        if (!policy?.download_url || this.backgroundProgressTimer) return;
        this.policy = policy;
        try {
            const response = await fetch('/api/system/update', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    download_url: policy.download_url || '',
                    sha256: policy.sha256 || '',
                }),
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(body.detail || '??????');
            }
            if (window.footerMarquee?.addMessage) {
                window.footerMarquee.addMessage(
                    `????????? v${policy.latest_version}`,
                    'info', false, 1
                );
            }
            this.backgroundProgressTimer = setInterval(() => this.pollBackgroundPreparation(), 2000);
            await this.pollBackgroundPreparation();
        } catch (error) {
            console.warn('Background update prepare failed:', error);
            if (window.footerMarquee?.addMessage) {
                window.footerMarquee.addMessage(`?????????${this.normalizeError(error.message)}`, 'warning', false, 1);
            }
        }
    }

    async pollBackgroundPreparation() {
        try {
            const response = await fetch('/api/system/update-progress', { headers: this.getHeaders() });
            const data = await response.json().catch(() => ({}));
            if (data.status === 'ready_to_install') {
                if (this.backgroundProgressTimer) {
                    clearInterval(this.backgroundProgressTimer);
                    this.backgroundProgressTimer = null;
                }
                if (window.footerMarquee?.addMessage) {
                    window.footerMarquee.addMessage(
                        `??? v${this.policy?.latest_version || ''} ?????????????????`,
                        'success', false, 0
                    );
                }
            } else if (data.status === 'error') {
                if (this.backgroundProgressTimer) {
                    clearInterval(this.backgroundProgressTimer);
                    this.backgroundProgressTimer = null;
                }
                if (window.footerMarquee?.addMessage) {
                    window.footerMarquee.addMessage(`???????${this.normalizeError(data.error || data.message)}`, 'warning', false, 1);
                }
            }
        } catch (error) {
            console.warn('Background update progress failed:', error);
        }
    }

    async triggerAutoRestart() {
        if (this.autoRestartTriggered) {
            return;
        }

        // 创作中不自动安装，等待创作结束后自动安装
        if (this._isCreativeBusy()) {
            this.setStep('download', 'done', '下载完成（创作中，暂不安装）');
            this.setStep('install', 'pending', '等待创作结束…');
            this.showProgressBlock(false);
            this.setFooterHint('更新已下载完成，当前正在创作中，创作结束后将自动安装');
            this.appendLog('⏳ 检测到正在创作内容，等待创作结束后自动安装更新');
            this.renderFooter('<button type="button" class="update-btn update-btn-primary" onclick="window.updateChecker.installNow()">立即安装并重启</button>');

            // 启动轮询等待创作结束
            if (!this._creativeWaitTimer) {
                this._creativeWaitTimer = setInterval(() => {
                    if (!this._isCreativeBusy()) {
                        clearInterval(this._creativeWaitTimer);
                        this._creativeWaitTimer = null;
                        this.appendLog('✅ 创作已结束，开始自动安装更新');
                        this.triggerAutoRestart();
                    }
                }, 3000);
            }
            return;
        }

        // 清理等待定时器
        if (this._creativeWaitTimer) {
            clearInterval(this._creativeWaitTimer);
            this._creativeWaitTimer = null;
        }

        this.autoRestartTriggered = true;
        this.setStep('install', 'active', '正在准备安装…');
        this.setFooterHint('安装助手将自动关闭旧版本并安装新版本');
        this.showProgressBlock(true);
        this.resetProgress();
        if (this.elements.progressLabel) {
            this.elements.progressLabel.textContent = '安装进度';
        }
        this.renderFooter('');

        // 启动 helper 脚本（它会主动关闭旧进程、安装、启动新版本）
        await this.restartAndInstall();
    }

    _isCreativeBusy() {
        const workshop = window.creativeWorkshopManager;
        return !!(workshop && workshop.isGenerating);
    }

    installNow() {
        this.autoRestartTriggered = false;
        this.triggerAutoRestart();
    }

    async startInstaller() {
        try {
            const response = await fetch('/api/system/start-install', {
                method: 'POST',
                headers: this.getHeaders(),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.detail || '启动安装程序失败');
            }
            this.appendLog(`✅ 安装助手已启动: ${data.message || ''}`);
            this.setStep('install', 'active', '安装助手正在运行…');
            this.setFooterHint('安装助手将自动关闭旧版本、安装新版本并启动，请稍候');
            await this.pollInstallStatus();
        } catch (error) {
            this.renderError(error.message);
        }
    }

    async pollInstallStatus() {
        const maxWaitMs = 180000;
        const startTime = Date.now();
        let lastStatus = '';
        let lastProgress = -1;
        let noResponseCount = 0;

        while (Date.now() - startTime < maxWaitMs) {
            try {
                const response = await fetch('/api/system/install-status', {
                    headers: this.getHeaders(),
                });
                if (!response.ok) {
                    noResponseCount++;
                    if (noResponseCount > 5) {
                        this.setStep('install', 'active', '⏳ 安装中（连接可能因窗口切换中断）...');
                        this.setFooterHint('安装正在进行中，请耐心等待。新版本安装完成后会自动打开。');
                        noResponseCount = 0;
                    }
                    await new Promise(r => setTimeout(r, 2000));
                    continue;
                }
                noResponseCount = 0;

                const data = await response.json().catch(() => ({}));
                const status = data.status || 'unknown';
                const progress = Math.min(100, Math.max(0, parseInt(data.progress, 10) || 0));

                if (status !== lastStatus || progress !== lastProgress) {
                    lastStatus = status;
                    lastProgress = progress;
                    this.applyProgressUi(progress, status);
                    if (this.elements.progressLabel) {
                        this.elements.progressLabel.textContent = '安装进度';
                    }
                    this.showProgressBlock(true);
                    this.appendLog(`[安装] ${data.message || status} (${progress}%)`);
                }

                if (status === 'installed') {
                    this.applyProgressUi(100, 'installed');
                    this.setStep('install', 'done', '✅ 安装完成');
                    this.setStep('restart', 'active', '🚀 新版本正在启动…');
                    this.setFooterHint('安装完成！新版本正在启动，旧窗口即将自动关闭…');
                    // helper 脚本已启动新版本，旧窗口延迟关闭
                    setTimeout(() => this._closeApp(), 3000);
                    return;
                }

                if (status === 'done') {
                    this.applyProgressUi(100, 'done');
                    this.setStep('install', 'done', '✅ 安装完成');
                    this.setStep('restart', 'done', '🎉 更新完成！');
                    this.setFooterHint('更新完成！已成功升级到最新版本。旧窗口即将自动关闭…');
                    this.showProgressBlock(false);
                    // helper 脚本已启动新版本，旧窗口延迟关闭
                    setTimeout(() => this._closeApp(), 2000);
                    return;
                }

                if (status === 'error') {
                    this.setStep('install', 'error', data.message || '安装失败');
                    this.setFooterHint(`❌ ${data.message || '安装过程中出现错误'}`);
                    this.showProgressBlock(false);
                    return;
                }

                if (status === 'installing') {
                    const elapsed = Math.floor((Date.now() - startTime) / 1000);
                    this.setStep('install', 'active', `${data.message || '正在安装中...'} (${elapsed}秒)`);

                    if (elapsed < 8) {
                        this.setFooterHint('安装助手正在关闭旧版本并准备安装...');
                    } else if (progress >= 90) {
                        this.setFooterHint('即将完成！正在配置并启动新版本...');
                    } else {
                        this.setFooterHint('正在解压安装文件... (' + elapsed + '秒)');
                    }
                } else if (status === 'waiting') {
                    this.setStep('install', 'active', '正在关闭旧版本…');
                    this.setFooterHint('安装助手正在关闭旧版本，请稍候…');
                } else if (status === 'not_started' || status === 'unknown') {
                    const elapsed = Math.floor((Date.now() - startTime) / 1000);
                    if (elapsed > 10) {
                        this.setFooterHint('⏳ 安装程序可能正在后台运行，请稍候...');
                    }
                }
            } catch (e) {
                console.warn('Poll install status error:', e);
                noResponseCount++;
            }
            await new Promise(r => setTimeout(r, 1500));
        }

        this.setStep('install', 'active', '安装仍在进行中…');
        this.setFooterHint('安装时间较长，新版本完成后会自动启动。');
    }

    async beginAutoUpdateFlow(forceMode = false) {
        // 创作中不自动开始下载，只提示用户
        if (this._isCreativeBusy()) {
            this.policy = this.policy || {};
            this.openModal(false);
            this.resetUiForFlow();
            this.fillVersionInfo(this.policy);
            this.setStep('check', 'done', `当前 v${this.policy.current_version || '?' }，最新 v${this.policy.latest_version || '?'}`);
            this.setStep('download', 'pending', '创作中，暂不下载');
            this.setFooterHint('当前正在创作中，创作结束后可手动更新');
            this.renderFooter('<button type="button" class="update-btn update-btn-primary" onclick="window.updateChecker.beginAutoUpdateFlow(false)">立即更新</button>');
            return;
        }

        this.forceMode = forceMode;
        this.silentAutoMode = forceMode;
        this.installAfterDownload = true;
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
        this._stopSmoothAnimation();
        this._displayProgress = 0;
        this._targetProgress = 0;
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
        this._stopSmoothAnimation();
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
        this.downloadStartTime = Date.now();
        this.lastProgressTime = Date.now();

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);
            const response = await fetch('/api/system/update', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ download_url: this.policy?.download_url || '', sha256: this.policy?.sha256 || '' }),
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(body.detail || '更新准备失败');
            }
            this.appendLog(`服务器响应: ${body.status} - ${body.message || ''}`);
            await this.pollProgress();
        } catch (error) {
            if (error.name === 'AbortError') {
                this.renderError('请求超时（30秒），请检查网络连接后重试');
            } else {
                clearInterval(this.progressTimer);
                this.progressTimer = null;
                this.renderError(error.message);
            }
        }
    }

    applyProgressUi(progress, status) {
        const raw = Number(progress) || 0;
        // 设置目标进度（后端实际进度）
        this._targetProgress = raw;

        // 对于完成状态直接跳到目标
        if (status === 'ready_to_install' || status === 'done' || status === 'installed') {
            this._displayProgress = raw;
            this._targetProgress = raw;
            this._renderProgressBar(raw, status);
            return;
        }

        // 启动乐观进度动画（如果还没启动）
        if (!this._smoothTimer) {
            this._startOptimisticAnimation();
        }
    }

    /**
     * 乐观进度条动画：
     * - 显示进度先匀速前进（每80ms +0.5），看起来一直在动
     * - 如果显示进度追上了实际进度，就停下来等实际进度更新
     * - 实际进度更新后，显示进度继续追赶
     */
    _startOptimisticAnimation() {
        if (this._smoothTimer) return;
        this._smoothTimer = setInterval(() => {
            if (this._displayProgress < this._targetProgress) {
                // 追赶实际进度：每次逼近差距的20%，至少+1
                const diff = this._targetProgress - this._displayProgress;
                const step = Math.max(1, Math.ceil(diff * 0.2));
                this._displayProgress = Math.min(this._targetProgress, this._displayProgress + step);
                this._renderProgressBar(this._displayProgress, 'downloading');
            } else if (this._displayProgress < 95) {
                // 显示进度已追上实际进度，但还没到95%
                // 匀速缓慢前进，让用户感觉一直在下载
                this._displayProgress = Math.min(95, this._displayProgress + 0.5);
                this._renderProgressBar(this._displayProgress, 'downloading');
            }
            // 到95%以上就停住，等实际进度追上来
            if (this._displayProgress >= 100) {
                this._stopSmoothAnimation();
            }
        }, 80);
    }

    _stopSmoothAnimation() {
        if (this._smoothTimer) {
            clearInterval(this._smoothTimer);
            this._smoothTimer = null;
        }
    }

    _renderProgressBar(value, status) {
        const display = Math.min(100, Math.max(0, Math.round(value)));
        if (this.elements.progressBar) {
            this.elements.progressBar.style.width = `${display}%`;
            this.elements.progressBar.classList.toggle('is-indeterminate', status === 'downloading' && display <= 1);
        }
        if (this.elements.progressText) {
            this.elements.progressText.textContent = status === 'downloading' && display <= 1
                ? '下载中…'
                : `${display}%`;
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
                if (progress > (this._lastProgress || 0)) {
                    this.lastProgressTime = Date.now();
                }
                this._lastProgress = progress;
                const stuckMs = Date.now() - this.lastProgressTime;
                if (stuckMs > 60000 && progress === (this._lastProgress || 0)) {
                    clearInterval(this.progressTimer);
                    this.progressTimer = null;
                    this.renderError(`下载卡住超过60秒（当前${progress}%），请检查网络或手动下载后重试`);
                    return;
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

    _closeApp() {
        try {
            fetch('/shutdown', { method: 'POST' }).catch(() => {});
        } catch(e) {}
        try { window.close(); } catch(e) {}
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
