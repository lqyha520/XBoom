/**
 * 内容质量检测管理器
 * 处理内容分析、优化建议、自动优化等功能
 */

class QualityManager {
    constructor() {
        this.panelVisible = false;
        this.currentContent = '';
        this.optimizedContent = '';
        this.currentArticleInfo = null;
        this.currentAnalysis = null;
        this.isOptimizing = false;
        this.selectedSuggestions = new Set(); // 选中的优化建议
        this.currentSuggestions = []; // 当前所有建议

        this.metricsInfo = {
            originality: { name: '原创性', icon: '⭐', weight: 0.20 },
            readability: { name: '可读性', icon: '📖', weight: 0.15 },
            coherence: { name: '连贯性', icon: '🔗', weight: 0.15 },
            vocabulary: { name: '词汇丰富度', icon: '📚', weight: 0.10 },
            sentence_variety: { name: '句式多样性', icon: '📝', weight: 0.10 },
            ai_likelihood: { name: 'AI检测概率', icon: '🤖', weight: 0.20, inverse: true },
            semantic_depth: { name: '语义深度', icon: '💡', weight: 0.10 },
            emotional_polarity: { name: '情感共鸣', icon: '🎭', weight: 0.05 },
            hook_cta: { name: '黄金开头', icon: '🪝', weight: 0.05 },
            topic_transition: { name: '内容衔接', icon: '🛤️', weight: 0.05 }
        };

        this.init();
    }

    notify(message, type = 'info') {
        if (window.app?.showNotification) {
            window.app.showNotification(message, type);
        } else {
            console.log(`[Quality][${type}] ${message}`);
        }
    }

    init() {
        this.createPanel();
        this.bindEvents();
    }

    createPanel() {
        // 面板已经通过HTML模板加载
        this.panel = document.getElementById('quality-panel');
        if (!this.panel) {
            console.warn('Quality panel not found');
        }
    }

    bindEvents() {
        // 关闭按钮
        const closeBtn = document.getElementById('close-quality-panel');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }

        // 自动优化按钮
        const optimizeBtn = document.getElementById('btn-auto-optimize');
        if (optimizeBtn) {
            optimizeBtn.addEventListener('click', () => this.startAutoOptimize());
        }

        // 对比按钮
        const compareBtn = document.getElementById('btn-compare');
        if (compareBtn) {
            compareBtn.addEventListener('click', () => this.showComparison());
        }

        // 应用优化结果按钮
        const applyBtn = document.getElementById('btn-apply-optimized');
        if (applyBtn) {
            applyBtn.addEventListener('click', () => this.applyOptimized());
        }

        const cleanLeaksBtn = document.getElementById('btn-clean-visual-leaks');
        if (cleanLeaksBtn) {
            cleanLeaksBtn.addEventListener('click', () => this.cleanVisualLeaksFromPanel());
        }

