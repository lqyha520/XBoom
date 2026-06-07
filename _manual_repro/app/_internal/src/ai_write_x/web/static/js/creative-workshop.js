/**        
 * 内容生成管理器        
 * 职责:话题输入、内容生成、配置面板管理、日志流式传输        
 */
const ErrorType = {
    PROCESS: 'process',
    SYSTEM: 'system',
    VALIDATION: 'validation'
};

class CreativeWorkshopManager {

    constructor() {
        this.isGenerating = false;
        this.currentTopic = '';
        this.generationHistory = [];
        this.templateCategories = [];
        this.templates = [];
        this.logWebSocket = null;
        this.statusPollInterval = null;
        this.bottomProgress = new BottomProgressManager();
        this._hotSearchPlatform = '';

        this.messageQueue = [];  // 消息队列
        this.isProcessingQueue = false;  // 是否正在处理队列
        // 实时预览相关
        this.livePreviewContent = '';
        this.isCapturingContent = false;

        // v5: 增强 WebSocket 重连控制与耗时计时器
        this._wsReconnectAttempts = 0;
        this._wsMaxReconnects = 10;
        this._wsReconnectTimer = null;
        this._wsHeartbeatTimer = null;
        this._generationStartTime = 0;
        this._generationTimer = null;

        // v2: 幂等性控制 - 防止handleGenerationComplete被重复调用
        this._generationCompleteHandled = false;
        // v2: 轮询启动时间戳
        this._pollingStartTime = 0;

        // 防止后台节流导致假死：监听页面可见性变化
        this._onVisibilityChange = this._handleVisibilityChange.bind(this);
        document.addEventListener('visibilitychange', this._onVisibilityChange);

        this.initialized = false;
        this.initializing = false;
    }

    async init() {
        // 防止重复初始化或并发初始化
        if (this.initialized || this.initializing) {
            return;
        }

        this.initializing = true;

        try {
            this.bindEventListeners();
            this.loadHistory();
            this.initKeyboardShortcuts();
            await this.loadTemplateCategories();
            await this.loadArticleList();  // 加载文章列表
            await this.resetStaleGenerationState();
            this.initialized = true;
        } catch (error) {
            console.error('CreativeWorkshopManager 初始化失败:', error);
        } finally {
            this.initializing = false;
        }
    }

    destroy() {
        // 移除可见性监听
        if (this._onVisibilityChange) {
            document.removeEventListener('visibilitychange', this._onVisibilityChange);
            this._onVisibilityChange = null;
        }

        // 断开 WebSocket  
        this.disconnectLogWebSocket();

        // 停止状态轮询  
        this.stopStatusPolling();

        // v5: 清理重连定时器、心跳和计时器
        if (this._wsReconnectTimer) {
            clearTimeout(this._wsReconnectTimer);
            this._wsReconnectTimer = null;
        }
        this._stopHeartbeat();
        this._stopGenerationTimer();
    }

