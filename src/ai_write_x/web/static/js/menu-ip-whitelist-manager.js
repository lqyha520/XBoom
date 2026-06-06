/**
 * MenuIpWhitelistManager - 受限菜单 IP 白名单 CRUD
 */
class MenuIpWhitelistManager {
    constructor() {
        this.items = [];
        this.status = null;
        this._initialized = false;
        this._loading = false;
        this._editingId = null;
    }

    init() {
        if (this._initialized) return;
        this._initialized = true;
        this._checkAvailable();
    }

    async _checkAvailable() {
        try {
            const res = await fetch('/api/menu-ip-whitelist/status');
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                if (res.status === 503 || String(data.detail || '').includes('mysql') || String(data.detail || '').includes('未配置')) {
                    this._showUnavailable();
                    return;
                }
                throw new Error(data.detail || `状态加载失败 (${res.status})`);
            }
            this.status = await res.json();
            await this.fetchList();
            this.renderStatus();
            this.renderTable();
        } catch (e) {
            this._showError(e.message || String(e));
        }
    }

    _showUnavailable() {
        const container = document.getElementById('menu-ip-whitelist-view');
        if (!container) return;
        const existing = container.querySelector('.ip-unavailable-hint');
        if (existing) return;
        const hint = document.createElement('div');
        hint.className = 'ip-unavailable-hint';
        hint.style.cssText = 'padding:40px;text-align:center;color:#999;';
        hint.innerHTML = '<p style="font-size:14px;">🔒 IP 白名单功能未启用</p><p style="font-size:12px;margin-top:8px;">如需使用，请在配置文件中设置 <code>menu_access.mysql</code></p>';
        const tableWrap = container.querySelector('.ip-whitelist-table-wrap');
        if (tableWrap) { tableWrap.style.display = 'none'; }
        const statusArea = container.querySelector('.ip-status-area');
        if (statusArea) { statusArea.style.display = 'none'; }
        container.insertBefore(hint, container.firstChild);
    }

    async refresh(showToast = false) {
        if (this._loading) return;
        this._loading = true;
        const btn = document.getElementById('menu-ip-refresh-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = '刷新中…';
        }
        try {
            await Promise.all([this.fetchStatus(), this.fetchList()]);
            this.renderStatus();
            this.renderTable();
            this._hideError();
            if (showToast && window.showNotification) {
                window.showNotification(`已刷新，共 ${this.items.length} 条`, 'success');
            }
        } catch (e) {
            this._showError(e.message || String(e));
        } finally {
            this._loading = false;
            if (btn) {
                btn.disabled = false;
                btn.textContent = '刷新';
            }
        }
    }

    async fetchStatus() {
        const res = await fetch('/api/menu-ip-whitelist/status');
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || `状态加载失败 (${res.status})`);
        }
        this.status = await res.json();
    }

    async fetchList() {
        const res = await fetch('/api/menu-ip-whitelist');
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || `列表加载失败 (${res.status})`);
        }
        const data = await res.json();
        this.items = data.items || [];
    }

    renderStatus() {
        const el = document.getElementById('menu-ip-status-badge');
        const hint = document.getElementById('menu-ip-list-hint');
        if (!this.status || !el) return;
        const ip = this.status.public_ip || '—';
        const allowed = this.status.allowed;
        el.textContent = `本机 ${ip} · ${allowed ? '在白名单内' : '不在白名单'}`;
        el.classList.toggle('is-allowed', !!allowed);
        el.classList.toggle('is-denied', !allowed);
        if (hint) {
            hint.textContent = `共 ${this.items.length} 条 · 生效 ${this.items.filter((i) => i.enabled).length} 条`;
        }
    }

    renderTable() {
        const tbody = document.getElementById('menu-ip-table-body');
        if (!tbody) return;
        if (!this.items.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-5 text-secondary">暂无记录，点击「添加 IP」</td></tr>';
            return;
        }
        tbody.innerHTML = this.items
            .map((row) => {
                const statusCls = row.enabled ? 'tag-enabled' : 'tag-disabled';
                const statusText = row.enabled ? '启用' : '停用';
                return `
                <tr data-id="${row.id}">
                    <td>${row.id}</td>
                    <td><code>${this.escapeHtml(row.ip)}</code></td>
                    <td>${this.escapeHtml(row.remark || '—')}</td>
                    <td><span class="${statusCls}">${statusText}</span></td>
                    <td>${this.escapeHtml(row.created_at || '—')}</td>
                    <td>${this.escapeHtml(row.updated_at || '—')}</td>
                    <td>
                        <button type="button" class="btn-link" data-action="edit" data-id="${row.id}">编辑</button>
                        <span class="divider">|</span>
                        <button type="button" class="btn-link" data-action="toggle" data-id="${row.id}">
                            ${row.enabled ? '停用' : '启用'}
                        </button>
                        <span class="divider">|</span>
                        <button type="button" class="btn-link btn-link-danger" data-action="delete" data-id="${row.id}">删除</button>
                    </td>
                </tr>`;
            })
            .join('');

        tbody.querySelectorAll('[data-action]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const id = Number(e.currentTarget.dataset.id);
                const action = e.currentTarget.dataset.action;
                const row = this.items.find((i) => i.id === id);
                if (!row) return;
                if (action === 'edit') this.openFormModal(row);
                else if (action === 'toggle') this.toggleEnabled(row);
                else if (action === 'delete') this.deleteRow(row);
            });
        });
    }

    openFormModal(row = null) {
        this._editingId = row ? row.id : null;
        const modal = document.getElementById('menu-ip-form-modal');
        const title = document.getElementById('menu-ip-form-title');
        const ipInput = document.getElementById('menu-ip-form-ip');
        const remarkInput = document.getElementById('menu-ip-form-remark');
        const enabledInput = document.getElementById('menu-ip-form-enabled');
        if (!modal || !ipInput) return;
        if (title) title.textContent = row ? '编辑 IP' : '添加 IP';
        ipInput.value = row ? row.ip : '';
        if (remarkInput) remarkInput.value = row ? row.remark || '' : '';
        if (enabledInput) enabledInput.checked = row ? !!row.enabled : true;
        ipInput.disabled = false;
        modal.style.display = 'flex';
        ipInput.focus();
    }

    closeFormModal() {
        const modal = document.getElementById('menu-ip-form-modal');
        if (modal) modal.style.display = 'none';
        this._editingId = null;
    }

    async submitForm() {
        const ip = (document.getElementById('menu-ip-form-ip')?.value || '').trim();
        const remark = (document.getElementById('menu-ip-form-remark')?.value || '').trim();
        const enabled = !!document.getElementById('menu-ip-form-enabled')?.checked;
        if (!ip) {
            window.showNotification?.('请填写 IP 地址', 'warning');
            return;
        }
        const submitBtn = document.getElementById('menu-ip-form-submit');
        if (submitBtn) submitBtn.disabled = true;
        try {
            let res;
            if (this._editingId) {
                res = await fetch(`/api/menu-ip-whitelist/${this._editingId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ip, remark, enabled }),
                });
            } else {
                res = await fetch('/api/menu-ip-whitelist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ip, remark, enabled }),
                });
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.detail || `保存失败 (${res.status})`);
            }
            this.closeFormModal();
            window.showNotification?.(this._editingId ? '已更新' : '已添加', 'success');
            await this.refresh(false);
        } catch (e) {
            window.showNotification?.(e.message || String(e), 'error');
        } finally {
            if (submitBtn) submitBtn.disabled = false;
        }
    }

    async toggleEnabled(row) {
        try {
            const res = await fetch(`/api/menu-ip-whitelist/${row.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !row.enabled }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `操作失败 (${res.status})`);
            window.showNotification?.(row.enabled ? '已停用' : '已启用', 'success');
            await this.refresh(false);
        } catch (e) {
            window.showNotification?.(e.message || String(e), 'error');
        }
    }

    async deleteRow(row) {
        const ok = window.confirm?.(`确定删除 IP ${row.ip}？`) ?? true;
        if (!ok) return;
        try {
            const res = await fetch(`/api/menu-ip-whitelist/${row.id}`, { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `删除失败 (${res.status})`);
            window.showNotification?.('已删除', 'success');
            await this.refresh(false);
        } catch (e) {
            window.showNotification?.(e.message || String(e), 'error');
        }
    }

    _showError(msg) {
        const el = document.getElementById('menu-ip-load-error');
        if (!el) return;
        el.style.display = 'block';
        el.textContent = msg;
    }

    _hideError() {
        const el = document.getElementById('menu-ip-load-error');
        if (el) el.style.display = 'none';
    }

    escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.menuIpWhitelistManager = new MenuIpWhitelistManager();
});
