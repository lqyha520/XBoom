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
        this.elements = {};

        window.__aiwritexUpdateCheckerInstance = this;

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init(), { once: true });
        } else {
            this.init();
        }
    }

    init() {
        this.cacheElements();
        this.ensureForceOverlay();
        this.checkStartupPolicy();
    }

    cacheElements() {
        this.elements.modal = document.getElementById('update-modal-overlay');
        this.elements.logTerminal = document.getElementById('update-log-terminal');
        this.elements.progressBar = document.getElementById('update-progress-inner');
        this.elements.progressText = document.getElementById('update-progress-percent');
        this.elements.footerRight = document.querySelector('#update-modal-overlay .footer-right');
        this.elements.closeButton = document.querySelector('#update-modal-overlay .close-btn');
        this.elements.updateButtonText = document.getElementById('update-btn-text');
    }

    ensureForceOverlay() {
        let overlay = document.getElementById('force-update-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'force-update-overlay';
            overlay.style.cssText = [
                'position:fixed',
                'inset:0',
                'z-index:20000',
                'display:none',
                'align-items:center',
                'justify-content:center',
                'background:rgba(8,10,18,0.92)',
                'backdrop-filter:blur(8px)',
                'padding:24px',
            ].join(';');
            overlay.innerHTML = `
                <div style="width:min(520px, 100%); background:#111827; border:1px solid rgba(255,255,255,0.08); border-radius:12px; box-shadow:0 20px 80px rgba(0,0,0,0.35); padding:28px; color:#f3f4f6;">
                    <div style="font-size:20px; font-weight:700; margin-bottom:10px;">需要先更新 AIWriteX</div>
                    <div id="force-update-message" style="font-size:14px; line-height:1.7; color:#cbd5e1; margin-bottom:18px;"></div>
                    <div id="force-update-notes" style="max-height:180px; overflow:auto; padding:12px; border-radius:8px; background:rgba(255,255,255,0.04); color:#cbd5e1; white-space:pre-wrap; font-size:13px; line-height:1.6; margin-bottom:18px;"></div>
                    <div style="display:flex; gap:12px; justify-content:flex-end;">
                        <button id="force-update-button" style="border:none; border-radius:8px; padding:10px 18px; cursor:pointer; background:#22c55e; color:#08110a; font-size:14px; font-weight:700;">立即更新</button>
                    </div>
                </div>
            `;
            document.body.appendChild(overlay);
        }

        this.elements.forceOverlay = overlay;
        this.elements.forceMessage = document.getElementById('force-update-message');
        this.elements.forceNotes = document.getElementById('force-update-notes');
        this.elements.forceButton = document.getElementById('force-update-button');
        this.elements.forceButton.onclick = () => this.openManualCheck(true);
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
        const parts = decodeURIComponent(document.cookie).split(';');
        for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.startsWith(key)) {
                return trimmed.substring(key.length);
            }
        }
        return '';
    }

    async fetchPolicy() {
        const response = await fetch('/api/system/update-policy', {
            headers: this.getHeaders(),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || '检查更新失败');
        }
        this.policy = data;
        return data;
    }

    async checkStartupPolicy() {
        try {
            const policy = await this.fetchPolicy();
            if (!policy.enabled || !policy.startup_check) {
                return;
            }

            if (policy.should_auto_update) {
                await this.runSilentAutoUpdate(policy);
                return;
            }

            if (policy.force_update) {
                if (policy.auto_update_silent && policy.can_update) {
                    await this.runSilentAutoUpdate(policy);
                } else {
                    this.showForceOverlay(policy);
                }
            }
        } catch (error) {
            console.error('Startup update check failed:', error);
        }
    }

    shouldAutoRestart() {
        if (this.policy?.auto_update_silent === false) {
            return false;
        }
        return Boolean(
            this.silentAutoMode
            || this.forceMode
            || this.policy?.auto_update_silent
            || this.policy?.should_auto_update
            || this.policy?.is_release_build
        );
    }

    async triggerAutoRestart() {
        if (this.autoRestartTriggered) {
            return;
        }
        this.autoRestartTriggered = true;
        this.appendLog('下载完成，即将自动重启并安装...', '#52c41a');
        this.renderFooter('<button class="modal-btn secondary-btn" disabled>正在重启并安装...</button>');
        await this.restartAndInstall(true);
    }

    async runSilentAutoUpdate(policy) {
        this.policy = policy;
        this.silentAutoMode = true;
        this.forceMode = true;
        this.autoRestartTriggered = false;

        this.openModal(true);
        this.resetProgress();
        this.renderLogs([
            `检测到新版本 v${policy.latest_version}（当前 v${policy.current_version}）`,
            '正在自动下载并安装，请勿关闭程序...',
            '',
            policy.release_notes || '暂无更新说明',
        ]);
        this.renderFooter('<button class="modal-btn secondary-btn" disabled>自动更新中...</button>');

        await this.startUpdate(true);
    }

    showForceOverlay(policy) {
        this.forceMode = true;
        this.elements.forceOverlay.style.display = 'flex';
        this.elements.forceMessage.textContent =
            `当前版本 v${policy.current_version} 低于最低支持版本 v${policy.min_supported_version || policy.latest_version}，更新完成前不能继续使用。`;
        this.elements.forceNotes.textContent = policy.release_notes || '请先更新到最新版本。';
        this.elements.forceButton.disabled = !policy.can_update;
        this.elements.forceButton.textContent = policy.can_update ? '立即更新' : '当前无法自动更新';
    }

    hideForceOverlay() {
        this.forceMode = false;
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
    }

    renderFooter(buttonsHtml) {
        if (this.elements.footerRight) {
            this.elements.footerRight.innerHTML = buttonsHtml;
        }
    }

    appendLog(message, color = '') {
        if (!this.elements.logTerminal) return;
        const line = document.createElement('div');
        line.className = 'log-line';
        if (color) {
            line.style.color = color;
        }
        line.textContent = message;
        this.elements.logTerminal.appendChild(line);
        this.elements.logTerminal.scrollTop = this.elements.logTerminal.scrollHeight;
    }

    renderLogs(lines = []) {
        if (!this.elements.logTerminal) return;
        this.elements.logTerminal.innerHTML = '';
        lines.forEach(line => this.appendLog(line));
    }

    async openManualCheck(forceMode = false) {
        this.openModal(forceMode);
        this.resetProgress();
        this.renderLogs(['正在检查版本策略...', '正在获取服务器上的最新发布信息...']);
        this.renderFooter('<button class="modal-btn secondary-btn" disabled>检查中...</button>');

        try {
            const policy = await this.fetchPolicy();
            if (policy.force_update) {
                this.showForceOverlay(policy);
            }

            if (policy.has_update) {
                this.renderUpdateAvailable(policy, forceMode || policy.force_update);
            } else {
                this.renderUpToDate(policy);
            }
        } catch (error) {
            this.renderError(error.message || '检查更新失败');
        }
    }

    renderUpdateAvailable(policy, forceMode) {
        const minVersionText = policy.min_supported_version
            ? `最低支持版本: v${policy.min_supported_version}`
            : '未设置最低支持版本';

        this.renderLogs([
            `当前版本: v${policy.current_version}`,
            `最新版本: v${policy.latest_version}`,
            minVersionText,
            '',
            policy.release_notes || '暂无更新说明',
        ]);

        if (!policy.can_update) {
            this.renderFooter('<button class="modal-btn secondary-btn" onclick="window.updateChecker.closeModal()">关闭</button>');
            if (forceMode) {
                this.renderFooter('<button class="modal-btn secondary-btn" disabled>当前无法自动更新</button>');
            }
            return;
        }

        const cancelButton = forceMode
            ? ''
            : '<button class="modal-btn secondary-btn" onclick="window.updateChecker.closeModal()">稍后再说</button>';
        this.renderFooter(`
            ${cancelButton}
            <button class="modal-btn primary-btn" onclick="window.updateChecker.startUpdate()">立即更新</button>
        `);
    }

    renderUpToDate(policy) {
        this.renderLogs([
            `当前版本: v${policy.current_version}`,
            '已是最新版本。',
        ]);
        this.renderFooter('<button class="modal-btn secondary-btn" onclick="window.updateChecker.closeModal()">关闭</button>');
        if (window.app?.showNotification) {
            window.app.showNotification(`当前已是最新版本 v${policy.current_version}`, 'success');
        }
    }

    renderError(message) {
        this.renderLogs([`检查更新失败: ${message}`]);
        if (this.forceMode) {
            this.renderFooter('<button class="modal-btn secondary-btn" disabled>请联系管理员处理更新源</button>');
            return;
        }
        this.renderFooter('<button class="modal-btn secondary-btn" onclick="window.updateChecker.closeModal()">关闭</button>');
    }

    async startUpdate(silentAuto = false) {
        if (silentAuto) {
            this.silentAutoMode = true;
            this.forceMode = true;
        }
        this.openModal(this.forceMode);
        if (!silentAuto) {
            this.renderLogs(['正在准备更新...', '开始下载安装包，请稍候。']);
        }
        this.resetProgress();
        if (!this.silentAutoMode) {
            this.renderFooter('<button class="modal-btn secondary-btn" disabled>下载中...</button>');
        }

        if (this.progressTimer) {
            clearInterval(this.progressTimer);
        }
        this.progressTimer = setInterval(() => this.pollProgress(), 800);

        try {
            const response = await fetch('/api/system/update', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    download_url: this.policy?.download_url || '',
                }),
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || '更新准备失败');
            }
        } catch (error) {
            clearInterval(this.progressTimer);
            this.renderError(error.message || '更新失败');
        }
    }

    async pollProgress() {
        try {
            const response = await fetch('/api/system/update-progress', {
                headers: this.getHeaders(),
            });
            const data = await response.json();
            this.renderLogs(data.logs || []);

            if (this.elements.progressBar) {
                this.elements.progressBar.style.width = `${data.progress || 0}%`;
            }
            if (this.elements.progressText) {
                this.elements.progressText.textContent = `${data.progress || 0}%`;
            }

            if (data.status === 'ready_to_install') {
                clearInterval(this.progressTimer);
                if (this.shouldAutoRestart()) {
                    await this.triggerAutoRestart();
                    return;
                }
                this.renderFooter(`
                    ${this.forceMode ? '' : '<button class="modal-btn secondary-btn" onclick="window.updateChecker.closeModal()">后台等待</button>'}
                    <button class="modal-btn primary-btn" id="restart-btn" onclick="window.updateChecker.restartAndInstall()">立即重启并安装</button>
                `);
            } else if (data.status === 'error') {
                clearInterval(this.progressTimer);
                this.renderError(data.error || '更新失败');
            }
        } catch (error) {
            console.error('Poll update progress failed:', error);
        }
    }

    async restartAndInstall(exitingAfterRequest = false) {
        const button = document.getElementById('restart-btn');
        if (button) {
            button.disabled = true;
            button.textContent = '正在重启并安装...';
        }

        try {
            const response = await fetch('/api/system/restart-and-update', {
                method: 'POST',
                headers: this.getHeaders(),
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || '启动安装失败');
            }
            if (exitingAfterRequest) {
                this.appendLog('已发送重启指令，程序即将退出并完成安装...', '#52c41a');
            }
        } catch (error) {
            if (exitingAfterRequest) {
                this.appendLog('已发送重启指令，程序即将退出并完成安装...', '#52c41a');
                return;
            }
            if (button) {
                button.disabled = false;
                button.textContent = '立即重启并安装';
            }
            this.appendLog(`启动安装失败: ${error.message}`, '#ff4d4f');
        }
    }

    copyLogs() {
        if (!this.elements.logTerminal) return;
        const logs = this.elements.logTerminal.innerText || '';
        navigator.clipboard.writeText(logs);
    }
}

window.UpdateChecker = UpdateChecker;
window.updateChecker = window.updateChecker || new UpdateChecker();