    // ========== 耗时计时器 (v5新增) ==========
    _startGenerationTimer() {
        this._stopGenerationTimer();
        this._generationStartTime = Date.now();
        this._generationTimer = setInterval(() => {
            if (!this.isGenerating) {
                this._stopGenerationTimer();
                return;
            }
            const progressText = document.getElementById('progress-text');
            if (progressText && progressText.textContent) {
                let baseText = progressText.textContent;
                // 去除可能已有的时间文本，只取基础进度
                if (baseText.includes(' (')) {
                    baseText = baseText.split(' (')[0];
                }
                const elapsed = Math.floor((Date.now() - this._generationStartTime) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                progressText.textContent = `${baseText} (${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')})`;
            }
        }, 1000);
    }

    _stopGenerationTimer() {
        if (this._generationTimer) {
            clearInterval(this._generationTimer);
            this._generationTimer = null;
        }
    }

    // ========== 模板数据加载 ==========      

    async loadTemplateCategories() {
        try {
            const response = await fetch('/api/templates/categories');
            if (response.ok) {
                const result = await response.json();
                this.templateCategories = result.data || [];
                this.populateTemplateCategoryOptions();
            } else {
                console.error('加载模板分类失败:', response.status);
                this.templateCategories = [];
                this.populateTemplateCategoryOptions();
            }
        } catch (error) {
            console.error('加载模板分类失败:', error);
            this.templateCategories = [];
            this.populateTemplateCategoryOptions();
        }
    }

    populateTemplateCategoryOptions() {
        const select = document.getElementById('workshop-template-category');
        if (!select || !this.templateCategories) return;

        select.innerHTML = '';

        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '随机分类';
        select.appendChild(defaultOption);

        this.templateCategories.forEach(category => {
            const categoryName = typeof category === 'object' ? category.name : category;
            const option = document.createElement('option');
            option.value = categoryName;
            option.textContent = categoryName;
            select.appendChild(option);
        });
    }

    async loadTemplatesByCategory(category) {
        try {
            if (!category) {
                return [];
            }

            const response = await fetch(`/api/templates?category=${encodeURIComponent(category)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            return result.data || [];
        } catch (error) {
            console.error('加载模板列表失败:', error);
            return [];
        }
    }

    populateTemplateOptions(templates) {
        const select = document.getElementById('workshop-template-name');
        if (!select) return;

        select.innerHTML = '';

        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '随机模板';
        select.appendChild(defaultOption);

        templates.forEach(template => {
            const templateName = typeof template === 'object' ? template.name : template;
            const option = document.createElement('option');
            option.value = templateName;
            option.textContent = templateName;
            select.appendChild(option);
        });
    }

    // ========== 事件监听器 ==========      

    bindEventListeners() {
        const topicInput = document.getElementById('topic-input');
        if (topicInput) {
            topicInput.addEventListener('input', (e) => {
                this.currentTopic = e.target.value;
            });

            topicInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (!this.isGenerating) {
                        this.startGeneration();
                    }
                }
            });
        }

        const generateBtn = document.getElementById('generate-btn');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => {
                if (this.isGenerating) {
                    this.stopGeneration();
                } else {
                    this.startGeneration();
                }
            });
        }

        //  借鉴模式按钮事件  
        const referenceModeBtn = document.getElementById('reference-mode-btn');
        if (referenceModeBtn) {
            referenceModeBtn.addEventListener('click', () => {
                this.toggleReferenceMode();
            });
        }

        const logProgressBtn = document.getElementById('log-progress-btn');
        if (logProgressBtn) {
            logProgressBtn.addEventListener('click', () => {
                const refPanel = document.getElementById('reference-mode-panel');
                const referenceModeBtn = document.getElementById('reference-mode-btn');

                if (refPanel && !refPanel.classList.contains('collapsed')) {
                    refPanel.classList.add('collapsed');
                    if (referenceModeBtn && !this.isGenerating) {
                        referenceModeBtn.classList.remove('active');
                    }
                }

                this.switchOutputTab('logs');
                logProgressBtn.classList.add('active');
                document.getElementById('live-preview-btn')?.classList.remove('active');
            });
        }

        const livePreviewBtn = document.getElementById('live-preview-btn');
        if (livePreviewBtn) {
            livePreviewBtn.addEventListener('click', () => {
                this.switchOutputTab('preview');
            });
        }

        document.getElementById('tab-preview-btn')?.addEventListener('click', () => {
            this.switchOutputTab('preview');
        });
        document.getElementById('tab-logs-btn')?.addEventListener('click', () => {
            this.switchOutputTab('logs');
        });

        document.getElementById('open-sidebar-preview-btn')?.addEventListener('click', () => {
            this.openSidebarPreview();
        });

        // 预览面板控制按钮
        const scrollBtn = document.getElementById('live-preview-scroll-btn');
        if (scrollBtn) {
            scrollBtn.addEventListener('click', () => {
                const content = document.getElementById('live-preview-content');
                if (content) content.scrollTop = content.scrollHeight;
            });
        }
        const clearPreviewBtn = document.getElementById('live-preview-clear-btn');
        if (clearPreviewBtn) {
            clearPreviewBtn.addEventListener('click', () => {
                this.livePreviewContent = '';
                this.isCapturingContent = false;
                const contentEl = document.getElementById('live-preview-content');
                if (contentEl) {
                    contentEl.innerHTML = `<div id="live-preview-placeholder" class="live-preview-placeholder">
                        <div class="placeholder-icon" aria-hidden="true">📝</div>
                        <p class="placeholder-title">已清空</p>
                        <p class="placeholder-hint">再次生成后将显示新内容</p>
                    </div>`;
                }
                this.setPreviewStatus('等待生成', 'idle');
                this.setPreviewMeta('');
            });
        }

        const exportLogsBtn = document.getElementById('export-logs-btn');
        if (exportLogsBtn) {
            exportLogsBtn.addEventListener('click', () => {
                this.exportLogs();
            });
        }

        const clearLogsBtn = document.getElementById('clear-logs-btn');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => {
                const logsOutput = document.getElementById('logs-output');
                if (logsOutput) {
                    logsOutput.innerHTML = '';
                }
            });
        }

        // 一键复制所有日志
        const copyLogsBtn = document.getElementById('copy-logs-btn');
        if (copyLogsBtn) {
            copyLogsBtn.addEventListener('click', async () => {
                const logsOutput = document.getElementById('logs-output');
                if (!logsOutput) return;

                // 获取所有日志文本
                const logEntries = logsOutput.querySelectorAll('.log-entry');
                let allLogs = '';
                logEntries.forEach(entry => {
                    const time = entry.querySelector('.log-time')?.textContent || '';
                    const content = entry.querySelector('.log-content')?.textContent || entry.textContent || '';
                    allLogs += `[${time}] ${content}\n`;
                });

                if (!allLogs) {
                    this.showNotification('没有日志可复制', 'warning');
                    return;
                }

                try {
                    await navigator.clipboard.writeText(allLogs);
                    this.showNotification('日志已复制到剪贴板', 'success');
                } catch (err) {
                    // 降级方案
                    const textarea = document.createElement('textarea');
                    textarea.value = allLogs;
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    this.showNotification('日志已复制到剪贴板', 'success');
                }
            });
        }

        // 加载文章按钮事件
        const loadArticleBtn = document.getElementById('load-article-btn');
        if (loadArticleBtn) {
            loadArticleBtn.addEventListener('click', () => {
                this.loadSelectedArticle();
            });
        }

        // 文章下拉框选择后自动加载
        const referenceArticlesSelect = document.getElementById('reference-articles');
        if (referenceArticlesSelect) {
            referenceArticlesSelect.addEventListener('change', (e) => {
                if (e.target.value) {
                    this.loadSelectedArticle();
                }
            });
        }

        const categorySelect = document.getElementById('workshop-template-category');
        if (categorySelect) {
            categorySelect.addEventListener('change', async (e) => {
                const category = e.target.value;
                if (!category) {
                    this.populateTemplateOptions([]);
                } else {
                    const templates = await this.loadTemplatesByCategory(category);
                    this.populateTemplateOptions(templates);
                }
            });
        }

        // AI 自动美化开关 → 同步工作流节点可见性 + localStorage 持久化
        const autoReTemplateSwitch = document.getElementById('auto-retemplate-switch');
        if (autoReTemplateSwitch) {
            // 从 localStorage 恢复用户的选择
            const savedState = localStorage.getItem('aiwritex_auto_retemplate');
            if (savedState !== null) {
                autoReTemplateSwitch.checked = savedState === 'true';
            }
            // 初始化时同步工作流节点显隐
            const initShow = autoReTemplateSwitch.checked ? '' : 'none';
            const initNode = document.getElementById('wf-node-retemplate');
            const initLine = document.getElementById('wf-line-retemplate');
            if (initNode) initNode.style.display = initShow;
            if (initLine) initLine.style.display = initShow;

            autoReTemplateSwitch.addEventListener('change', (e) => {
                const node = document.getElementById('wf-node-retemplate');
                const line = document.getElementById('wf-line-retemplate');
                const show = e.target.checked ? '' : 'none';
                if (node) node.style.display = show;
                if (line) line.style.display = show;
                // 持久化到 localStorage
                localStorage.setItem('aiwritex_auto_retemplate', e.target.checked);
            });
        }

        const workshopFastMode = document.getElementById('workshop-fast-mode');
        if (workshopFastMode && autoReTemplateSwitch) {
            const syncBeautifyWithFastMode = () => {
                if (workshopFastMode.checked) {
                    autoReTemplateSwitch.checked = false;
                    autoReTemplateSwitch.disabled = true;
                    const node = document.getElementById('wf-node-retemplate');
                    const line = document.getElementById('wf-line-retemplate');
                    if (node) node.style.display = 'none';
                    if (line) line.style.display = 'none';
                } else {
                    autoReTemplateSwitch.disabled = false;
                    const show = autoReTemplateSwitch.checked ? '' : 'none';
                    const node = document.getElementById('wf-node-retemplate');
                    const line = document.getElementById('wf-line-retemplate');
                    if (node) node.style.display = show;
                    if (line) line.style.display = show;
                }
            };
            workshopFastMode.addEventListener('change', syncBeautifyWithFastMode);
            syncBeautifyWithFastMode();
        }

        // V15.2: 过滤已处理话题开关持久化
        const workshopFilterProcessed = document.getElementById('workshop-filter-processed');
        if (workshopFilterProcessed) {
            const savedState = localStorage.getItem('aiwritex_workshop_filter_processed');
            if (savedState !== null) {
                workshopFilterProcessed.checked = savedState === 'true';
            }
            workshopFilterProcessed.addEventListener('change', (e) => {
                localStorage.setItem('aiwritex_workshop_filter_processed', e.target.checked);
            });
        }
    }

    // ========== 借鉴模式管理 ==========      

    toggleReferenceMode() {
        const panel = document.getElementById('reference-mode-panel');
        const referenceModeBtn = document.getElementById('reference-mode-btn');
        const logPanel = document.getElementById('generation-progress');  // 新增  

        if (!panel || !referenceModeBtn) return;

        if (this.isGenerating) {
            window.app?.showNotification('生成过程中无法切换借鉴模式', 'warning');
            return;
        }

        if (panel.classList.contains('collapsed')) {
            // 展开借鉴面板前,先关闭日志面板  
            if (logPanel && !logPanel.classList.contains('collapsed')) {
                logPanel.classList.add('collapsed');
            }

            panel.classList.remove('collapsed');
            referenceModeBtn.classList.add('active');
            this.resetReferenceForm();
            this.setReferenceFormState(false);

            setTimeout(() => {
                panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
        } else {
            panel.classList.add('collapsed');
            referenceModeBtn.classList.remove('active');
            this.setReferenceFormState(true);
        }
    }

    async resetReferenceForm() {
        const categorySelect = document.getElementById('workshop-template-category');
        if (categorySelect) {
            categorySelect.value = '';
        }

        this.populateTemplateOptions([]);

        const urlsTextarea = document.getElementById('reference-urls');
        if (urlsTextarea) {
            urlsTextarea.value = '';
        }

        const ratioSelect = document.getElementById('reference-ratio');
        if (ratioSelect) {
            ratioSelect.value = '30';
        }
    }

    setReferenceFormState(disabled) {
        const formElements = [
            'workshop-template-category',
            'workshop-template-name',
            'reference-urls',
            'reference-ratio'
        ];

        formElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = disabled;
            }
        });
    }

    getReferenceConfig() {
        const panel = document.getElementById('reference-mode-panel');
        const isEnabled = panel && !panel.classList.contains('collapsed');

        if (!isEnabled) {
            return null;
        }

        // 获取选中的文章ID
        const articleSelect = document.getElementById('reference-articles');
        const selectedArticleId = articleSelect?.value || '';

        return {
            template_category: document.getElementById('workshop-template-category')?.value || '',
            template_name: document.getElementById('workshop-template-name')?.value || '',
            reference_urls: document.getElementById('reference-urls')?.value || '',
            reference_ratio: parseInt(document.getElementById('reference-ratio')?.value || '30'),
            reference_article_id: selectedArticleId
        };
    }

    /** 放弃上次未完成/残留的生成任务，清空前端缓存态（不续跑旧稿） */
    async resetStaleGenerationState() {
        try {
            await fetch('/api/generate/reset', { method: 'POST' });
        } catch (error) {
            try {
                await fetch('/api/generate/stop', { method: 'POST' });
            } catch (e) {
                console.error('清理中断任务状态失败:', e);
            }
        }

        this.isGenerating = false;
        this._generationCompleteHandled = false;
        this.livePreviewContent = '';
        this.isCapturingContent = false;
        this.messageQueue = [];
        this.isProcessingQueue = false;
        this._hotSearchPlatform = '';

        const contentEl = document.getElementById('live-preview-content');
        if (contentEl) {
            contentEl.innerHTML = '';
        }
        const statusEl = document.getElementById('live-preview-status');
        if (statusEl) {
            statusEl.textContent = '';
        }

        if (this.bottomProgress) {
            this.bottomProgress.stop();
        }
        const progressEl = document.getElementById('bottom-progress');
        if (progressEl) {
            progressEl.classList.add('hidden');
        }

        this.updateGenerationUI(false);
        this.stopStatusPolling();
        this.disconnectLogWebSocket();
        this._stopGenerationTimer();
    }

    // ========== 内容生成流程 ==========      

    async startGeneration() {
        // ========== 阶段 1: 前置检查 ==========  
        if (this.isGenerating) return;

        // 每次点击「开始生成」都放弃上次未完成任务，从零开始
        await this.resetStaleGenerationState();

        // ========== 阶段 2: 系统配置校验 ==========  
        try {
            const configResponse = await fetch('/api/config/validate');
            if (!configResponse.ok) {
                const error = await configResponse.json();
                this.showConfigErrorDialog(error.detail || '系统配置错误,请检查配置');
                return;
            }
        } catch (error) {
            console.error('配置验证失败:', error);
            this.showConfigErrorDialog('无法验证配置,请检查设置');
            return;
        }

        // ========== 阶段 3: 获取话题 ==========  
        let topic = this.currentTopic.trim();
        let referenceConfig = this.getReferenceConfig();

        // 借鉴模式参数校验  
        if (referenceConfig) {
            // 检查是否有参考内容（文章ID或URL）
            const hasReferenceContent = referenceConfig.reference_article_id || referenceConfig.reference_urls;

            // 如果没有话题也没有参考内容，则提示错误
            if (!topic && !hasReferenceContent) {
                window.app?.showNotification('借鉴模式下请输入话题，或选择已有文章/填写参考链接', 'error');
                return;
            }

            // 有参考内容但没有话题，会自动从参考内容提取话题
            if (!topic && hasReferenceContent) {
                window.app?.showNotification('将根据参考内容自动生成话题...', 'info');
            }

            if (referenceConfig.reference_urls) {
                const urls = referenceConfig.reference_urls.split('|')
                    .map(u => u.trim())
                    .filter(u => u);

                const invalidUrls = urls.filter(url => !this.isValidUrl(url));
                if (invalidUrls.length > 0) {
                    window.app?.showNotification(
                        '存在无效的URL,请检查输入(确保使用http://或https://)',
                        'error'
                    );
                    return;
                }
            }
        }

        // ========== 阶段 4: 所有校验通过,启动生成 ==========  
        try {
            // 提前设置生成状态, 让UI立即响应
            this.isGenerating = true;
            this.updateGenerationUI(true);
            this._startGenerationTimer(); // V5 启动计时器

            // 启动进度条  
            if (this.bottomProgress) {
                this.bottomProgress.start('init');
                const progressEl = document.getElementById('bottom-progress');
                if (progressEl) {
                    progressEl.classList.remove('hidden');
                }
            }

            // 初始化日志按钮显示  
            this.updateLogButtonProgress('init', 0);

            // 清空消息队列,准备新任务  
            this.clearMessageQueue();

            // 记录日志 - 根据模式显示不同信息
            let taskMode = referenceConfig ? '借鉴模式' : '热搜模式';
            let logMessage = `🚀 开始生成任务`;

            if (referenceConfig) {
                if (referenceConfig.reference_article_id && this._selectedArticle) {
                    const articleTitle = this._selectedArticle.title || '未知文章';
                    const articleSource = this._selectedArticle.source || '热点';
                    logMessage = `🚀 开始生成任务 (借鉴模式)`;
                    this.appendLog(logMessage, 'status', false, Date.now() / 1000);
                    this.appendLog(`📰 参考文章: [${articleSource}] ${articleTitle}`, 'info', false, Date.now() / 1000);
                } else if (referenceConfig.reference_urls) {
                    logMessage = `🚀 开始生成任务 (借鉴模式 - 参考链接)`;
                    this.appendLog(logMessage, 'status', false, Date.now() / 1000);
                } else {
                    this.appendLog(`🚀 开始生成任务 (${taskMode})`, 'status', false, Date.now() / 1000);
                }
            } else {
                this.appendLog(`🚀 开始生成任务 (${taskMode})`, 'status', false, Date.now() / 1000);
            }

            // 自动获取热搜交由后端处理
            if (!topic && !referenceConfig) {
                // 获取批量生成配置
                const currentArticleCount = parseInt(document.getElementById('article-count')?.value || '1', 10);

                if (currentArticleCount === 1) {
                    window.app?.showNotification('正在开启全网搜索与AI权威审稿...', 'info');
                    this.appendLog('🌍 话题为空，已开启【权威优先聚合搜索】模式生成单篇深度爆款...', 'info', false, Date.now() / 1000);
                } else {
                    this.appendLog(`🔍 话题为空，已开启【权威优先聚合搜索】模式生成 ${currentArticleCount} 篇独立的新闻/热点...`, 'info', false, Date.now() / 1000);
                }
            }

            // 添加到历史记录  
            if (topic) {
                this.addToHistory(topic);
            }

            // ========== 阶段 5: 发起生成请求 ==========  
            // 获取批量生成配置
            const articleCount = parseInt(document.getElementById('article-count')?.value || '1', 10);
            const postAction = document.getElementById('post-action')?.value || 'none';

            const autoReTemplateSwitch = document.getElementById('auto-retemplate-switch');
            const fastModeSwitch = document.getElementById('workshop-fast-mode');
            const isFastModeOn = fastModeSwitch ? fastModeSwitch.checked : false;
            let isBeautifyOn = autoReTemplateSwitch ? autoReTemplateSwitch.checked : false;
            if (isFastModeOn && isBeautifyOn) {
                isBeautifyOn = false;
                this.appendLog('⚡ 极速模式已开启，已跳过「自动换模板」', 'info', false, Date.now() / 1000);
            }

            const workshopFilterProcessed = document.getElementById('workshop-filter-processed');

            if (isFastModeOn) {
                this.appendLog('⚡ 极速模式已开启：将跳过深度审计、预览截图与标题优化；正文会走轻量配图提示词并继续调用生图。', 'info', false, Date.now() / 1000);
            }

            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    topic: topic,
                    platform: this._hotSearchPlatform || '',
                    reference: referenceConfig,
                    article_count: articleCount,
                    post_action: postAction,
                    ai_beautify: isBeautifyOn,
                    filter_processed: workshopFilterProcessed?.checked || false,
                    fast_mode: isFastModeOn,
                    collection_mode: document.getElementById('workshop-collection-mode')?.checked || false
                })
            });

            if (!response.ok) {
                const error = await response.json();

                // 请求失败:清理进度条和队列  
                this.cleanupProgress();
                this.resetLogButton();
                this.clearMessageQueue();

                if (response.status === 400 && error.detail &&
                    (error.detail.includes('API KEY') ||
                        error.detail.includes('Model') ||
                        error.detail.includes('配置错误'))) {
                    this.showConfigErrorDialog(error.detail);
                } else {
                    window.app?.showNotification('生成失败: ' + (error.detail || '未知错误'), 'error');
                }

                this.isGenerating = false;
                this.updateGenerationUI(false);
                return;
            }

            const result = await response.json();
            window.app?.showNotification(result.message || '内容生成已开始', 'success');

            // 【新增】注册到全局后台任务管理器
            if (window.articleManager) {
                window.articleManager.addTask('article-generation', {
                    name: `AI 创作: ${topic.substring(0, 15)}${topic.length > 15 ? '...' : ''}`,
                    type: 'generation'
                });
            }

            // 连接 WebSocket 接收实时日志  
            this.connectLogWebSocket();

            // 此处开始等待完成
            this.startStatusPolling();

        } catch (error) {
            console.error('流程启动或生成过程中失败:', error);

            // 异常:清理进度条和队列  
            this.cleanupProgress();
            this.resetLogButton();  // 重置日志按钮  
            this.clearMessageQueue();

            window.app?.showNotification('生成失败: ' + (error.message || '未知异常情况'), 'error');
            this.appendLog(`❌ 生成失败: ${error.message || '未知异常情况'}`, 'error', false, Date.now() / 1000);
            this.isGenerating = false;
            this.updateGenerationUI(false);
        }
    }

    // 清理进度条的辅助方法    
    cleanupProgress() {
        if (this.bottomProgress) {
            this.bottomProgress.stop();
            const progressEl = document.getElementById('bottom-progress');
            if (progressEl) {
                progressEl.classList.add('hidden');
            }
            this.bottomProgress.reset();
        }
    }

    isValidUrl(url) {
        try {
            const urlObj = new URL(url);
            return urlObj.protocol === 'http:' || urlObj.protocol === 'https:';
        } catch {
            return false;
        }
    }

    showConfigErrorDialog(errorMessage) {
        const dialogHtml = `      
            <div class="modal-overlay" id="config-error-dialog">      
                <div class="modal-content" style="max-width: 500px;">      
                    <div class="modal-header">      
                        <h3>配置错误</h3>      
                        <button class="modal-close" onclick="window.creativeWorkshopManager.closeConfigErrorDialog()">×</button>      
                    </div>      
                    <div class="modal-body">      
                        <div class="error-icon" style="text-align: center; margin-bottom: 20px;">      
                            <svg viewBox="0 0 24 24" width="64" height="64" fill="none" stroke="#ef4444" stroke-width="2">      
                                <circle cx="12" cy="12" r="10"/>      
                                <line x1="12" y1="8" x2="12" y2="12"/>      
                                <line x1="12" y1="16" x2="12.01" y2="16"/>      
                            </svg>      
                        </div>      
                        <p style="text-align: center; color: var(--text-secondary); margin-bottom: 20px;">      
                            ${this.escapeHtml(errorMessage)}      
                        </p>      
                    </div>      
                    <div class="modal-footer">      
                        <button class="btn btn-secondary" onclick="window.creativeWorkshopManager.closeConfigErrorDialog()">取消</button>      
                        <button class="btn btn-primary" onclick="window.creativeWorkshopManager.goToConfig('${this.getConfigPanelFromError(errorMessage)}')">前往配置</button>      
                    </div>      
                </div>      
            </div>      
        `;

        document.body.insertAdjacentHTML('beforeend', dialogHtml);
    }

    getConfigPanelFromError(errorMessage) {
        if (errorMessage.includes('微信公众号') || errorMessage.includes('appid') || errorMessage.includes('appsecret')) {
            return 'wechat';
        } else if (errorMessage.includes('API KEY') || errorMessage.includes('Model') || errorMessage.includes('api_key') || errorMessage.includes('model')) {
            return 'api';
        } else if (errorMessage.includes('图片生成')) {
            return 'img-api';
        } else {
            return 'api';
        }
    }

    goToConfig(panelId = 'api') {
        this.closeConfigErrorDialog();

        const configLink = document.querySelector('[data-view="config-manager"]');
        if (configLink) {
            configLink.click();

            setTimeout(() => {
                const targetPanel = document.querySelector(`[data-config="${panelId}"]`);
                if (targetPanel) {
                    targetPanel.click();
                }
            }, 100);
        }
    }

    closeConfigErrorDialog() {
        const dialog = document.getElementById('config-error-dialog');
        if (dialog) dialog.remove();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async stopGeneration() {
        if (!this.isGenerating) return;

        try {
            const response = await fetch('/api/generate/stop', {
                method: 'POST'
            });

            if (response.ok) {
                const result = await response.json();

                // 等待队列处理完毕  
                while (this.isProcessingQueue) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                }

                // 清空队列  
                this.clearMessageQueue();

                // 清理进度条  
                this.cleanupProgress();

                // 【新增】重置日志按钮  
                this.resetLogButton();

                this.disconnectLogWebSocket();
                this.stopStatusPolling();

                this._hotSearchPlatform = '';
                const topicInput = document.getElementById('topic-input');
                if (topicInput) {
                    topicInput.value = '';
                    this.currentTopic = '';
                }

                window.app?.showNotification(result.message || '已停止生成', 'info');
            }
        } catch (error) {
            console.error('停止生成失败:', error);
            window.app?.showNotification('停止失败', 'error');
        } finally {
            this.isGenerating = false;
            this.updateGenerationUI(false);
            this._stopGenerationTimer(); // 关闭计时器

            // 【新增】从全局任务管理器移除
            if (window.articleManager) {
                window.articleManager.removeTask('article-generation');
            }
        }
    }

    resetLogButton() {
        const progressText = document.getElementById('progress-text');
        const btnIcon = document.querySelector('#log-progress-btn .btn-icon');

        if (progressText) {
            progressText.textContent = '日志';
        }

        if (btnIcon) {
            // 恢复默认图标  
            btnIcon.innerHTML = '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>';
            btnIcon.classList.remove('rotating');
        }
    }
    // ========== WebSocket 日志流式传输 (v2: 自动重连+心跳) ==========      

    connectLogWebSocket() {
        if (this.logWebSocket) {
            this.logWebSocket.close();
        }

        // v2: 重置重连计数器（首次连接时）
        if (this._wsReconnectAttempts === 0) {
            this._generationCompleteHandled = false;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/ws/generate/logs`;

        try {
            this.logWebSocket = new WebSocket(wsUrl);

            this.logWebSocket.onopen = () => {
                console.log('日志 WebSocket 已连接');
                this._wsReconnectAttempts = 0; // v2: 连接成功后重置重连计数
                this._startHeartbeat(); // v2: 启动心跳
            };

            this.logWebSocket.onmessage = async (event) => {
                try {
                    const data = JSON.parse(event.data);

                    // v2: 心跳pong响应忽略
                    if (data.type === 'pong') return;

                    if (data.message && data.message.includes('[PROGRESS:')) {
                        // 提取所有进度标记  
                        const progressMarkers = data.message.match(/\[PROGRESS:[^\]]+\]/g);
                    }
                    // 将消息加入队列而不是直接处理  
                    this.messageQueue.push(data);

                    // 如果没有在处理队列,启动处理  
                    if (!this.isProcessingQueue) {
                        this.processMessageQueue();
                    }

                    // 转发到全局日志面板      
                    this.appendLog(data.message, data.type, false, data.timestamp);

                    // 后台补图完成通知：自动刷新文章列表
                    if (data.message && data.message.includes('[IMG_FIX_DONE]')) {
                        try {
                            if (window.articleManager) {
                                await window.articleManager.loadArticles();
                                window.articleManager.renderStatusTree();
                            }
                        } catch (e) { console.warn('补图完成后刷新文章列表失败:', e); }
                    }

                    // 实时预览：截取 AI 输出内容（status 类型 = AI 内容块）
                    if (data.message) {
                        this.updateLivePreview(data.message, data.type);
                    }

                    if (data.article_paths?.length) {
                        this._lastGeneratedArticlePaths = data.article_paths;
                    }

                    // 检查完成状态      
                    if (data.type === 'completed' || data.type === 'failed') {
                        this._stopHeartbeat(); // v2: 停止心跳
                        this.handleGenerationComplete(data);
                    }
                } catch (error) {
                    console.error('解析日志消息失败:', error);
                }
            };

            this.logWebSocket.onerror = (error) => {
                console.error('WebSocket 错误:', error);
            };

            this.logWebSocket.onclose = (event) => {
                this._stopHeartbeat(); // v2: 停止心跳
                this.logWebSocket = null;

                // v5: 智能重连 - 仅在生成进行中且未收到完成消息时重连
                if (this.isGenerating && !this._generationCompleteHandled) {
                    if (this._wsReconnectAttempts < this._wsMaxReconnects) {
                        this._wsReconnectAttempts++;
                        // v5 指数退避: 限制最大为 16s (1s, 2s, 4s, 8s, 16s...)
                        const delay = Math.min(1000 * Math.pow(2, this._wsReconnectAttempts - 1), 16000);
                        console.log(`[WebSocket] 断连，${delay / 1000}秒后第${this._wsReconnectAttempts}次重连...`);
                        this._wsReconnectTimer = setTimeout(() => {
                            if (this.isGenerating && !this._generationCompleteHandled) {
                                this.connectLogWebSocket();
                            }
                        }, delay);
                    } else {
                        console.warn('[WebSocket] 重连次数耗尽，已回退至状态轮询');
                    }
                }
            };
        } catch (error) {
            console.error('创建 WebSocket 连接失败:', error);
        }
    }

    // v2: 心跳机制 - 使用 Web Worker 保持后台心跳不被节流
    _startHeartbeat() {
        this._stopHeartbeat();
        // 创建内联 Web Worker 用于心跳定时
        const workerCode = `
            let timer = null;
            self.onmessage = function(e) {
                if (e.data === 'start') {
                    timer = setInterval(() => self.postMessage('ping'), 30000);
                } else if (e.data === 'stop') {
                    clearInterval(timer);
                    timer = null;
                }
            };
        `;
        const blob = new Blob([workerCode], { type: 'application/javascript' });
        this._heartbeatWorker = new Worker(URL.createObjectURL(blob));
        this._heartbeatWorker.onmessage = () => {
            if (this.logWebSocket && this.logWebSocket.readyState === WebSocket.OPEN) {
                try {
                    this.logWebSocket.send(JSON.stringify({ type: 'ping' }));
                } catch (e) {
                    console.warn('心跳发送失败:', e.message);
                }
            }
        };
        this._heartbeatWorker.postMessage('start');
    }

    _stopHeartbeat() {
        if (this._heartbeatWorker) {
            this._heartbeatWorker.postMessage('stop');
            this._heartbeatWorker.terminate();
            this._heartbeatWorker = null;
        }
        if (this._wsHeartbeatTimer) {
            clearInterval(this._wsHeartbeatTimer);
            this._wsHeartbeatTimer = null;
        }
    }

    /**
     * 处理页面可见性变化，防止后台节流导致假死
     * 当窗口从后台恢复到前台时：
     * 1. 如果正在生成且WebSocket已断开，自动重连
     * 2. 如果正在生成且轮询已停止，恢复轮询
     * 3. 主动查询一次最新状态，避免错过完成事件
     */
    _handleVisibilityChange() {
        if (document.hidden) {
            // 页面进入后台，无需特殊处理（浏览器会自动节流定时器）
            console.log('[Visibility] 页面进入后台，定时器可能被节流');
            return;
        }

        // 页面恢复前台
        console.log('[Visibility] 页面恢复前台，检查生成状态...');

        if (!this.isGenerating) {
            return;
        }

        // 1. 检查WebSocket连接状态，断开则重连
        if (!this.logWebSocket || this.logWebSocket.readyState !== WebSocket.OPEN) {
            console.log('[Visibility] WebSocket 已断开，正在重连...');
            this._wsReconnectAttempts = 0; // 重置重连计数，允许重新连接
            this.connectLogWebSocket();
        } else {
            // 连接仍在，重启心跳确保活跃
            this._startHeartbeat();
        }

        // 2. 恢复状态轮询（如果已停止）
        if (!this.statusPollInterval) {
            console.log('[Visibility] 恢复状态轮询...');
            this.startStatusPolling();
        }

        // 3. 立即查询一次最新状态
        fetch('/api/generate/status')
            .then(r => r.ok ? r.json() : null)
            .then(result => {
                if (!result) return;
                if (result.status === 'completed' || result.status === 'failed' || result.status === 'stopped') {
                    this.stopStatusPolling();
                    this.handleGenerationComplete({
                        type: result.status,
                        error: result.error,
                        article_paths: result.article_paths,
                        ai_beautify: result.ai_beautify,
                    });
                    this.disconnectLogWebSocket();
                }
            })
            .catch(err => console.warn('[Visibility] 状态查询失败:', err));
    }

    // 处理消息队列  
    async processMessageQueue() {
        if (this.isProcessingQueue) return;
        this.isProcessingQueue = true;

        try {
            while (this.messageQueue.length > 0) {
                const data = this.messageQueue.shift();
                const markers = this.extractProgressMarkers(data.message);

                for (const marker of markers) {
                    const { stage, progress } = this.mapMarkerToProgress(marker);

                    if (stage) {
                        if (marker.status === 'DETAIL') {
                            if (this.bottomProgress && typeof this.bottomProgress.setNodeDetail === 'function') {
                                this.bottomProgress.setNodeDetail(stage, marker.detail);
                            }
                        } else if (progress !== null) {
                            if (this.bottomProgress) {
                                this.bottomProgress.updateProgress(stage, progress);
                                this.updateLogButtonProgress(stage, progress);

                                // 【新增】同步更新全局任务管理器
                                if (window.articleManager) {
                                    window.articleManager.updateTask('article-generation', { progress });
                                }
                            }
                        }
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }
                }
            }
        } catch (error) {
            console.error("处理消息队列出错:", error);
        } finally {
            this.isProcessingQueue = false;
        }
    }

    updateLogButtonProgress(stage, progress) {
        const progressText = document.getElementById('progress-text');
        const btnIcon = document.querySelector('#log-progress-btn .btn-icon');

        if (!progressText || !btnIcon || !this.bottomProgress) return;

        const stageConfig = this.bottomProgress.stages[stage];
        if (!stageConfig) return;

        const currentProgress = Math.round(this.bottomProgress.currentProgress || 0);
        if (isNaN(currentProgress)) return;

        let timerStr = "";
        if (this._generationStartTime) {
            const elapsed = Math.floor((Date.now() - this._generationStartTime) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            timerStr = ` (${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')})`;
        }
        progressText.textContent = `${stageConfig.name} ${currentProgress}%${timerStr}`;

        // 更新SVG图标并添加旋转动画  
        btnIcon.innerHTML = stageConfig.icon;
        btnIcon.classList.add('rotating');
    }

    // 从消息中提取所有进度标记  
    extractProgressMarkers(message) {
        if (!message) return [];
        const markers = [];
        const progressRegex = /\[PROGRESS:(\w+):(START|END)\]/g;
        let match;

        while ((match = progressRegex.exec(message)) !== null) {
            markers.push({
                stage: match[1],
                status: match[2]
            });
        }

        // 捕获 DETAIL 标记
        const detailRegex = /\[PROGRESS:(\w+):DETAIL\]\s*(.+)/g;
        while ((match = detailRegex.exec(message)) !== null) {
            markers.push({
                stage: match[1],
                status: 'DETAIL',
                detail: match[2].trim()
            });
        }

        // 特殊处理完成标记  
        if (message.includes('任务执行完成')) {
            markers.push({
                stage: 'COMPLETE',
                status: 'END'
            });
        }

        return markers;
    }

    mapMarkerToProgress(marker) {
        const stageMap = {
            'INIT': { stage: 'init', start: 0, end: 15 },
            'SPIDER': { stage: 'spider', start: 15, end: 30 },
            'CREATIVE': { stage: 'planning', start: 30, end: 45 },
            'WRITING': { stage: 'writing', start: 45, end: 70 },
            'REVIEW': { stage: 'review', start: 70, end: 85 },
            'VISUAL': { stage: 'visual', start: 85, end: 95 },
            'SAVE': { stage: 'done', start: 95, end: 99 },
            'COMPLETE': { stage: 'done', start: 100, end: 100 }
        };

        const config = stageMap[marker.stage];
        if (!config) {
            return { stage: null, progress: null };
        }

        const progress = marker.status === 'START' ? config.start : config.end;
        return { stage: config.stage, progress };
    }

    // 清空消息队列  
    clearMessageQueue() {
        this.messageQueue = [];
        this.isProcessingQueue = false;
    }

    disconnectLogWebSocket() {
        if (this.logWebSocket) {
            this.logWebSocket.close();
            this.logWebSocket = null;
        }
    }

    /**      
     * 处理生成完成 (v2: 幂等性保护，防止WebSocket和轮询双重触发)  
     */
    async handleGenerationComplete(data) {
        if (data?.article_paths?.length) {
            this._lastGeneratedArticlePaths = data.article_paths;
        } else {
            this._lastGeneratedArticlePaths = [];
        }
        // v2: 幂等保护 - 避免被WebSocket和轮询同时触发
        if (this._generationCompleteHandled) {
            console.log('handleGenerationComplete 已处理过，跳过重复调用');
            return;
        }
        this._generationCompleteHandled = true;

        // 等待队列处理完毕  
        while (this.isProcessingQueue) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        this.isGenerating = false;

        // V4: 用 try/finally 保证 UI 始终重置，即使中间步骤抛错也不会卡死
        try {
            // 标记全局任务为完成
            try {
                if (window.articleManager) {
                    window.articleManager.updateTask('article-generation', {
                        progress: 100,
                        status: data.type === 'completed' ? 'done' : 'failed'
                    });
                    setTimeout(() => window.articleManager.removeTask('article-generation'), 3000);
                }
            } catch (e) { console.warn('更新任务管理器状态失败:', e); }

            // 智能恢复借鉴按钮状态  
            const refPanel = document.getElementById('reference-mode-panel');
            const logPanel = document.getElementById('generation-progress');
            const referenceModeBtn = document.getElementById('reference-mode-btn');

            if (refPanel && logPanel && referenceModeBtn) {
                if (refPanel.classList.contains('collapsed')) {
                    referenceModeBtn.classList.remove('active');
                }
            }

            if (data.type === 'completed') {
                if (!this._lastGeneratedArticlePaths?.length) {
                    window.app?.showNotification('生成完成但未产出文章，请检查配置（API Key/Model）或查看日志', 'warning');
                    this.bottomProgress?.showWarning('未产出文章');
                    this.resetLogButton();
                    this.isGenerating = false;
                    this.updateGenerationUI(false);
                    return;
                }
                if (this.bottomProgress) {
                    this.bottomProgress.complete();
                }

                // 等待进度条动画到达100%后再停止  
                setTimeout(() => {
                    if (this.bottomProgress) {
                        this.bottomProgress.stop();
                    }
                    this.resetLogButton();
                    setTimeout(() => {
                        const progressEl = document.getElementById('bottom-progress');
                        if (progressEl) {
                            progressEl.classList.add('hidden');
                        }
                        if (this.bottomProgress) {
                            this.bottomProgress.reset();
                        }
                        try { this.autoPreviewGeneratedArticle(); } catch (e) { console.warn('自动预览失败:', e); }
                    }, 1000);
                }, 1000);

            } else if (data.type === 'failed') {
                if (this.bottomProgress) {
                    this.bottomProgress.showError(data.error || '未知错误');
                }
                this.resetLogButton();
                setTimeout(() => {
                    const progressEl = document.getElementById('bottom-progress');
                    if (progressEl) {
                        progressEl.classList.add('hidden');
                    }
                    if (this.bottomProgress) {
                        this.bottomProgress.reset();
                    }
                }, 1000);

            } else if (data.type === 'stopped') {
                const progressEl = document.getElementById('bottom-progress');
                if (progressEl) {
                    progressEl.classList.add('hidden');
                }
                if (this.bottomProgress) {
                    this.bottomProgress.reset();
                }
                this.resetLogButton();
            }

            // 完成后的通知和后续操作
            if (data.type === 'completed') {
                const duration = this._generationStartTime
                    ? Math.floor((Date.now() - this._generationStartTime) / 1000)
                    : 0;
                const durationText = duration >= 60
                    ? `${Math.floor(duration / 60)}分${duration % 60}秒`
                    : `${duration}秒`;

                window.app?.showNotification(`生成完成（耗时 ${durationText}）`, 'success');
                try {
                    this.appendLog(`✅ 本次生成总耗时：${durationText}`, 'success', false, Date.now() / 1000);
                } catch (e) {
                    console.warn('写入耗时日志失败:', e);
                }

                // V5: 触发前端增强体验
                window.app?.playSuccessSound();
                window.app?.triggerCelebration();

                window.app?.trackPerformance('article_generation_completed', { duration_sec: duration, topic: this.currentTopic });

                // 自动刷新文章列表 + 侧栏状态计数
                try {
                    if (window.articleManager) {
                        await window.articleManager.loadArticles();
                        window.articleManager.renderStatusTree();
                        // 立即切换到文章库视图，让用户看到新生成的文章
                        const articleViewLink = document.querySelector('[data-view="article-manager"]');
                        if (articleViewLink) {
                            articleViewLink.click();
                        }
                    }
                } catch (e) { console.warn('刷新文章列表失败:', e); }

                // 成功后删除被借鉴的文章
                try {
                    if (this._selectedArticle?.id) {
                        this.deleteReferenceArticle(this._selectedArticle.id);
                    }
                } catch (e) { console.warn('删除借鉴文章失败:', e); }

                // ===== 生成后自动换模板（延迟启动，不阻塞文章库显示） =====
                const shouldBeautify = data.ai_beautify
                    || document.getElementById('auto-retemplate-switch')?.checked;
                if (shouldBeautify && !document.getElementById('workshop-fast-mode')?.checked) {
                    const paths = data.article_paths || this._lastGeneratedArticlePaths || [];
                    // 延迟2秒启动换模板，确保文章库先完成渲染
                    setTimeout(() => this.runAutoBeautifyAfterGenerate(paths), 2000);
                }

                // 生成后定时刷新文章列表（后台补图完成后自动更新）
                this._startPostGenerationRefresh();

            } else if (data.type === 'failed') {
                window.app?.showNotification('生成失败: ' + (data.error || '未知错误'), 'error');
            } else if (data.type === 'stopped') {
                window.app?.showNotification('生成已停止', 'info');
            }

        } catch (outerError) {
            console.error('handleGenerationComplete 内部异常:', outerError);
            window.app?.showNotification('生成流程出现异常，UI 已重置', 'warning');
        } finally {
            // V4: 无论如何都要执行 UI 重置，这是防止 UI 卡死的最后保障
            this.updateGenerationUI(false);
            this.stopStatusPolling();

            this._hotSearchPlatform = '';
            const topicInput = document.getElementById('topic-input');
            if (topicInput) {
                topicInput.value = '';
                this.currentTopic = '';
            }
        }

        if (this.logWebSocket) {
            this.logWebSocket.close();
        }
    }

    /**
     * 生成完成后自动换模板（配图已在后端同步补齐）
     */
    async runAutoBeautifyAfterGenerate(paths) {
        this.appendLog('🎨 已开启「自动换模板」，正在处理本次生成的文章...', 'info', false, Date.now() / 1000);

        let targetPath = Array.isArray(paths) && paths.length ? paths[paths.length - 1] : null;

        if (!targetPath) {
            try {
                const res = await fetch('/api/articles');
                if (res.ok) {
                    const result = await res.json();
                    const articles = (result.data || []).sort(
                        (a, b) => new Date(b.create_time) - new Date(a.create_time)
                    );
                    targetPath = articles[0]?.path;
                }
            } catch (e) {
                console.warn('获取最新文章失败:', e);
            }
        }

        if (!targetPath) {
            this.appendLog('⚠️ 未找到可换模板的文章', 'warning', false, Date.now() / 1000);
            return;
        }

        const baseName = targetPath.split(/[/\\]/).pop() || '';
        const article = {
            path: targetPath,
            title: baseName.replace(/\.[^.]+$/, '').replace(/_/g, '|'),
        };

        if (!window.articleManager?.triggerAutoReTemplate) {
            this.appendLog('⚠️ 文章库管理器未就绪，无法自动换模板', 'warning', false, Date.now() / 1000);
            return;
        }

        this.appendLog(`🎨 开始自动换模板: ${article.title}`, 'status', false, Date.now() / 1000);
        try {
            await window.articleManager.triggerAutoReTemplate(article, {
                autoSave: true,
                preserveImages: true,
            });
        } catch (err) {
            console.error('自动换模板失败:', err);
            this.appendLog(`❌ 自动换模板失败: ${err.message}`, 'error', false, Date.now() / 1000);
        }
    }

    /**  
     * 自动预览最新生成的文章  
     */
    async autoPreviewGeneratedArticle() {
        try {
            const response = await fetch('/api/articles');
            if (!response.ok) {
                console.error('获取文章列表失败');
                return;
            }

            const result = await response.json();
            if (result.status === 'success' && result.data && result.data.length > 0) {
                const articles = result.data.sort((a, b) => {
                    return new Date(b.create_time) - new Date(a.create_time);
                });

                // 【新增】保存刚刚生成的批量文章信息供对比模式翻页使用
                const articleCount = parseInt(document.getElementById('article-count')?.value || '1', 10);
                window._comparisonArticles = articles.slice(0, articleCount);
                window._currentComparisonIndex = 0;

                const latestArticle = articles[0];

                const contentResponse = await fetch(
                    `/api/articles/content?path=${encodeURIComponent(latestArticle.path)}`
                );
                if (contentResponse.ok) {
                    const content = await contentResponse.text();

                    const isHtml = content.trim().startsWith('<');
                    const ext = latestArticle.path.toLowerCase().split('.').pop();
                    let htmlContent = content;

                    if (isHtml) {
                        htmlContent = content;
                    } else if ((ext === 'md' || ext === 'markdown') && window.markdownRenderer) {
                        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
                        htmlContent = window.markdownRenderer.renderWithStyles(content, isDark);
                    }

                    this.livePreviewContent = htmlContent;
                    const contentEl = document.getElementById('live-preview-content');
                    if (contentEl) {
                        contentEl.innerHTML = `<div class="preview-article-body">${htmlContent}</div>`;
                    }
                    const charCount = htmlContent.replace(/<[^>]+>/g, '').length;
                    this.setPreviewStatus('✅ 生成完成', 'done');
                    this.setPreviewMeta(charCount > 0 ? `约 ${charCount} 字` : '');
                    this.switchOutputTab('preview');

                    // 质量分析已禁用（避免干扰正文显示）
                    // this.showQualityAnalysis(content, latestArticle.title, latestArticle);
                }
            }
        } catch (error) {
            console.error('自动预览失败:', error);
        }
    }

    /**
     * 显示质量分析面板
     */
    showQualityAnalysis(content, title = '', articleInfo = null) {
        // 延迟显示，让用户先看到预览内容
        setTimeout(() => {
            if (window.qualityManager) {
                window.qualityManager.show(content, articleInfo);

                // 添加日志提示
                this.appendLog('📊 正在分析内容质量...', 'info', false, Date.now() / 1000);
            }
        }, 500);
    }

    appendLog(message, type = 'info', skipGlobal = false, timestamp = null) {
        // 过滤 internal 类型  
        if (type === 'internal') {
            const progressOnlyPattern = /^\[PROGRESS:\w+:(START|END)\]$/;
            if (progressOnlyPattern.test(message.trim())) {
                return;
            }

            if (message.includes('任务执行完成')) {
                return;
            }
        }

        // 【步骤2】过滤合并消息中的纯进度标记行  
        if (message.includes('\n')) {
            const lines = message.split('\n');
            const filteredLines = lines.filter(line => {
                const trimmedLine = line.trim();
                if (!trimmedLine) return false;
                const progressOnlyPattern = /^\[PROGRESS:\w+:(START|END)\]$/;
                const internalPattern = /^\[\d{2}:\d{2}:\d{2}\] \[INTERNAL\]: \[PROGRESS:\w+:(START|END)\]$/;
                return !progressOnlyPattern.test(trimmedLine) && !internalPattern.test(trimmedLine);
            });

            if (filteredLines.length === 0) {
                return;
            }

            // 【关键修改】将过滤后的行重新组合,移除空行  
            message = filteredLines.filter(line => line.trim()).join('\n');
        }

        // 添加到日志详情面板  
        const logsOutput = document.getElementById('logs-output');
        if (logsOutput) {
            const entry = document.createElement('div');
            entry.className = `log-entry ${type}`;

            // 检测时间戳  
            const hasTimestamp = /^\[\d{2}:\d{2}:\d{2}\]/.test(message);

            let finalMessage = message;
            if (!hasTimestamp && timestamp) {
                const time = new Date(timestamp * 1000);
                const timeStr = time.toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                });
                finalMessage = `[${timeStr}] ${message}`;
            }

            // 【关键修改】清理多余空格和多个连续换行符  
            const cleanedMessage = finalMessage
                .replace(/[ \t]+/g, ' ')  // 压缩空格和制表符  
                .replace(/\n{2,}/g, '\n')  // 将多个连续换行符压缩为单个  
                .trimEnd();  // 移除末尾空白  

            entry.innerHTML = `<span class="log-message">${this.escapeHtml(cleanedMessage)}</span>`;

            logsOutput.appendChild(entry);

            const logsContainer = logsOutput.parentElement;
            if (logsContainer) {
                logsContainer.scrollTop = logsContainer.scrollHeight;
            }
        }
    }

    // ========== 状态轮询 (v2: 智能降频) ==========  

    startStatusPolling() {
        this.stopStatusPolling();
        this._pollingStartTime = Date.now();
        this._lastPollTickTime = Date.now();

        // 防节流保活：使用 requestAnimationFrame 检测定时器是否被节流
        // 当页面在后台时，浏览器会节流 setTimeout/setInterval
        // 如果超过15秒没有轮询tick，主动进行一次状态查询
        this._startThrottleWatchdog();

        // v2: 使用动态间隔 - 前10秒高频(1s)确保快速响应，后续降频(3s)节省资源
        const pollOnce = async () => {
            if (!this.isGenerating) {
                this.stopStatusPolling();
                return;
            }

            this._lastPollTickTime = Date.now();

            try {
                const response = await fetch('/api/generate/status');
                if (response.ok) {
                    const result = await response.json();

                    if (result.status === 'completed' || result.status === 'failed' || result.status === 'stopped') {
                        this.stopStatusPolling();

                        this.handleGenerationComplete({
                            type: result.status,
                            error: result.error,
                            article_paths: result.article_paths,
                            ai_beautify: result.ai_beautify,
                        });

                        // 关闭 WebSocket  
                        this.disconnectLogWebSocket();
                    }
                }
            } catch (error) {
                console.error('轮询状态失败:', error);
            }

            // v2: 动态计算下次轮询间隔
            if (this.isGenerating) {
                const elapsed = Date.now() - this._pollingStartTime;
                const interval = elapsed < 10000 ? 1000 : 3000;
                this.statusPollInterval = setTimeout(pollOnce, interval);
            }
        };

        // 首次轮询延迟1秒启动
        this.statusPollInterval = setTimeout(pollOnce, 1000);
    }

    stopStatusPolling() {
        if (this.statusPollInterval) {
            clearTimeout(this.statusPollInterval); // v2: 改为clearTimeout匹配setTimeout
            this.statusPollInterval = null;
        }
        this._stopThrottleWatchdog();
    }

    /**
     * 防节流看门狗：使用 Web Worker 保持后台定时器不被节流
     * 当页面在后台时，浏览器会节流主线程的 setTimeout/setInterval
     * 但 Web Worker 中的定时器不受影响，可以持续发送心跳
     */
    _startThrottleWatchdog() {
        this._stopThrottleWatchdog();
        // 创建内联 Web Worker，避免额外文件
        const workerCode = `
            let timer = null;
            self.onmessage = function(e) {
                if (e.data === 'start') {
                    timer = setInterval(() => self.postMessage('tick'), 5000);
                } else if (e.data === 'stop') {
                    clearInterval(timer);
                    timer = null;
                }
            };
        `;
        const blob = new Blob([workerCode], { type: 'application/javascript' });
        this._watchdogWorker = new Worker(URL.createObjectURL(blob));
        this._watchdogWorker.onmessage = () => {
            if (!this.isGenerating) return;
            const elapsed = Date.now() - this._lastPollTickTime;
            if (elapsed > 15000) {
                // 定时器被节流超过15秒，主动查询状态
                console.warn(`[Watchdog] 检测到定时器节流（${Math.round(elapsed/1000)}秒无tick），主动查询状态`);
                fetch('/api/generate/status')
                    .then(r => r.ok ? r.json() : null)
                    .then(result => {
                        if (!result) return;
                        if (result.status === 'completed' || result.status === 'failed' || result.status === 'stopped') {
                            this.stopStatusPolling();
                            this.handleGenerationComplete({
                                type: result.status,
                                error: result.error,
                                article_paths: result.article_paths,
                                ai_beautify: result.ai_beautify,
                            });
                            this.disconnectLogWebSocket();
                            return;
                        }
                        // 更新tick时间，避免重复触发
                        this._lastPollTickTime = Date.now();
                    })
                    .catch(() => {});
            }
        };
        this._watchdogWorker.postMessage('start');
    }

    _stopThrottleWatchdog() {
        if (this._watchdogWorker) {
            this._watchdogWorker.postMessage('stop');
            this._watchdogWorker.terminate();
            this._watchdogWorker = null;
        }
    }

    _startPostGenerationRefresh() {
        this._stopPostGenerationRefresh();
        let refreshCount = 0;
        const maxRefreshCount = 12; // 最多刷新12次
        const interval = 10000; // 每10秒刷新一次，共2分钟
        this._postGenRefreshTimer = setInterval(async () => {
            refreshCount++;
            if (refreshCount >= maxRefreshCount) {
                this._stopPostGenerationRefresh();
                return;
            }
            try {
                if (window.articleManager) {
                    await window.articleManager.loadArticles();
                    window.articleManager.renderStatusTree();
                }
            } catch (e) { console.warn('生成后刷新文章列表失败:', e); }
        }, interval);
    }

    _stopPostGenerationRefresh() {
        if (this._postGenRefreshTimer) {
            clearInterval(this._postGenRefreshTimer);
            this._postGenRefreshTimer = null;
        }
    }

    // ========== 按钮状态管理 ==========  

    updateGenerationUI(isGenerating) {
        const generateBtn = document.getElementById('generate-btn');
        const topicInput = document.getElementById('topic-input');
        const referenceModeBtn = document.getElementById('reference-mode-btn');

        if (generateBtn) {
            const btnText = generateBtn.querySelector('span');
            if (btnText) {
                btnText.textContent = isGenerating ? '停止生成' : '开始生成';
            }

            // 切换按钮样式  
            if (isGenerating) {
                generateBtn.classList.remove('btn-generate');
                generateBtn.classList.add('btn-stop');
            } else {
                generateBtn.classList.remove('btn-stop');
                generateBtn.classList.add('btn-generate');
            }

            // 图标切换逻辑  
            const btnIcon = generateBtn.querySelector('svg.btn-icon') || generateBtn.querySelector('.btn-icon');
            if (btnIcon) {
                if (isGenerating) {
                    // 停止状态:显示等待微动画和停止图标
                    btnIcon.outerHTML = `  
                        <svg class="btn-icon" viewBox="0 0 24 24" style="animation: rotate 2s linear infinite;">  
                            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>  
                    `;
                } else {
                    // 开始状态:显示闪电图标  
                    btnIcon.outerHTML = `  
                        <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">  
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>  
                        </svg>  
                    `;
                }
            }
        }

        if (topicInput) {
            topicInput.disabled = isGenerating;
            topicInput.style.opacity = isGenerating ? '0.6' : '1';
            topicInput.style.cursor = isGenerating ? 'not-allowed' : 'text';
        }

        // 禁用/启用借鉴按钮  
        if (referenceModeBtn) {
            referenceModeBtn.disabled = isGenerating;
            referenceModeBtn.style.opacity = isGenerating ? '0.5' : '1';
            referenceModeBtn.style.cursor = isGenerating ? 'not-allowed' : 'pointer';

            this.setReferenceFormState(isGenerating);
        }
    }

    // 加载已有文章列表
    async loadArticleList() {
        try {
            const response = await fetch('/api/spider/articles?limit=100');
            if (response.ok) {
                const result = await response.json();
                const articles = result.articles || [];
                this.populateArticleSelect(articles);
            }
        } catch (error) {
            console.error('加载文章列表失败:', error);
        }
    }

    // 填充文章选择下拉框
    populateArticleSelect(articles) {
        const select = document.getElementById('reference-articles');
        if (!select) return;

        select.innerHTML = '<option value="">-- 选择抓取的热点文章 --</option>';

        articles.forEach(article => {
            const option = document.createElement('option');
            option.value = article.id;

            // 显示格式: [来源] 标题 (日期)
            const source = article.source || '热点';
            const title = article.title || `文章 ${article.id}`;
            const date = article.save_date ? article.save_date.slice(5) : ''; // 只取 MM-DD

            option.textContent = `[${source}] ${title} ${date ? '(' + date + ')' : ''}`;
            select.appendChild(option);
        });
    }

    // 加载选中的文章内容
    async loadSelectedArticle() {
        const select = document.getElementById('reference-articles');
        const articleId = select?.value;

        if (!articleId) {
            window.app?.showNotification('请先选择一篇热点文章', 'warning');
            return;
        }

        try {
            // 先尝试获取所有文章，然后找到对应ID的文章
            const response = await fetch('/api/spider/articles?limit=1000');
            if (response.ok) {
                const result = await response.json();
                const articles = result.articles || [];
                const article = articles.find(a => a.id == articleId);

                if (article) {
                    // 保存选中的文章信息
                    this._selectedArticle = article;

                    // 如果有外部链接则填入参考链接
                    const referenceUrls = document.getElementById('reference-urls');
                    if (article.article_url && referenceUrls) {
                        referenceUrls.value = article.article_url;
                    }

                    // 显示文章标题预览（不强制填入话题输入框）
                    const topicInput = document.getElementById('topic-input');
                    if (topicInput) {
                        // 如果话题输入框为空，则预填文章标题
                        if (!topicInput.value.trim()) {
                            topicInput.value = article.title;
                            this.currentTopic = article.title;
                        }
                    }

                    // 显示提示
                    const sourceInfo = article.source ? `(${article.source})` : '';
                    const dateInfo = article.save_date ? ` ${article.save_date}` : '';
                    window.app?.showNotification(`✅ 已加载热点文章${sourceInfo}: ${article.title}`, 'success');
                } else {
                    window.app?.showNotification('未找到该文章，请刷新重试', 'error');
                }
            } else {
                window.app?.showNotification('加载文章失败', 'error');
            }
        } catch (error) {
            console.error('加载文章失败:', error);
            window.app?.showNotification('加载文章失败: ' + error.message, 'error');
        }
    }

    // 删除被借鉴的文章（成功创作后调用）
    async deleteReferenceArticle(articleId) {
        if (!articleId) return;

        try {
            const response = await fetch(`/api/spider/articles/by-id/${articleId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    console.log('已删除被借鉴的文章:', articleId);
                    // 清空选中的文章
                    this._selectedArticle = null;
                    // 刷新文章列表
                    await this.loadArticleList();
                }
            }
        } catch (error) {
            console.error('删除被借鉴文章失败:', error);
        }
    }

    loadHistory() {
        const saved = localStorage.getItem('generation_history');
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed)) {
                    this.generationHistory = parsed;
                } else {
                    this.generationHistory = [];
                }
            } catch (e) {
                console.error('加载历史记录失败:', e);
                this.generationHistory = [];
            }
        }
    }

    addToHistory(topic) {
        if (!Array.isArray(this.generationHistory)) {
            this.generationHistory = [];
        }
        const entry = {
            topic: topic,
            timestamp: new Date().toISOString()
        };

        this.generationHistory.unshift(entry);

        if (this.generationHistory.length > 50) {
            this.generationHistory = this.generationHistory.slice(0, 50);
        }

        localStorage.setItem('generation_history', JSON.stringify(this.generationHistory));
    }

    initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Enter: 快速生成  
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                if (!this.isGenerating) {
                    this.startGeneration();
                }
            }

            // Ctrl/Cmd + K: 聚焦输入框  
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                document.getElementById('topic-input')?.focus();
            }

            // Esc: 停止生成  
            if (e.key === 'Escape' && this.isGenerating) {
                this.stopGeneration();
            }
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async exportLogs() {
        try {
            // 从后端获取日志文件  
            const response = await fetch('/api/logs/latest');
            if (!response.ok) {
                throw new Error('获取日志失败');
            }

            const blob = await response.blob();
            const filename = `generation_log_${new Date().toISOString().slice(0, 10)}.log`;

            // 使用 File System Access API 让用户选择保存位置  
            if ('showSaveFilePicker' in window) {
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{
                        description: '日志文件',
                        accept: { 'text/plain': ['.log'] },
                    }],
                });

                const writable = await handle.createWritable();
                await writable.write(blob);
                await writable.close();

                window.app?.showNotification('日志导出成功', 'success');
            } else {
                // 降级方案:使用传统下载方式  
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                window.app?.showNotification('日志已下载到默认下载目录', 'success');
            }
        } catch (error) {
            window.app?.showNotification('导出日志失败: ' + error.message, 'error');
        }
    }

    // ==================== 实时预览 ====================

    // ==================== 输出区 Tab ====================

    switchOutputTab(tab) {
        const isPreview = tab === 'preview';
        const previewPanel = document.getElementById('live-preview-panel');
        const logPanel = document.getElementById('generation-progress');
        const tabPreview = document.getElementById('tab-preview-btn');
        const tabLogs = document.getElementById('tab-logs-btn');
        const livePreviewBtn = document.getElementById('live-preview-btn');
        const logProgressBtn = document.getElementById('log-progress-btn');

        if (previewPanel) {
            previewPanel.classList.toggle('collapsed', !isPreview);
        }
        if (logPanel) {
            logPanel.classList.toggle('collapsed', isPreview);
        }
        tabPreview?.classList.toggle('is-active', isPreview);
        tabLogs?.classList.toggle('is-active', !isPreview);
        tabPreview?.setAttribute('aria-selected', isPreview ? 'true' : 'false');
        tabLogs?.setAttribute('aria-selected', !isPreview ? 'true' : 'false');
        livePreviewBtn?.classList.toggle('active', isPreview);
        logProgressBtn?.classList.toggle('active', !isPreview);
    }

    setPreviewStatus(text, state = 'idle') {
        const statusEl = document.getElementById('live-preview-status');
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.className = `live-preview-status status-${state}`;
    }

    setPreviewMeta(text) {
        const metaEl = document.getElementById('live-preview-meta');
        if (metaEl) {
            metaEl.textContent = text || '';
        }
    }

    openSidebarPreview() {
        const html = this.livePreviewContent
            || document.getElementById('live-preview-content')?.querySelector('.preview-article-body')?.innerHTML
            || '';
        if (!html || !html.trim()) {
            window.app?.showNotification('暂无内容可预览，请先生成文章', 'warning');
            return;
        }
        if (window.previewPanelManager) {
            window.previewPanelManager.setSize('desktop');
            window.previewPanelManager.show(html);
        }
    }

    // 切换实时预览面板
    toggleLivePreview() {
        const panel = document.getElementById('live-preview-panel');
        const logPanel = document.getElementById('generation-progress');
        const refPanel = document.getElementById('reference-mode-panel');

        if (panel?.classList.contains('collapsed')) {
            if (logPanel && !logPanel.classList.contains('collapsed')) {
                logPanel.classList.add('collapsed');
            }
            if (refPanel && !refPanel.classList.contains('collapsed')) {
                refPanel.classList.add('collapsed');
                document.getElementById('reference-mode-btn')?.classList.remove('active');
            }
            this.switchOutputTab('preview');
        } else {
            panel?.classList.add('collapsed');
            document.getElementById('live-preview-btn')?.classList.remove('active');
        }
    }

    // 从 WebSocket 消息中截取 AI 输出内容并实时渲染
    updateLivePreview(message, type) {
        // [新增] 处理 chunk 类型 (来自 Master Drafting 的内容块)
        if (type === 'chunk' || type === 'status') {
            if (!this.isCapturingContent) {
                this.isCapturingContent = true;
                this.livePreviewContent = '';
                // 自动打开预览面板
                const panel = document.getElementById('live-preview-panel');
                if (panel && panel.classList.contains('collapsed')) {
                    this.switchOutputTab('preview');
                }
                const contentEl = document.getElementById('live-preview-content');
                if (contentEl) {
                    contentEl.innerHTML = '';
                    this._liveChars = 0;
                }
            }
            if (message && message.trim()) {
                this._processAndRenderChunk(message);
            }
            return;
        }

        // 检测内容捕获边界
        if (message.includes('[PROGRESS:WRITING:START]')) {
            this.isCapturingContent = true;
            this.livePreviewContent = '';
            // 自动打开预览面板
            const panel = document.getElementById('live-preview-panel');
            if (panel && panel.classList.contains('collapsed')) {
                this.switchOutputTab('preview');
            }
            // 更新状态
            const statusEl = document.getElementById('live-preview-status');
            if (statusEl) {
                this.setPreviewStatus('✍️ AI 写作中...', 'writing');
            }
            // 清空旧内容，插入 V3 Skeleton 占位动画
            const contentEl = document.getElementById('live-preview-content');
            if (contentEl) {
                contentEl.innerHTML = `
                    <div class="skeleton-wrapper" style="padding: 20px;">
                        <div class="skeleton-title" style="width: 60%; height: 28px; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; border-radius: 4px; margin-bottom: 24px; animation: skeleton-loading 1.5s infinite;"></div>
                        <div class="skeleton-line" style="width: 100%; height: 16px; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; border-radius: 4px; margin-bottom: 12px; animation: skeleton-loading 1.5s infinite;"></div>
                        <div class="skeleton-line" style="width: 90%; height: 16px; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; border-radius: 4px; margin-bottom: 12px; animation: skeleton-loading 1.5s infinite;"></div>
                        <div class="skeleton-line" style="width: 95%; height: 16px; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; border-radius: 4px; margin-bottom: 12px; animation: skeleton-loading 1.5s infinite;"></div>
                        <div class="skeleton-line" style="width: 70%; height: 16px; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; border-radius: 4px; margin-bottom: 24px; animation: skeleton-loading 1.5s infinite;"></div>
                    </div>
                    <style>
                        @keyframes skeleton-loading {
                            0% { background-position: 200% 0; }
                            100% { background-position: -200% 0; }
                        }
                        [data-theme='dark'] .skeleton-title, [data-theme='dark'] .skeleton-line {
                            background: linear-gradient(90deg, #2a2f3d 25%, #3a4154 50%, #2a2f3d 75%) !important;
                            background-size: 200% 100% !important;
                        }
                    </style>
                `;
                this._liveChars = 0;
            }
            return;
        }

        if (message.includes('[PROGRESS:WRITING:END]') ||
            message.includes('[PROGRESS:REVIEW:START]') ||
            message.includes('[PROGRESS:VISUAL:START]')) {
            // 注意：视觉集成时可能也会发 chunk，所以这里不强制关闭 isCapturingContent
            // 只是更新个状态
            const statusEl = document.getElementById('live-preview-status');
            if (statusEl) {
                if (message.includes('REVIEW')) {
                    this.setPreviewStatus('👁️ 终审打磨中...', 'writing');
                } else if (message.includes('VISUAL')) {
                    this.setPreviewStatus('🖼️ 视觉集成中...', 'writing');
                } else {
                    this.setPreviewStatus('⏳ 处理中...', 'writing');
                }
            }
            return;
        }

        // 生成完成标记
        if (message.includes('任务执行完成') || type === 'completed' || message.includes('[PROGRESS:COMPLETE:START]')) {
            this.isCapturingContent = false;
            this.setPreviewStatus('✅ 生成完成', 'done');
            return;
        }

        if (type === 'failed') {
            this.isCapturingContent = false;
            this.setPreviewStatus('❌ 生成失败', 'error');
            return;
        }

        // 只在写作阶段捕获内容
        if (!this.isCapturingContent) return;

        // 过滤掉非内容消息
        if (message.includes('[PROGRESS:') || message.includes('[INTERNAL]') ||
            type === 'internal' || type === 'system') return;

        // 过滤时间戳前缀的系统消息
        let cleaned = message.trim();
        // 移除 [HH:MM:SS] 前缀
        cleaned = cleaned.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, '');
        // 移除 [INFO]:, [DEBUG]: 等日志前缀
        cleaned = cleaned.replace(/^\[.*?\]\s*:?\s*/, '').trim();

        if (!cleaned || cleaned.length < 2) return;

        // 过滤明显不是文章正文的系统提示词或CrewAI特定的中间输出
        const skipPatterns = [
            /^AI生成/, /^开始/, /^调用/, /^正在/, /^INFO:/, /^WARNING:/, /^ERROR:/, /^DEBUG:/,
            /^\> Entering new/, /^Thought:/, /^Action:/, /^Action Input:/, /^Observation:/,
            /^Finished chain/, /^Working on task/, /^Starting task/, /== Working Agent:/,
            /\[.*\]/ // 匹配只包含在括号内的行（通常是日志提示）
        ];

        for (const pattern of skipPatterns) {
            if (pattern.test(cleaned)) return;
        }

        // [新增] 智能全量内容替换检测（如果接收到的是已经排版过的大段HTML，则直接覆盖）
        if (cleaned.includes('<div') || cleaned.includes('<p')) {
            this.livePreviewContent = cleaned;
        } else {
            // 普通文本增量追加
            this.livePreviewContent += cleaned + '\n';
        }

        this._liveChars = this.livePreviewContent.replace(/<[^>]+>/g, '').length;

        this.setPreviewStatus(`✍️ 写作中 · ${this._liveChars} 字`, 'writing');
        this.setPreviewMeta(this._liveChars > 0 ? `约 ${this._liveChars} 字` : '');

        const contentEl = document.getElementById('live-preview-content');
        if (contentEl) {
            if (this.livePreviewContent.includes('<')) {
                contentEl.innerHTML = `<div class="preview-article-body">${this.livePreviewContent}</div>`;
            } else {
                const formatted = this.livePreviewContent
                    .replace(/^#{1,3}\s+(.+)$/gm, '<h3>$1</h3>')
                    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\*(.+?)\*/g, '<em>$1</em>')
                    .replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>')
                    .replace(/\n\n+/g, '</p><p>')
                    .replace(/\n/g, '<br>');
                contentEl.innerHTML = `<div class="preview-article-body"><p>${formatted}</p></div>`;
            }

            contentEl.scrollTop = contentEl.scrollHeight;
        }

        this._syncFloatingPreviewIfOpen();
    }

    /** 若用户已打开侧栏预览，同步写入（内容生成默认不自动弹出侧栏） */
    _syncFloatingPreviewIfOpen() {
        if (window.previewPanelManager?.isVisible && this.livePreviewContent) {
            window.previewPanelManager.setContent(this.livePreviewContent);
        }
    }

    _processAndRenderChunk(message) {
        if (!message?.trim()) return;
        this.livePreviewContent += message;
        this._liveChars = this.livePreviewContent.replace(/<[^>]+>/g, '').length;
        this.setPreviewStatus(`✍️ 写作中 · ${this._liveChars} 字`, 'writing');
        this.setPreviewMeta(this._liveChars > 0 ? `约 ${this._liveChars} 字` : '');

        const contentEl = document.getElementById('live-preview-content');
        if (!contentEl) return;

        const formatted = this.livePreviewContent
            .replace(/^#{1,3}\s+(.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>')
            .replace(/\n\n+/g, '</p><p>')
            .replace(/\n/g, '<br>');
        contentEl.innerHTML = `<div class="preview-article-body"><p>${formatted}</p></div>`;
        contentEl.scrollTop = contentEl.scrollHeight;
        this._syncFloatingPreviewIfOpen();
    }
}