        // 建议区按钮（事件委托，避免 innerHTML 后丢失绑定）
        if (this.panel) {
            this.panel.addEventListener('click', (e) => {
                const selectAllBtn = e.target.closest('#btn-select-all-suggestions');
                const optimizeBtn = e.target.closest('#btn-optimize-selected');
                if (selectAllBtn) {
                    e.preventDefault();
                    this.toggleSelectAll();
                }
                if (optimizeBtn && !optimizeBtn.disabled) {
                    e.preventDefault();
                    this.optimizeSelected();
                }
            });
        }
    }

    show(content = '', articleInfo = null) {
        this.currentContent = content;
        this.currentArticleInfo = articleInfo
            || window.previewPanelManager?.currentArticleInfo
            || null;
        this.panelVisible = true;

        if (this.panel) {
            this.panel.style.display = 'flex';
        }

        const hint = document.getElementById('quality-empty-hint');
        if (hint) {
            hint.style.display = content ? 'none' : 'block';
        }

        if (content) {
            this.analyzeContent(content);
        } else {
            this.notify('请先在预览中加载文章内容，或从生成完成页打开质量检测', 'warning');
        }
    }

    hide() {
        this.panelVisible = false;
        if (this.panel) {
            this.panel.style.display = 'none';
        }
    }

    toggle(content = '') {
        if (this.panelVisible) {
            this.hide();
        } else {
            this.show(content);
        }
    }

    async analyzeContent(content) {
        if (!content) return;

        this.currentContent = content;

        // 显示加载状态
        this.updateScoreDisplay('--', 0);
        document.getElementById('ai-risk-value').textContent = '分析中...';
        document.getElementById('originality-value').textContent = '分析中...';

        try {
            const response = await fetch('/api/quality/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });

            const result = await response.json();

            if (result.status === 'success') {
                this.currentAnalysis = result.data;
                this.updateDisplay(result.data);
            } else {
                throw new Error(result.message || '分析失败');
            }
        } catch (error) {
            console.error('Content analysis failed:', error);
            this.showError('内容分析失败: ' + error.message);
        }
    }

    updateDisplay(data) {
        // 更新综合评分
        this.updateScoreDisplay(data.overall_score, data.overall_score);

        // 更新AI检测概率
        const aiRisk = data.ai_detection_score;
        const aiRiskEl = document.getElementById('ai-risk-value');
        const aiStatusEl = document.getElementById('ai-risk-status');

        aiRiskEl.textContent = aiRisk.toFixed(1) + '%';

        if (aiRisk <= 30) {
            aiStatusEl.textContent = '安全';
            aiStatusEl.className = 'metric-status good';
        } else if (aiRisk <= 50) {
            aiStatusEl.textContent = '警告';
            aiStatusEl.className = 'metric-status warning';
        } else {
            aiStatusEl.textContent = '危险';
            aiStatusEl.className = 'metric-status danger';
        }

        // 更新原创性
        const originality = data.originality_score;
        const origEl = document.getElementById('originality-value');
        const origStatusEl = document.getElementById('originality-status');

        origEl.textContent = originality.toFixed(1);

        if (originality >= 75) {
            origStatusEl.textContent = '优秀';
            origStatusEl.className = 'metric-status good';
        } else if (originality >= 60) {
            origStatusEl.textContent = '一般';
            origStatusEl.className = 'metric-status warning';
        } else {
            origStatusEl.textContent = '较低';
            origStatusEl.className = 'metric-status danger';
        }

        // 更新详细指标
        this.updateMetricsGrid(data.quality_scores);

        // 更新优化建议
        this.updateSuggestions(data.suggestions);
    }

    updateScoreDisplay(score, percentage) {
        const scoreValue = document.getElementById('overall-score-value');
        const progressRing = document.getElementById('score-progress-ring');

        scoreValue.textContent = score.toFixed ? score.toFixed(1) : score;

        // 更新圆环进度
        const circumference = 283; // 2 * PI * 45
        const offset = circumference - (percentage / 100) * circumference;
        progressRing.style.strokeDashoffset = offset;

        // 根据分数改变颜色
        if (percentage >= 80) {
            progressRing.style.stroke = '#22c55e';
        } else if (percentage >= 60) {
            progressRing.style.stroke = '#eab308';
        } else {
            progressRing.style.stroke = '#ef4444';
        }
    }

    updateMetricsGrid(scores) {
        const grid = document.getElementById('metrics-grid');
        if (!grid) return;

        grid.innerHTML = '';

        for (const [key, data] of Object.entries(scores)) {
            const info = this.metricsInfo[key] || { name: key, icon: '📊' };
            // 确保分数有效，默认0
            const score = (data && typeof data.score === 'number') ? data.score : 0;
            const isInverse = info.inverse;

            // 特殊处理情感极性显示
            let displayValue = score;
            let displaySuffix = '';
            if (key === 'emotional_polarity') {
                displaySuffix = ' / 100';
            }

            // 对于AI检测概率，分数越低越好
            const displayPercentage = isInverse ? (100 - score) : score;
            const barColor = this.getScoreColor(isInverse ? score : displayPercentage, isInverse);

            const item = document.createElement('div');
            item.className = 'metric-item';
            item.innerHTML = `
                <div class="metric-item-header">
                    <span class="metric-item-name">${info.icon} ${info.name}</span>
                    <span class="metric-item-value">${score.toFixed(1)}${displaySuffix}</span>
                </div>
                <div class="metric-item-bar">
                    <div class="metric-item-bar-fill" style="width: ${score}%; background: ${barColor}"></div>
                </div>
            `;

            grid.appendChild(item);
        }
    }

    getScoreColor(score, isInverse = false) {
        if (isInverse) {
            // AI检测概率：越低越好
            if (score <= 30) return '#22c55e';
            if (score <= 50) return '#eab308';
            return '#ef4444';
        } else {
            // 其他指标：越高越好
            if (score >= 75) return '#22c55e';
            if (score >= 50) return '#eab308';
            return '#ef4444';
        }
    }

    updateSuggestions(suggestions) {
        const list = document.getElementById('suggestions-list');
        if (!list) return;

        list.innerHTML = '';
        this.currentSuggestions = suggestions || [];
        this.selectedSuggestions.clear();

        if (!suggestions || suggestions.length === 0) {
            list.innerHTML = '<div class="suggestion-item">✅ 内容质量良好，暂无优化建议</div>';
            this.updateOptimizeButton();
            return;
        }

        const actionBar = document.createElement('div');
        actionBar.className = 'suggestion-action-bar suggestion-action-bar-sticky';
        actionBar.innerHTML = `
            <button type="button" class="suggestion-btn-select-all" id="btn-select-all-suggestions">
                <span>☑️</span> 全选
            </button>
            <button type="button" class="suggestion-btn-optimize" id="btn-optimize-selected" disabled>
                <span>✨</span> 一键改写选中
            </button>
        `;
        list.appendChild(actionBar);

        suggestions.forEach((suggestion, index) => {
            const item = document.createElement('div');
            item.className = 'suggestion-item selectable';
            item.dataset.index = index;

            const isPriority = suggestion.includes('【优先】');
            const cleanSuggestion = suggestion.replace('【优先】', '');

            item.innerHTML = `
                <label class="suggestion-checkbox">
                    <input type="checkbox" data-index="${index}">
                    <span class="checkmark"></span>
                </label>
                <span class="suggestion-icon">${isPriority ? '⚠️' : '💡'}</span>
                <span class="suggestion-text">${cleanSuggestion}</span>
            `;

            if (isPriority) {
                item.classList.add('priority');
            }

            const checkbox = item.querySelector('input[type="checkbox"]');
            checkbox.addEventListener('click', (e) => e.stopPropagation());
            checkbox.addEventListener('change', (e) => {
                this.toggleSuggestion(index, e.target.checked);
            });

            item.addEventListener('click', (e) => {
                if (e.target.closest('label') || e.target.type === 'checkbox') return;
                checkbox.checked = !checkbox.checked;
                this.toggleSuggestion(index, checkbox.checked);
            });

            list.appendChild(item);
        });

        this.updateOptimizeButton();
    }

    toggleSuggestion(index, isSelected) {
        if (isSelected) {
            this.selectedSuggestions.add(index);
        } else {
            this.selectedSuggestions.delete(index);
        }

        // 更新UI
        const item = document.querySelector(`.suggestion-item[data-index="${index}"]`);
        if (item) {
            item.classList.toggle('selected', isSelected);
        }

        this.updateOptimizeButton();
    }

    toggleSelectAll() {
        const allChecked = this.selectedSuggestions.size === this.currentSuggestions.length;
        const checkboxes = document.querySelectorAll('.suggestion-item input[type="checkbox"]');

        if (allChecked) {
            // 取消全选
            this.selectedSuggestions.clear();
            checkboxes.forEach(cb => cb.checked = false);
            document.querySelectorAll('.suggestion-item.selectable').forEach(item => {
                item.classList.remove('selected');
            });
        } else {
            // 全选
            this.currentSuggestions.forEach((_, index) => {
                this.selectedSuggestions.add(index);
            });
            checkboxes.forEach(cb => cb.checked = true);
            document.querySelectorAll('.suggestion-item.selectable').forEach(item => {
                item.classList.add('selected');
            });
        }

        this.updateOptimizeButton();
    }

    updateOptimizeButton() {
        const btn = document.getElementById('btn-optimize-selected');
        if (btn) {
            const count = this.selectedSuggestions.size;
            btn.innerHTML = count > 0
                ? `<span>✨</span> 一键改写选中 (${count})`
                : `<span>✨</span> 一键改写选中`;
            btn.disabled = count === 0 || this.isOptimizing;
            btn.classList.toggle('is-loading', this.isOptimizing);
        }
    }

    async optimizeSelected() {
        if (this.isOptimizing) return;

        if (!this.currentContent || !this.currentContent.trim()) {
            this.notify('没有可优化的正文，请先生成或粘贴内容', 'warning');
            return;
        }

        if (this.selectedSuggestions.size === 0) {
            this.notify('请先勾选要执行的优化建议', 'warning');
            return;
        }

        this.isOptimizing = true;
        this.updateOptimizeButton();

        const selectedTexts = Array.from(this.selectedSuggestions).map(idx => {
            let text = this.currentSuggestions[idx];
            return text.replace('【优先】', '').trim();
        });

        this.notify(`正在根据 ${selectedTexts.length} 条建议改写，请稍候…`, 'info');

        try {
            // 调用AI优化API，添加超时控制
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 120000); // 2分钟超时

            console.log('[Quality] 发送请求到 /api/quality/optimize-with-suggestions');

            const response = await fetch('/api/quality/optimize-with-suggestions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content: this.currentContent,
                    suggestions: selectedTexts,
                    mode: 'agent'
                }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            console.log('[Quality] 收到响应:', response.status);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const result = await response.json();
            console.log('[Quality] 响应结果:', result);

            if (result.status === 'success' && result.data) {
                this.optimizedContent = result.data.optimized_content;

                // 显示优化结果
                this.showOptimizationResult(
                    this.currentContent,
                    this.optimizedContent,
                    result.data.changes || selectedTexts
                );

                this.notify('改写完成，请查看对比结果', 'success');
            } else {
                throw new Error(result.detail || result.message || '优化失败');
            }
        } catch (error) {
            console.error('[Quality] 优化失败:', error);
            if (error.name === 'AbortError') {
                this.notify('改写超时，请稍后重试', 'error');
            } else {
                let msg = error.message || '未知错误';
                try {
                    const errJson = JSON.parse(msg.replace(/^HTTP \d+: /, ''));
                    msg = errJson.detail || msg;
                } catch (_) { /* keep msg */ }
                this.notify('改写失败: ' + msg, 'error');
            }
        } finally {
            this.isOptimizing = false;
            this.updateOptimizeButton();
        }
    }

    showOptimizationResult(original, optimized, changes) {
        // 创建对比弹窗
        const modal = document.createElement('div');
        modal.className = 'optimization-result-modal';
        modal.innerHTML = `
            <div class="optimization-result-overlay">
                <div class="optimization-result-content">
                    <div class="result-header">
                        <h3>✨ AI智能优化结果</h3>
                        <button class="close-btn">&times;</button>
                    </div>
                    <div class="result-body">
                        <div class="changes-list">
                            <h4>优化项：</h4>
                            <ul>
                                ${changes.map(c => `<li>✓ ${c}</li>`).join('')}
                            </ul>
                        </div>
                        <div class="diff-view">
                            <div class="diff-section markdown-body" style="overflow-y: auto; max-height: 400px; padding: 10px; border: 1px solid #ddd; background: var(--bg-secondary);">
                                <h4>原文</h4>
                                <div class="diff-content original">${window.marked && window.marked.parse ? window.marked.parse(original) : original}</div>
                            </div>
                            <div class="diff-arrow" style="align-self: center; font-size: 24px; padding: 0 10px;">➜</div>
                            <div class="diff-section markdown-body" style="overflow-y: auto; max-height: 400px; padding: 10px; border: 1px solid #ddd; background: var(--bg-secondary);">
                                <h4>优化后</h4>
                                <div class="diff-content optimized">${window.marked && window.marked.parse ? window.marked.parse(optimized) : optimized}</div>
                            </div>
                        </div>
                    </div>
                    <div class="result-footer">
                        <button class="btn-cancel">取消</button>
                        <button class="btn-apply">应用优化</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // 绑定事件
        modal.querySelector('.close-btn').addEventListener('click', () => modal.remove());
        modal.querySelector('.btn-cancel').addEventListener('click', () => modal.remove());
        modal.querySelector('.btn-apply').addEventListener('click', () => {
            this.optimizedContent = optimized;
            this.applyOptimized();
            modal.remove();
        });

        // 点击遮罩关闭
        modal.querySelector('.optimization-result-overlay').addEventListener('click', (e) => {
            if (e.target === modal.querySelector('.optimization-result-overlay')) {
                modal.remove();
            }
        });
    }

    async startAutoOptimize() {
        if (this.isOptimizing || !this.currentContent) {
            if (!this.currentContent) {
                this.notify('没有可优化的正文', 'warning');
            }
            return;
        }

        this.isOptimizing = true;

        // 显示优化进度
        const progressEl = document.getElementById('optimization-progress');
        progressEl.style.display = 'block';

        // 禁用按钮
        document.getElementById('btn-auto-optimize').disabled = true;

        try {
            // 获取优化计划
            const planResponse = await fetch('/api/quality/auto-optimize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content: this.currentContent,
                    target_originality: 75.0,
                    max_ai_likelihood: 30.0,
                    max_iterations: 5
                })
            });

            const planResult = await planResponse.json();

            if (planResult.status === 'success') {
                const data = planResult.data;

                if (!data.needs_optimization) {
                    this.updateProgressStatus('✅ 内容已达标，无需优化');
                    this.isOptimizing = false;
                    document.getElementById('btn-auto-optimize').disabled = false;
                    return;
                }

                // 更新初始分数
                this.updateProgressBar('overall', data.current_scores.overall);
                this.updateProgressBar('originality', data.current_scores.originality);
                this.updateProgressBar('ai', data.current_scores.ai_likelihood, true);

                // 生成优化后的内容（通过AI）
                this.updateProgressStatus('🔄 正在生成优化内容...');

                const optimizedContent = await this.generateOptimizedContent(
                    this.currentContent,
                    data.suggestions
                );

                if (optimizedContent) {
                    this.optimizedContent = optimizedContent;

                    // 分析优化后的内容
                    this.updateProgressStatus('🔍 正在分析优化结果...');
                    const analysisResult = await this.analyzeContentAsync(optimizedContent);

                    if (analysisResult) {
                        // 更新进度
                        this.updateProgressBar('overall', analysisResult.overall_score);
                        this.updateProgressBar('originality', analysisResult.originality_score);
                        this.updateProgressBar('ai', analysisResult.ai_detection_score, true);

                        // 显示对比按钮和应用按钮
                        document.getElementById('btn-compare').style.display = 'flex';
                        document.getElementById('btn-apply-optimized').style.display = 'flex';

                        // 更新显示
                        this.currentAnalysis = analysisResult;
                        this.updateDisplay(analysisResult);

                        this.updateProgressStatus('✅ 优化完成！');
                    }
                }
            }
        } catch (error) {
            console.error('Auto optimize failed:', error);
            this.updateProgressStatus('❌ 优化失败: ' + error.message);
            this.notify('自动优化失败: ' + error.message, 'error');
        } finally {
            this.isOptimizing = false;
            document.getElementById('btn-auto-optimize').disabled = false;
        }
    }

    async generateOptimizedContent(content, suggestions) {
        // 调用AI生成优化内容
        try {
            const response = await fetch('/api/generate/optimize-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content: content,
                    suggestions: suggestions,
                    optimize_type: 'quality'
                })
            });

            const result = await response.json();

            if (result.status === 'success') {
                return result.data.content;
            } else {
                throw new Error(result.message || '生成优化内容失败');
            }
        } catch (error) {
            console.error('Generate optimized content failed:', error);
            // 如果API不存在，返回模拟的优化内容
            return this.simulateOptimization(content, suggestions);
        }
    }

    simulateOptimization(content, suggestions) {
        // 简单的模拟优化
        let optimized = content;

        // 替换一些AI常用表达
        const replacements = {
            '首先，': '第一，',
            '其次，': '第二，',
            '最后，': '另外，',
            '总而言之': '总之',
            '综上所述': '整体来看',
            '不可否认': '确实',
            '毋庸置疑': '毫无疑问',
            '显而易见': '很明显',
            '众所周知': '大家都知道',
            '在当今社会': '现在',
            '随着科技的发展': '科技发展',
            '值得一提的是': '值得注意的是',
            '让我们来看看': '来看看',
            '接下来我们将讨论': '下面讨论',
        };

        for (const [from, to] of Object.entries(replacements)) {
            optimized = optimized.split(from).join(to);
        }

        return optimized;
    }

    async analyzeContentAsync(content) {
        try {
            const response = await fetch('/api/quality/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });

            const result = await response.json();
            return result.status === 'success' ? result.data : null;
        } catch (error) {
            console.error('Analyze content failed:', error);
            return null;
        }
    }

    updateProgressBar(type, value, isAi = false) {
        const bar = document.getElementById(`progress-${type}`);
        const valueEl = document.getElementById(`progress-${type}-value`);

        if (bar) {
            bar.style.width = value + '%';
            if (isAi) {
                bar.style.background = value <= 30 ? '#22c55e' : value <= 50 ? '#eab308' : '#ef4444';
            }
        }

        if (valueEl) {
            valueEl.textContent = value.toFixed(1);
        }
    }

    updateProgressStatus(message) {
        const statusEl = document.getElementById('progress-status');
        if (statusEl) {
            if (message.includes('✅') || message.includes('❌')) {
                statusEl.innerHTML = `<span>${message}</span>`;
            } else {
                statusEl.innerHTML = `
                    <div class="status-spinner"></div>
                    <span>${message}</span>
                `;
            }
        }
    }

    async showComparison() {
        if (!this.currentContent || !this.optimizedContent) return;

        try {
            const response = await fetch('/api/quality/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    original: this.currentContent,
                    optimized: this.optimizedContent
                })
            });

            const result = await response.json();

            if (result.status === 'success') {
                this.renderComparison(result.data);
                document.getElementById('comparison-view').style.display = 'block';
            }
        } catch (error) {
            console.error('Comparison failed:', error);
        }
    }

    renderComparison(data) {
        const originalScores = document.getElementById('original-scores');
        const optimizedScores = document.getElementById('optimized-scores');
        const summary = document.getElementById('improvement-summary');

        if (!originalScores || !optimizedScores) return;

        // 渲染原始分数
        originalScores.innerHTML = this.renderComparisonScores(
            data.original_analysis,
            false
        );

        // 渲染优化后分数
        optimizedScores.innerHTML = this.renderComparisonScores(
            data.optimized_analysis,
            true,
            data.improvements
        );

        // 渲染改进摘要
        summary.innerHTML = `
            <div class="improvement-item">
                <div class="improvement-value">+${data.overall_improvement}</div>
                <div class="improvement-label">综合提升</div>
            </div>
            <div class="improvement-item">
                <div class="improvement-value">${data.similarity}%</div>
                <div class="improvement-label">内容相似度</div>
            </div>
        `;
    }

    renderComparisonScores(analysis, isOptimized, improvements = {}) {
        const scores = [
            { key: 'overall', label: '综合评分', value: analysis.overall_score },
            { key: 'originality', label: '原创性', value: analysis.originality_score },
            { key: 'ai', label: 'AI概率', value: analysis.ai_detection_score },
        ];

        return scores.map(score => {
            const improvement = improvements[score.key];
            const improvementText = isOptimized && improvement ?
                `<span style="color: ${improvement.improvement > 0 ? '#22c55e' : '#ef4444'}">
                    ${improvement.improvement > 0 ? '+' : ''}${improvement.improvement}
                </span>` : '';

            return `
                <div class="comparison-score-item">
                    <span class="comparison-score-name">${score.label}</span>
                    <span class="comparison-score-value ${isOptimized && improvement?.improvement > 0 ? 'improved' : ''}">
                        ${score.value.toFixed(1)} ${improvementText}
                    </span>
                </div>
            `;
        }).join('');
    }

    async cleanVisualLeaksFromPanel() {
        const articlePath = this.currentArticleInfo?.path;
        if (!articlePath) {
            this.notify('请从文章库打开文章后再清理（需关联文章文件）', 'warning');
            return;
        }
        try {
            const res = await fetch('/api/articles/clean-visual-leaks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: articlePath }),
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || data.message || `HTTP ${res.status}`);
            }
            if (data.changed) {
                const contentRes = await fetch(
                    `/api/articles/content?path=${encodeURIComponent(articlePath)}`
                );
                const html = await contentRes.text();
                this.currentContent = html;
                if (window.previewPanelManager) {
                    window.previewPanelManager.setContent(html);
                    if (window.previewPanelManager.isVisible) {
                        window.previewPanelManager.show(html);
                    }
                }
            }
            this.notify(data.message || '清理完成', 'success');
        } catch (e) {
            this.notify('清理失败: ' + e.message, 'error');
        }
    }

    async mergePreserveImages(original, optimized) {
        if (!original || !optimized || !/<img/i.test(original)) {
            return optimized;
        }
        try {
            const res = await fetch('/api/articles/merge-optimized', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ original, optimized }),
            });
            const data = await res.json();
            if (res.ok && data.status === 'success' && data.data?.content) {
                return data.data.content;
            }
        } catch (e) {
            console.warn('[Quality] 合并配图失败，使用优化结果原文:', e);
        }
        return optimized;
    }

    async applyOptimized() {
        if (!this.optimizedContent) {
            this.notify('没有可应用的优化结果', 'warning');
            return;
        }

        let content = this.optimizedContent;
        if (this.currentContent && /<img/i.test(this.currentContent)) {
            content = await this.mergePreserveImages(this.currentContent, content);
            this.optimizedContent = content;
        }

        // 1. 同步到预览面板 / 创意工坊实时预览
        if (window.previewPanelManager) {
            window.previewPanelManager.setContent(content);
            if (window.previewPanelManager.isVisible) {
                window.previewPanelManager.show(content);
            }
        }
        const livePreview = document.getElementById('live-preview-content');
        if (livePreview) {
            if (content.trim().startsWith('<')) {
                livePreview.innerHTML = content;
            } else if (window.marked?.parse) {
                livePreview.innerHTML = window.marked.parse(content);
            } else {
                livePreview.textContent = content;
            }
        }

        // 2. 写入磁盘（有文章路径时）
        const articlePath = this.currentArticleInfo?.path;
        if (articlePath) {
            try {
                const res = await fetch(
                    `/api/articles/content?path=${encodeURIComponent(articlePath)}`,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content }),
                    }
                );
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `HTTP ${res.status}`);
                }
            } catch (e) {
                console.error('[Quality] 保存优化结果失败:', e);
                this.notify('应用失败：无法保存到文章文件 - ' + e.message, 'error');
                return;
            }
        }

        // 3. 通知内容编辑器（若已打开）
        document.dispatchEvent(new CustomEvent('quality:apply-optimized', {
            detail: { content, path: articlePath || null },
        }));

        this.currentContent = content;
        this.analyzeContent(content);

        const keptImages = this.currentContent && /<img/i.test(this.currentContent);
        const msg = articlePath
            ? (keptImages
                ? '已应用优化结果并保存到文章（已保留原有配图）'
                : '已应用优化结果并保存到文章')
            : '已应用优化结果到预览（未关联文章文件，请从文章库打开后再优化以便自动保存）';
        this.notify(msg, 'success');
    }

    showError(message) {
        const list = document.getElementById('suggestions-list');
        if (list) {
            list.innerHTML = `<div class="suggestion-item" style="color: #ef4444;">❌ ${message}</div>`;
        }
    }
}

// 创建全局实例
let qualityManager = null;

document.addEventListener('DOMContentLoaded', () => {
    qualityManager = new QualityManager();
    window.qualityManager = qualityManager;
});
