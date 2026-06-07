/**
 * NewsHub 选题中心管理器
 */
class NewsHubManager {
    constructor() {
        this.allNews = [];
        this.news = [];
        this.trends = [];
        this.sources = [];
        this.autoRefreshInterval = null;
        this.refreshInterval = 300000;
        this.initialized = false;
        this.initializing = false;
        this._loading = false;
    }

    init() {
        if (this.initializing) return;
        if (this.initialized) {
            // 已初始化，仅刷新界面显示
            this.applyNewsFilter();
            return;
        }
        this.initializing = true;
        this.bindEvents();
        
        // 先标记已初始化，立即显示界面
        this.initialized = true;
        this.initializing = false;
        
        // 显示加载中状态
        this.showLoadingState();
        
        // 后台异步加载数据，不阻塞界面
        this.loadDataInBackground();
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
            ...options,
            headers: {
                ...(options.headers || {}),
                ...this._authHeaders(),
            },
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

    async refreshAll(showToast = false) {
        if (this._loading) return;
        this._loading = true;
        try {
            await this.loadSources();
            await Promise.all([this.loadCache(), this.loadTrends(), this.loadGitHubTrending()]);
            if (showToast) this.showSuccess('已刷新');
        } catch (e) {
            this.showError('加载失败: ' + (e.message || e));
        } finally {
            this._loading = false;
        }
    }

    bindEvents() {
        const refreshBtn = document.getElementById('nh-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.aggregateNow());
        }

        const categoryFilter = document.getElementById('nh-category-filter');
        if (categoryFilter) {
            categoryFilter.addEventListener('change', () => this.applyNewsFilter());
        }

        const sourcesBtn = document.getElementById('nh-sources-btn');
        if (sourcesBtn) {
            sourcesBtn.addEventListener('click', () => this.showSourcesConfig());
        }

        const autoRefresh = document.getElementById('nh-auto-refresh');
        if (autoRefresh) {
            autoRefresh.addEventListener('change', (e) => {
                if (e.target.checked) this.startAutoRefresh();
                else this.stopAutoRefresh();
            });
        }

        const filterProcessed = document.getElementById('nh-filter-processed');
        if (filterProcessed) {
            filterProcessed.addEventListener('change', () => this.aggregateNow());
        }

        const modal = document.getElementById('nh-sources-modal');
        this.closeModal = () => {
            if (modal) modal.style.display = 'none';
        };
        const closeBtn = document.getElementById('nh-sources-close');
        if (closeBtn) closeBtn.addEventListener('click', this.closeModal);
        window.addEventListener('click', (e) => {
            if (e.target === modal) this.closeModal();
        });
    }

    async loadSources() {
        try {
            const data = await this._fetchJson('/api/newshub/sources');
            this.sources = data.sources || [];
            this.updateStats({
                sources: data.enabled ?? this.sources.filter((s) => s.enabled).length,
                total_sources: data.total ?? this.sources.length,
            });
        } catch (error) {
            console.error('加载数据源失败:', error);
        }
    }

    async loadCache() {
        try {
            const data = await this._fetchJson('/api/newshub/cache?limit=200');
            if (data.status === 'success') {
                this.allNews = (data.data || []).map((item) => this._normalizeNewsItem(item));
                this.applyNewsFilter();
                if (data.trends?.length) {
                    this.trends = data.trends.map((t, i) => ({
                        keyword: t.keyword || t,
                        hot_score: Number(t.score ?? t.hot_score ?? 0),
                        growth_rate: Number(t.growth_rate ?? 0),
                        rank: i + 1,
                    }));
                    this.renderTrends();
                }
                this._updateTimeLabel(data.generated_at);
            }
        } catch (error) {
            console.error('加载缓存失败:', error);
            throw error;
        }
    }

    _normalizeNewsItem(item) {
        return {
            id: String(item.id || ''),
            title: item.title || '',
            summary: item.summary || '',
            category: item.category || '综合',
            keywords: item.keywords || [],
            score: Number(item.score ?? 0),
            sentiment: item.sentiment || 'neutral',
            source: item.source || '选题中心',
            url: item.url || '',
            published_at: item.published_at || '',
        };
    }

    applyNewsFilter() {
        const category = document.getElementById('nh-category-filter')?.value || '';
        this.news = category
            ? this.allNews.filter((n) => (n.category || '').toLowerCase().includes(category))
            : [...this.allNews];
        this.renderNews();
        this.updateStats({
            articles: this.news.length,
            trends: this.trends.length,
        });
        const countBadge = document.getElementById('nh-news-count-badge');
        if (countBadge) countBadge.textContent = `${this.news.length} 条`;
    }

    async loadTrends() {
        try {
            const data = await this._fetchJson('/api/newshub/trends?limit=10');
            if (data.status === 'success' && data.data?.length) {
                this.trends = data.data;
                this.renderTrends();
                this.updateStats({ trends: data.data.length });
            }
        } catch (error) {
            console.error('加载趋势失败:', error);
        }
    }

    async aggregateNow() {
        const btn = document.getElementById('nh-refresh-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> 聚合中...';
        }

        const category = document.getElementById('nh-category-filter')?.value || '';
        const filterProcessed = document.getElementById('nh-filter-processed')?.checked || false;

        try {
            const data = await this._fetchJson('/api/newshub/aggregate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    categories: category ? [category] : [],
                    min_score: 0,
                    limit: 200,
                    filter_processed: filterProcessed,
                }),
            });

            if (data.status === 'success') {
                this.allNews = (data.data || []).map((item) => this._normalizeNewsItem(item));
                this.applyNewsFilter();
                if (data.trends?.length) {
                    this.trends = data.trends;
                    this.renderTrends();
                } else {
                    await this.loadTrends();
                }
                await this.loadGitHubTrending();
                this._updateTimeLabel(data.generated_at);
                this.showSuccess(`聚合完成，共 ${this.allNews.length} 条热点`);
            }
        } catch (error) {
            console.error('聚合失败:', error);
            this.showError('聚合失败: ' + (error.message || '请稍后重试'));
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M23 4v6h-6M1 20v-6h6"/>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                    一键获取热点
                `;
            }
        }
    }

    _updateTimeLabel(isoOrDate) {
        const now = isoOrDate ? new Date(isoOrDate) : new Date();
        const fullTime = Number.isNaN(now.getTime())
            ? '尚未更新'
            : `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${now.toLocaleTimeString([], { hour12: false })}`;
        const timeEl = document.getElementById('nh-last-update-time');
        if (timeEl) timeEl.textContent = fullTime;
        this.updateStats({ last_update: now.toLocaleTimeString([], { hour12: false }) });
    }

    async loadGitHubTrending() {
        try {
            const data = await this._fetchJson('/api/newshub/github/trending?limit=10');
            if (data.status === 'success') {
                this.renderGitHubTrending(data.data);
            }
        } catch (error) {
            console.error('加载GitHub趋势失败:', error);
        }
    }

    renderTrends() {
        const container = document.getElementById('nh-trends-list');
        if (!container) return;

        if (!this.trends.length) {
            container.innerHTML = '<div class="empty-state">暂无趋势，点击「一键获取热点」同步</div>';
            return;
        }

        container.innerHTML = this.trends
            .map((trend, index) => {
                const hotScore = Number(trend.hot_score ?? 0);
                const growth = Number(trend.growth_rate ?? 0);
                const growthIcon = growth > 0 ? '📈' : growth < 0 ? '📉' : '➡️';
                const growthClass = growth > 0 ? 'positive' : growth < 0 ? 'negative' : '';
                const keyword = trend.keyword || trend;
                return `
                <div class="trend-item">
                    <span class="trend-rank">${trend.rank ?? index + 1}</span>
                    <span class="trend-keyword">${this.escapeHtml(String(keyword))}</span>
                    <span class="trend-score">${hotScore.toFixed(1)}°</span>
                    <span class="trend-growth ${growthClass}">${growthIcon} ${(Math.abs(growth) * 100).toFixed(0)}%</span>
                </div>`;
            })
            .join('');
    }

    renderNews() {
        const container = document.getElementById('nh-news-list');
        if (!container) return;

        if (!this.news.length) {
            container.innerHTML =
                '<div class="empty-state">暂无热点数据。点击右上角「一键获取热点」开始抓取</div>';
            return;
        }

        container.innerHTML = this.news
            .map((item) => {
                const sentimentClass =
                    item.sentiment === 'positive' ? 'positive' : item.sentiment === 'negative' ? 'negative' : 'neutral';
                const sentimentIcon = item.sentiment === 'positive' ? '😊' : item.sentiment === 'negative' ? '😔' : '😐';
                const id = this.escapeAttr(item.id);
                return `
                <div class="news-card" data-id="${id}">
                    <div class="news-header">
                        <span class="news-category">${this.escapeHtml(item.category)}</span>
                        <span class="news-score">评分: ${item.score.toFixed(1)}</span>
                    </div>
                    <h3 class="news-title">${this.escapeHtml(item.title)}</h3>
                    <p class="news-summary">${this.escapeHtml(item.summary)}</p>
                    <div class="news-footer">
                        <div class="news-keywords">
                            ${(item.keywords || [])
                                .slice(0, 6)
                                .map((kw) => `<span class="keyword-tag">${this.escapeHtml(kw)}</span>`)
                                .join('')}
                        </div>
                        <div class="news-meta">
                            <span class="news-source">${this.escapeHtml(item.source)}</span>
                            <span class="news-sentiment ${sentimentClass}">${sentimentIcon}</span>
                        </div>
                    </div>
                    <div class="news-actions">
                        <button class="action-btn" onclick="window.newshubManager.writeArticle('${id}')">
                            创作文章
                        </button>
                    </div>
                </div>`;
            })
            .join('');
    }

    renderGitHubTrending(data) {
        const container = document.getElementById('nh-github-list');
        if (!container || !data) return;

        const repos = this.parseGitHubData(data);
        if (!repos.length) {
            container.innerHTML = '<div class="empty-state">暂无 GitHub 趋势</div>';
            return;
        }

        container.innerHTML = repos
            .map(
                (repo, index) => `
            <div class="github-item">
                <span class="github-rank">${index + 1}</span>
                <div class="github-info">
                    <a href="${this.escapeAttr(repo.url)}" target="_blank" class="github-name">${this.escapeHtml(repo.name)}</a>
                    <p class="github-desc">${this.escapeHtml(repo.description)}</p>
                    <div class="github-meta">
                        <span class="github-stars">⭐ ${repo.stars.toLocaleString()}</span>
                        <span class="github-lang">${this.escapeHtml(repo.language)}</span>
                    </div>
                </div>
            </div>`
            )
            .join('');
    }

    parseGitHubData(text) {
        const repos = [];
        const lines = String(text).split('\n');
        let currentRepo = null;
        lines.forEach((line) => {
            if (/^\d+\./.test(line)) {
                if (currentRepo) repos.push(currentRepo);
                currentRepo = { name: line.replace(/^\d+\./, '').trim(), description: '', stars: 0, language: '', url: '' };
            } else if (currentRepo && line.includes('⭐')) {
                const match = line.match(/⭐ ([\d,]+)/);
                if (match) currentRepo.stars = parseInt(match[1].replace(/,/g, ''), 10);
                const langMatch = line.match(/\| ([\w#+]+) \|/);
                if (langMatch) currentRepo.language = langMatch[1];
            } else if (currentRepo && line.includes('🔗')) {
                currentRepo.url = line.replace('🔗', '').trim();
            } else if (currentRepo && line.trim() && !line.includes('===')) {
                currentRepo.description = line.trim();
            }
        });
        if (currentRepo) repos.push(currentRepo);
        return repos.slice(0, 10);
    }

    updateStats(stats) {
        if (stats.sources !== undefined) {
            const el = document.getElementById('nh-sources-count');
            if (el) el.textContent = stats.sources;
        }
        if (stats.articles !== undefined) {
            const el = document.getElementById('nh-articles-count');
            if (el) el.textContent = stats.articles;
        }
        if (stats.trends !== undefined) {
            const el = document.getElementById('nh-trends-count');
            if (el) el.textContent = stats.trends;
        }
        if (stats.last_update !== undefined) {
            const el = document.getElementById('nh-last-update');
            if (el) el.textContent = stats.last_update;
        }
    }

    startAutoRefresh() {
        const autoRefresh = document.getElementById('nh-auto-refresh');
        if (autoRefresh && !autoRefresh.checked) return;
        if (this.autoRefreshInterval) clearInterval(this.autoRefreshInterval);
        this.autoRefreshInterval = setInterval(() => this.aggregateNow(), this.refreshInterval);
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    backgroundInit() {
        // 后台静默采集，不显示界面，不阻塞其他操作
        if (this.initialized) return;
        
        this.initialized = true;
        this.initializing = false;
        
        console.log('[资讯采集] 后台静默采集开始');
        
        // 异步加载数据，不等待结果
        this.loadDataInBackground().then(() => {
            console.log('[资讯采集] 后台采集完成');
        }).catch(e => {
            console.error('[资讯采集] 后台采集失败:', e);
        });
    }

    showLoadingState() {
        const newsList = document.getElementById('nh-news-list');
        if (newsList) {
            newsList.innerHTML = '<div class="loading-state" style="text-align:center;padding:40px;color:var(--text-secondary);"><div class="spinner"></div><p>正在加载资讯...</p></div>';
        }
    }

    async loadDataInBackground() {
        try {
            await this.loadSources();
            await Promise.all([this.loadCache(), this.loadTrends(), this.loadGitHubTrending()]);
            this.startAutoRefresh();
        } catch (e) {
            console.error('[资讯采集] 后台加载失败:', e);
            const newsList = document.getElementById('nh-news-list');
            if (newsList) {
                newsList.innerHTML = '<div class="error-state" style="text-align:center;padding:40px;color:#ef4444;">加载失败，请稍后重试</div>';
            }
        }
    }

    showSourcesConfig() {
        const modal = document.getElementById('nh-sources-modal');
        if (!modal) return;
        modal.style.display = 'flex';
        this.renderSourcesList();
    }

    renderSourcesList() {
        const container = document.getElementById('nh-sources-list');
        if (!container) return;

        if (!this.sources?.length) {
            container.innerHTML = '<div class="empty-state">没有可配置的数据源</div>';
            return;
        }

        let html = `
            <div class="nh-source-add-form" style="margin-bottom:20px;padding:15px;background:var(--bg-secondary);border-radius:8px;border:1px solid var(--border-color);">
                <h4 style="margin-bottom:10px;font-size:14px;">添加自定义 RSS 源</h4>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <input type="text" id="nh-new-source-name" placeholder="源名称" style="flex:1;min-width:120px;padding:8px;border-radius:4px;border:1px solid var(--border-color);">
                    <input type="text" id="nh-new-source-url" placeholder="RSS URL" style="flex:2;min-width:180px;padding:8px;border-radius:4px;border:1px solid var(--border-color);">
                    <select id="nh-new-source-category" style="padding:8px;border-radius:4px;border:1px solid var(--border-color);">
                        <option value="tech">科技</option>
                        <option value="finance">财经</option>
                        <option value="social">综合</option>
                        <option value="ai">人工智能</option>
                    </select>
                    <button class="toolbar-btn primary" onclick="window.newshubManager.addCustomSource()" style="padding:6px 12px;">添加</button>
                </div>
            </div>
            <div class="sources-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;">`;

        this.sources.forEach((source) => {
            const isEnabled = source.enabled;
            const isCustom = String(source.id || '').startsWith('custom_');
            html += `
                <div class="mcp-card" style="padding:12px;border:1px solid var(--border-color);border-radius:6px;position:relative;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <h3 style="margin:0;font-size:14px;">${this.escapeHtml(source.name)}</h3>
                        <div style="display:flex;align-items:center;gap:8px;">
                            ${isCustom ? `<button onclick="window.newshubManager.deleteSource('${this.escapeAttr(source.id)}')" style="background:none;border:none;color:#ef4444;cursor:pointer;">删除</button>` : ''}
                            <label class="switch" style="position:relative;display:inline-block;width:34px;height:18px;">
                                <input type="checkbox" data-source-id="${this.escapeAttr(source.id)}" ${isEnabled ? 'checked' : ''} style="opacity:0;width:0;height:0;">
                                <span class="slider round"></span>
                            </label>
                        </div>
                    </div>
                    <p style="margin:0 0 8px;font-size:11px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${this.escapeAttr(source.url || '')}">${this.escapeHtml(source.url || '系统默认源')}</p>
                    <div class="mcp-status ${isEnabled ? 'running' : 'stopped'}" style="font-size:11px;">${isEnabled ? '已启用' : '已禁用'} · ${this.escapeHtml(source.category || '')}</div>
                </div>`;
        });
        html += '</div>';
        container.innerHTML = html;

        container.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
            checkbox.addEventListener('change', async (e) => {
                const sourceId = e.target.getAttribute('data-source-id');
                const isEnabled = e.target.checked;
                try {
                    const action = isEnabled ? 'enable' : 'disable';
                    await this._fetchJson(`/api/newshub/sources/${sourceId}/${action}`, { method: 'POST' });
                    const src = this.sources.find((s) => s.id === sourceId);
                    if (src) src.enabled = isEnabled;
                    this.updateStats({
                        sources: this.sources.filter((s) => s.enabled).length,
                        total_sources: this.sources.length,
                    });
                    window.app?.showNotification?.(`${isEnabled ? '启用' : '禁用'}成功`, 'success');
                } catch {
                    e.target.checked = !isEnabled;
                    window.app?.showNotification?.('操作失败', 'error');
                }
            });
        });
    }

    async addCustomSource() {
        const name = document.getElementById('nh-new-source-name')?.value.trim();
        const url = document.getElementById('nh-new-source-url')?.value.trim();
        const category = document.getElementById('nh-new-source-category')?.value;
        if (!name || !url) {
            window.app?.showNotification?.('请填写源名称和 URL', 'warning');
            return;
        }
        try {
            await this._fetchJson('/api/newshub/sources', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, url, category, type: 'rss' }),
            });
            window.app?.showNotification?.('数据源添加成功', 'success');
            await this.loadSources();
            this.renderSourcesList();
        } catch (error) {
            window.app?.showNotification?.('添加失败: ' + error.message, 'error');
        }
    }

    async deleteSource(sourceId) {
        if (!confirm('确定要删除这个数据源吗？')) return;
        try {
            await this._fetchJson(`/api/newshub/sources/${sourceId}`, { method: 'DELETE' });
            window.app?.showNotification?.('数据源已删除', 'success');
            await this.loadSources();
            this.renderSourcesList();
        } catch {
            window.app?.showNotification?.('删除失败', 'error');
        }
    }

    writeArticle(newsId) {
        const news = this.allNews.find((n) => n.id === newsId) || this.news.find((n) => n.id === newsId);
        if (!news) return;

        if (window.app?.showView) {
            window.app.showView('creative-workshop');
        }

        const performIntegration = () => {
            if (!window.creativeWorkshopManager?.initialized) {
                setTimeout(performIntegration, 200);
                return;
            }
            const topicInput = document.getElementById('topic-input');
            if (topicInput) {
                topicInput.value = news.title;
                topicInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            const refUrlsInput = document.getElementById('reference-urls');
            if (refUrlsInput && news.url) {
                refUrlsInput.value = news.url;
                refUrlsInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            window.app?.showNotification?.('已带入热点话题，可前往「内容生成」继续写作', 'info');
        };
        setTimeout(performIntegration, 300);
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

    showSuccess(message) {
        window.app?.showNotification?.(message, 'success');
    }

    showError(message) {
        window.app?.showNotification?.(message, 'error');
    }
}

if (typeof window !== 'undefined') {
    window.getNewsHubManager = function () {
        if (!window.newshubManager) {
            window.newshubManager = new NewsHubManager();
        }
        return window.newshubManager;
    };
}
