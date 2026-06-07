class AIWriteXConfigManager {
    constructor() {
        // 维度分组定义  
        this.DIMENSION_GROUPS = {
            expression: {
                name: '文体表达',
                emoji: '✍️',
                dimensions: ['style', 'language', 'tone'],
                description: '文体、语言与语调'
            },
            culture: {
                name: '文化时空',
                emoji: '🌏',
                dimensions: ['culture', 'time', 'scene'],
                description: '文化视角、时代与场景'
            },
            character: {
                name: '角色技法',
                emoji: '🎭',
                dimensions: ['personality', 'technique', 'perspective'],
                description: '人格、技法与叙述视角'
            },
            structure: {
                name: '结构节奏',
                emoji: '📐',
                dimensions: ['structure', 'rhythm'],
                description: '篇章结构与韵律'
            },
            audience: {
                name: '受众主题',
                emoji: '🎯',
                dimensions: ['audience', 'theme', 'emotion', 'format'],
                description: '受众、主题、情绪与格式'
            }
        };
        this._creativeRecommendedDimensions = ['audience', 'emotion', 'format', 'style', 'theme'];
        this._creativeBindingsReady = false;
        this._pageDesignBindingsReady = false;

        this.apiEndpoint = '/api/config';
        this.config = {};
        this.uiConfig = this.loadUIConfig();
        this.customAPIs = [];  // 自定义API配置
        this._selectedAPIProvider = null;  // 大模型 API 面板当前选中的厂商 key
        this.customImgAPIs = [];  // 自定义图片API配置
        this._selectedImgAPIProvider = null;  // 图片 API 面板当前选中的服务 key
        this.aiforgeCustomProviders = [];  // AIForge自定义LLM提供商配置

        this.currentPanel = 'general';
        this.init();
    }

    async init() {
        try {
            // 1. 从后端加载 UI 配置    
            const uiResponse = await fetch('/api/config/ui-config');
            if (uiResponse.ok) {
                const uiConfig = await uiResponse.json();
                localStorage.setItem('aiwritex_ui_config', JSON.stringify(uiConfig));
                this.uiConfig = uiConfig;
            }

            // 2. 加载业务配置    
            await this.loadConfig();

            // 2.5. 加载动态选项数据(新增)  
            await this.loadDynamicOptions();

            // 3. 绑定事件监听器(只绑定一次)    
            this.bindEventListeners();

            // 4. 填充UI(只负责填充值,不绑定事件)    
            this.populateUI();
            this.showConfigPanel(this.currentPanel);
            this.toggleGrapesJSTheme(this.uiConfig.designTheme || 'follow-system');

            // 5. 通知主题管理器和窗口模式管理器    
            if (window.themeManager) {
                window.themeManager.onConfigLoaded();
            }
            if (window.windowModeManager) {
                window.windowModeManager.onConfigLoaded();
            }

            // 6. 最后绑定导航事件(确保DOM已加载)    
            this.bindConfigNavigation();
        } catch (error) {
        }
    }

    bindEventListeners() {
        // 主题选择器  
        const themeSelector = document.getElementById('theme-selector');
        if (themeSelector) {
            themeSelector.addEventListener('change', (e) => {
                this.uiConfig.theme = e.target.value;
                if (window.themeManager) {
                    window.themeManager.applyTheme(e.target.value, false);
                }

                this._markGeneralConfigDirty();
            });
        }

        // 窗口模式选择器    
        const windowModeSelector = document.getElementById('window-mode-selector');
        if (windowModeSelector) {
            windowModeSelector.addEventListener('change', (e) => {
                this.uiConfig.windowMode = e.target.value;
                if (window.windowModeManager) {
                    window.windowModeManager.applyMode(e.target.value);
                }
                this._markGeneralConfigDirty();
            });
        }

        // 网页设计器主题选择器  
        const designThemeSelector = document.getElementById('design-theme-selector');
        if (designThemeSelector) {
            designThemeSelector.addEventListener('change', (e) => {
                this.uiConfig.designTheme = e.target.value;
                this.toggleGrapesJSTheme(e.target.value);
                this._markGeneralConfigDirty();
            });
        }

        const saveGeneralConfigBtn = document.getElementById('save-general-config');
        if (saveGeneralConfigBtn) {
            saveGeneralConfigBtn.addEventListener('click', () => this.saveGeneralConfig());
        }

        const resetGeneralConfigBtn = document.getElementById('reset-general-config');
        if (resetGeneralConfigBtn) {
            resetGeneralConfigBtn.addEventListener('click', () => this.resetGeneralConfig());
        }

        // 文章格式  
        const articleFormatSelect = document.getElementById('article-format');
        if (articleFormatSelect) {
            articleFormatSelect.addEventListener('change', async (e) => {
                await this.updateConfig({ article_format: e.target.value });

                // 联动禁用逻辑  
                const formatPublishCheckbox = document.getElementById('format-publish');
                if (formatPublishCheckbox) {
                    formatPublishCheckbox.disabled = e.target.value === 'html';
                }
            });
        }

        // 自动发布  
        const autoPublishCheckbox = document.getElementById('auto-publish');
        if (autoPublishCheckbox) {
            autoPublishCheckbox.addEventListener('change', async (e) => {
                await this.updateConfig({ auto_publish: e.target.checked });
            });
        }

        // 格式化发布  
        const formatPublishCheckbox = document.getElementById('format-publish');
        if (formatPublishCheckbox) {
            formatPublishCheckbox.addEventListener('change', async (e) => {
                await this.updateConfig({ format_publish: e.target.checked });
            });
        }

        const autoDeleteCheckbox = document.getElementById('auto-delete-published');
        if (autoDeleteCheckbox) {
            autoDeleteCheckbox.addEventListener('change', async (e) => {
                await this.updateConfig({ auto_delete_published: e.target.checked });
            });
        }

        // 使用模板  
        const useTemplateCheckbox = document.getElementById('use-template');
        if (useTemplateCheckbox) {
            useTemplateCheckbox.addEventListener('change', async (e) => {
                await this.updateConfig({ use_template: e.target.checked });

                // 联动禁用逻辑  
                const templateCategorySelect = document.getElementById('config-template-category');
                const templateSelect = document.getElementById('template');
                if (templateCategorySelect) templateCategorySelect.disabled = !e.target.checked;
                if (templateSelect) templateSelect.disabled = !e.target.checked;
            });
        }

        // 模板分类(修改为级联加载)  
        const templateCategorySelect = document.getElementById('config-template-category');
        if (templateCategorySelect) {
            templateCategorySelect.addEventListener('change', async (e) => {
                const category = e.target.value;

                // 更新配置  
                await this.updateConfig({ template_category: category });

                // 级联加载模板列表  
                const templateSelect = document.getElementById('template');
                if (templateSelect) {
                    // 清空现有选项  
                    templateSelect.innerHTML = '';

                    // 添加"随机模板"选项  
                    const randomOption = document.createElement('option');
                    randomOption.value = '';
                    randomOption.textContent = '随机模板';
                    templateSelect.appendChild(randomOption);

                    // 加载新分类的模板  
                    if (category) {
                        const templates = await this.loadTemplatesByCategory(category);
                        templates.forEach(template => {
                            const option = document.createElement('option');
                            option.value = template;
                            option.textContent = template;
                            templateSelect.appendChild(option);
                        });
                    }

                    // 重置为"随机模板"  
                    templateSelect.value = '';
                }
            });
        }

        // 模板选择  
        const templateSelect = document.getElementById('template');
        if (templateSelect) {
            templateSelect.addEventListener('change', async (e) => {
                await this.updateConfig({ template: e.target.value });
            });
        }

        // 压缩模板  
        const useCompressCheckbox = document.getElementById('use-compress');
        if (useCompressCheckbox) {
            useCompressCheckbox.addEventListener('change', async (e) => {
                await this.updateConfig({ use_compress: e.target.checked });
            });
        }

        // 最大搜索结果  
        const maxSearchResultsInput = document.getElementById('max-search-results');
        if (maxSearchResultsInput) {
            maxSearchResultsInput.addEventListener('change', async (e) => {
                await this.updateConfig({ aiforge_search_max_results: parseInt(e.target.value) });
            });
        }

        // 最小搜索结果  
        const minSearchResultsInput = document.getElementById('min-search-results');
        if (minSearchResultsInput) {
            minSearchResultsInput.addEventListener('change', async (e) => {
                await this.updateConfig({ aiforge_search_min_results: parseInt(e.target.value) });
            });
        }

        // 最小文章字数  
        const minArticleLenInput = document.getElementById('min-article-len');
        if (minArticleLenInput) {
            minArticleLenInput.addEventListener('change', async (e) => {
                await this.updateConfig({ min_article_len: parseInt(e.target.value) });
            });
        }

        // 最大文章字数  
        const maxArticleLenInput = document.getElementById('max-article-len');
        if (maxArticleLenInput) {
            maxArticleLenInput.addEventListener('change', async (e) => {
                await this.updateConfig({ max_article_len: parseInt(e.target.value) });
            });
        }

        // 文章配图数量
        const articleImageCountInput = document.getElementById('article-image-count');
        if (articleImageCountInput) {
            articleImageCountInput.addEventListener('change', async (e) => {
                let count = parseInt(e.target.value, 10);
                if (Number.isNaN(count)) count = 3;
                count = Math.max(1, Math.min(12, count));
                e.target.value = count;
                await this.updateConfig({
                    img_api: {
                        ...(this.config.img_api || {}),
                        settings: {
                            ...(this.config.img_api?.settings || {}),
                            article_image_count: count
                        }
                    }
                });
            });
        }

        // 严格新鲜度
        const strictFreshnessCheckbox = document.getElementById('strict-freshness');
        if (strictFreshnessCheckbox) {
            strictFreshnessCheckbox.addEventListener('change', async (e) => {
                await this.updateConfig({ strict_freshness: e.target.checked });
            });
        }

        // 串行模式强制开关 (V18.0)
        const serialModeCheckbox = document.getElementById('serial-mode-forced');
        if (serialModeCheckbox) {
            serialModeCheckbox.addEventListener('change', async (e) => {
                const forced = e.target.checked;
                await this.updateConfig({
                    swarm_settings: {
                        ...this.config.swarm_settings,
                        serial_mode_forced: forced,
                        swarm_mode_enabled: !forced  // 串行模式与蜂群模式互斥
                    }
                });
            });
        }

        // ========== 选题来源设置事件绑定 ==========  

        // 保存平台配置按钮  
        const savePlatformsConfigBtn = document.getElementById('save-platforms-config');
        if (savePlatformsConfigBtn) {
            savePlatformsConfigBtn.addEventListener('click', async () => {
                const success = await this.saveConfig();

                if (success) {
                    // 清除未保存提示  
                    const saveBtn = document.getElementById('save-platforms-config');
                    if (saveBtn) {
                        saveBtn.classList.remove('has-changes');
                        saveBtn.innerHTML = '保存设置';
                    }
                }

                window.app?.showNotification(
                    success ? '平台配置已保存' : '保存平台配置失败',
                    success ? 'success' : 'error'
                );
            });
        }

        // 恢复默认平台配置按钮  
        const resetPlatformsConfigBtn = document.getElementById('reset-platforms-config');
        if (resetPlatformsConfigBtn) {
            resetPlatformsConfigBtn.addEventListener('click', async () => {
                // 获取默认配置  
                const response = await fetch(`${this.apiEndpoint}/default`);
                if (response.ok) {
                    const result = await response.json();
                    const defaultPlatforms = result.data.platforms;

                    // 更新配置  
                    await this.updateConfig({ platforms: defaultPlatforms });

                    // 刷新UI  
                    this.populatePlatformsUI();

                    window.app?.showNotification('已恢复默认平台配置', 'info');
                } else {
                    window.app?.showNotification('恢复默认配置失败', 'error');
                }
            });
        }

        // ========== 微信公众号设置事件绑定 ==========  

        // 添加凭证按钮  
        const addWeChatCredentialBtn = document.getElementById('add-wechat-credential');
        if (addWeChatCredentialBtn) {
            addWeChatCredentialBtn.addEventListener('click', () => {
                this.addWeChatCredential();
            });
        }

        // 保存微信配置按钮  
        const saveWeChatConfigBtn = document.getElementById('save-wechat-config');
        if (saveWeChatConfigBtn) {
            saveWeChatConfigBtn.addEventListener('click', async () => {
                await this.saveWeChatConfig();
            });
        }

        // 恢复默认微信配置按钮  
        const resetWeChatConfigBtn = document.getElementById('reset-wechat-config');
        if (resetWeChatConfigBtn) {
            resetWeChatConfigBtn.addEventListener('click', async () => {
                const response = await fetch(`${this.apiEndpoint}/default`);
                if (response.ok) {
                    const result = await response.json();
                    const defaultCredentials = result.data.wechat.credentials;

                    await this.updateConfig({
                        wechat: { credentials: defaultCredentials }
                    });

                    this.populateWeChatUI();

                    window.app?.showNotification('已恢复默认微信配置', 'info');
                } else {
                    window.app?.showNotification('恢复默认配置失败', 'error');
                }
            });
        }

        // 绑定复制服务器IP按钮 (新增)
        const copyIPBtn = document.getElementById('copy-server-ip');
        if (copyIPBtn) {
            copyIPBtn.addEventListener('click', () => {
                const ipText = document.getElementById('server-outbound-ip')?.textContent;
                if (ipText && ipText !== '正在获取...' && ipText !== '获取失败') {
                    navigator.clipboard.writeText(ipText).then(() => {
                        const originalHTML = copyIPBtn.innerHTML;
                        copyIPBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> 已复制';
                        copyIPBtn.style.background = '#22c55e';

                        setTimeout(() => {
                            copyIPBtn.innerHTML = originalHTML;
                            copyIPBtn.style.background = '';
                        }, 2000);
                    });
                }
            });
        }

        // 绑定刷新服务器IP按钮
        const refreshIPBtn = document.getElementById('refresh-server-ip');
        if (refreshIPBtn) {
            refreshIPBtn.addEventListener('click', async () => {
                const ipDisplay = document.getElementById('server-outbound-ip');
                if (ipDisplay) {
                    ipDisplay.textContent = '正在刷新...';
                    ipDisplay.style.color = '';
                }
                refreshIPBtn.disabled = true;
                const refreshSvg = refreshIPBtn.querySelector('svg');
                if (refreshSvg) {
                    refreshSvg.style.animation = 'spin 1s linear infinite';
                }

                await this.loadServerIP();

                refreshIPBtn.disabled = false;
                if (refreshSvg) {
                    refreshSvg.style.animation = '';
                }
            });
        }

        // ========== 微信公众号输入框事件绑定 ==========  
        // 注意:由于凭证是动态生成的,需要使用事件委托  

        const wechatContainer = document.getElementById('wechat-credentials-container');
        if (wechatContainer) {
            // 处理复选框的change事件  
            wechatContainer.addEventListener('change', async (e) => {
                if (e.target.matches('input[type="checkbox"][id^="wechat-"]')) {
                    const id = e.target.id;
                    const match = id.match(/wechat-(\w+)-(\d+)/);
                    if (match) {
                        const [, field, indexStr] = match;
                        const index = parseInt(indexStr);

                        if (field === 'call-sendall') {
                            this.updateSendallOptions(index, e.target.checked);
                        } else if (field === 'sendall') {
                            const tagIdInput = document.getElementById(`wechat-tag-id-${index}`);
                            if (tagIdInput) {
                                tagIdInput.disabled = e.target.checked;
                            }
                            await this.updateWeChatCredential(index);
                        }
                    }
                }
            });
            
            // 处理文本输入框的input事件 - 实时更新配置
            wechatContainer.addEventListener('input', async (e) => {
                if (e.target.matches('input[type="text"][id^="wechat-appid-"]') ||
                    e.target.matches('input[type="text"][id^="wechat-appsecret-"]') ||
                    e.target.matches('input[type="text"][id^="wechat-author-"]') ||
                    e.target.matches('input[type="number"][id^="wechat-tag-id-"]')) {
                    const id = e.target.id;
                    const match = id.match(/wechat-(\w+)-(\d+)/);
                    if (match) {
                        const [, field, indexStr] = match;
                        const index = parseInt(indexStr);
                        // 防抖更新
                        clearTimeout(this._wechatUpdateTimer);
                        this._wechatUpdateTimer = setTimeout(() => {
                            this.updateWeChatCredential(index);
                        }, 500);
                    }
                }
            });
        }

        // ========== 大模型API设置事件绑定 ==========  

        // 保存API配置按钮  
        const saveAPIConfigBtn = document.getElementById('save-api-config');
        if (saveAPIConfigBtn) {
            saveAPIConfigBtn.addEventListener('click', async () => {
                await this.saveAPIConfig();
            });
        }

        // 恢复默认API配置按钮  
        const resetAPIConfigBtn = document.getElementById('reset-api-config');
        if (resetAPIConfigBtn) {
            resetAPIConfigBtn.addEventListener('click', async () => {
                const response = await fetch(`${this.apiEndpoint}/default`);
                if (response.ok) {
                    const result = await response.json();
                    const defaultAPI = result.data.api;

                    await this.updateConfig({ api: defaultAPI });

                    this.populateAPIUI();

                    window.app?.showNotification('已恢复默认API配置', 'info');
                } else {
                    window.app?.showNotification('恢复默认配置失败', 'error');
                }
            });
        }

        // 保存图片API配置  
        const saveImgAPIConfigBtn = document.getElementById('save-img-api-config');
        if (saveImgAPIConfigBtn) {
            saveImgAPIConfigBtn.addEventListener('click', async () => {
                await this.saveImgAPIConfig();
            });
        }

        // 恢复默认图片API配置  
        const resetImgAPIConfigBtn = document.getElementById('reset-img-api-config');
        if (resetImgAPIConfigBtn) {
            resetImgAPIConfigBtn.addEventListener('click', async () => {
                await this.resetImgAPIConfig();
            });
        }

        // 保存AIForge配置  
        const saveAIForgeConfigBtn = document.getElementById('save-aiforge-config');
        if (saveAIForgeConfigBtn) {
            saveAIForgeConfigBtn.addEventListener('click', async () => {
                const success = await this.saveConfig();

                if (success) {
                    saveAIForgeConfigBtn.classList.remove('has-changes');
                    saveAIForgeConfigBtn.innerHTML = '保存设置';
                }

                window.app?.showNotification(
                    success ? 'AIForge配置已保存' : '保存AIForge配置失败',
                    success ? 'success' : 'error'
                );
            });
        }

        // 恢复默认AIForge配置  
        const resetAIForgeConfigBtn = document.getElementById('reset-aiforge-config');
        if (resetAIForgeConfigBtn) {
            resetAIForgeConfigBtn.addEventListener('click', async () => {
                const response = await fetch(`${this.apiEndpoint}/default`);
                if (response.ok) {
                    const result = await response.json();
                    const defaultAIForge = result.data.aiforge_config;

                    await this.updateConfig({ aiforge_config: defaultAIForge });

                    this.populateAIForgeUI();

                    window.app?.showNotification('已恢复默认AIForge配置', 'info');
                } else {
                    window.app?.showNotification('恢复默认配置失败', 'error');
                }
            });
        }

        // 添加AIForge自定义LLM提供商
        const addAiforgeProviderBtn = document.getElementById('add-aiforge-custom-provider');
        if (addAiforgeProviderBtn) {
            addAiforgeProviderBtn.addEventListener('click', () => {
                this.addAiforgeCustomProvider();
            });
        }

        // 加载AIForge自定义提供商
        this.loadAiforgeCustomProviders();

        // ========== AIForge配置事件绑定 ==========  

        // 1. 通用配置 - 最大重试次数  
        const aiforgeMaxRounds = document.getElementById('aiforge-max-rounds');
        if (aiforgeMaxRounds) {
            aiforgeMaxRounds.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        max_rounds: parseInt(e.target.value)
                    }
                });
            });
        }

        // 2. 通用配置 - 默认最大Tokens  
        const aiforgeDefaultMaxTokens = document.getElementById('aiforge-default-max-tokens');
        if (aiforgeDefaultMaxTokens) {
            aiforgeDefaultMaxTokens.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        max_tokens: parseInt(e.target.value)  // ✅ 改为 max_tokens  
                    }
                });
            });
        }

        // 3. 代码缓存配置 - 启用缓存  
        const cacheEnabled = document.getElementById('cache-enabled');
        if (cacheEnabled) {
            cacheEnabled.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        cache: {  // ✅ 改为 cache  
                            ...this.config.aiforge_config.cache,
                            code: {  // ✅ 添加 code 层级  
                                ...this.config.aiforge_config.cache.code,
                                enabled: e.target.checked
                            }
                        }
                    }
                });
            });
        }

        // 4. 代码缓存配置 - 最大模块数  
        const cacheMaxModules = document.getElementById('cache-max-modules');
        if (cacheMaxModules) {
            cacheMaxModules.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        cache: {  // ✅ 改为 cache  
                            ...this.config.aiforge_config.cache,
                            code: {  // ✅ 添加 code 层级  
                                ...this.config.aiforge_config.cache.code,
                                max_modules: parseInt(e.target.value)
                            }
                        }
                    }
                });
            });
        }

        // 5. 代码缓存配置 - 失败阈值  
        const cacheFailureThreshold = document.getElementById('cache-failure-threshold');
        if (cacheFailureThreshold) {
            cacheFailureThreshold.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        cache: {  // ✅ 改为 cache  
                            ...this.config.aiforge_config.cache,
                            code: {  // ✅ 添加 code 层级  
                                ...this.config.aiforge_config.cache.code,
                                failure_threshold: parseFloat(e.target.value)  // ✅ 使用 parseFloat  
                            }
                        }
                    }
                });
            });
        }

        // 6. 代码缓存配置 - 最大保存天数  
        const cacheMaxAgeDays = document.getElementById('cache-max-save-days');
        if (cacheMaxAgeDays) {
            cacheMaxAgeDays.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        cache: {  // ✅ 改为 cache  
                            ...this.config.aiforge_config.cache,
                            code: {  // ✅ 添加 code 层级  
                                ...this.config.aiforge_config.cache.code,
                                max_age_days: parseInt(e.target.value)  // ✅ 改为 max_age_days  
                            }
                        }
                    }
                });
            });
        }

        // 7. 代码缓存配置 - 清理间隔  
        const cacheCleanupInterval = document.getElementById('cache-cleanup-interval');
        if (cacheCleanupInterval) {
            cacheCleanupInterval.addEventListener('change', async (e) => {
                await this.updateConfig({
                    aiforge_config: {
                        ...this.config.aiforge_config,
                        cache: {  // ✅ 改为 cache  
                            ...this.config.aiforge_config.cache,
                            code: {  // ✅ 添加 code 层级  
                                ...this.config.aiforge_config.cache.code,
                                cleanup_interval: parseInt(e.target.value)  // ✅ 改为 cleanup_interval  
                            }
                        }
                    }
                });
            });
        }

        this.bindCreativeConfigListeners();

        this.bindPageDesignConfigListeners();
    }

    _markPageDesignDirty() {
        const saveBtn = document.getElementById('save-page-design-config');
        if (saveBtn && !saveBtn.classList.contains('has-changes')) {
            saveBtn.classList.add('has-changes');
            saveBtn.innerHTML = '保存设置 <span style="color: var(--warning-color);">(有未保存更改)</span>';
        }
    }

    bindPageDesignConfigListeners() {
        if (this._pageDesignBindingsReady) return;
        this._pageDesignBindingsReady = true;

        document.getElementById('use-original-styles')?.addEventListener('change', (e) => {
            this.togglePageDesignSections(e.target.checked);
            this.updatePageDesignUIState();
            this._markPageDesignDirty();
        });

        document.getElementById('unified-brand-style')?.addEventListener('change', () => {
            this.updatePageDesignUIState();
            this._markPageDesignDirty();
        });

        document.getElementById('save-page-design-config')?.addEventListener('click', () => {
            this.savePageDesignConfig();
        });

        document.getElementById('reset-page-design-config')?.addEventListener('click', async () => {
            const response = await fetch(`${this.apiEndpoint}/default`);
            if (!response.ok) {
                window.app?.showNotification('恢复默认配置失败', 'error');
                return;
            }
            const result = await response.json();
            await this.updateConfig({ page_design: result.data.page_design });
            this.populatePageDesignUI();
            window.app?.showNotification('已恢复默认页面设计配置', 'info');
        });

        const pageDesignInputs = [
            'container-max-width', 'container-margin-h', 'container-bg-color',
            'card-border-radius', 'card-padding', 'card-bg-color', 'card-box-shadow',
            'typography-font-size', 'typography-line-height', 'typography-heading-scale',
            'typography-text-color', 'typography-heading-color',
            'spacing-section-margin', 'spacing-element-margin',
            'accent-primary-color', 'accent-secondary-color', 'accent-highlight-bg',
            'unified-brand-style'
        ];

        pageDesignInputs.forEach((inputId) => {
            const input = document.getElementById(inputId);
            if (!input) return;
            const handler = () => {
                if (input.type === 'color') {
                    this.syncPageDesignColorLabels(input);
                    this.updatePageDesignAccentPreview();
                }
                this._markPageDesignDirty();
            };
            input.addEventListener('input', handler);
            input.addEventListener('change', handler);
        });
    }

    syncPageDesignColorLabels(colorInput) {
        const hex = document.querySelector(`[data-color-for="${colorInput.id}"]`);
        if (hex) hex.textContent = (colorInput.value || '').toLowerCase();
    }

    syncAllPageDesignColorLabels() {
        document.querySelectorAll('.page-design-color-input input[type="color"]').forEach((el) => {
            this.syncPageDesignColorLabels(el);
        });
    }

    updatePageDesignAccentPreview() {
        const primary = document.getElementById('accent-primary-color')?.value || '#3a7bd5';
        const secondary = document.getElementById('accent-secondary-color')?.value || '#00b09b';
        const highlight = document.getElementById('accent-highlight-bg')?.value || '#f0f7ff';
        const elP = document.getElementById('preview-primary');
        const elS = document.getElementById('preview-secondary');
        const elH = document.getElementById('preview-highlight');
        if (elP) elP.style.background = primary;
        if (elS) elS.style.background = secondary;
        if (elH) elH.style.background = highlight;
    }

    updatePageDesignUIState() {
        const useOriginal = document.getElementById('use-original-styles')?.checked || false;
        const unifiedBrand = document.getElementById('unified-brand-style')?.checked !== false;
        const modeTitle = document.getElementById('page-design-mode-title');
        const modeDesc = document.getElementById('page-design-mode-desc');
        const brandPill = document.getElementById('page-design-brand-pill');
        const modeBar = document.getElementById('page-design-mode-bar');
        const accentHint = document.getElementById('page-design-accent-hint');
        const accentBody = document.getElementById('accent-design-body');

        if (modeTitle) {
            modeTitle.textContent = useOriginal ? '使用原始样式' : '应用全局样式';
        }
        if (modeDesc) {
            modeDesc.textContent = useOriginal
                ? '已跳过全局参数，排版以 HTML 文件内联样式为准'
                : '下方参数将注入新生成文章的 HTML 排版';
        }
        if (brandPill) {
            brandPill.textContent = unifiedBrand ? '统一配色' : '自由配色';
            brandPill.classList.toggle('is-free', !unifiedBrand);
        }
        if (modeBar) modeBar.classList.toggle('is-original', useOriginal);
        if (accentHint) accentHint.hidden = unifiedBrand;
        if (accentBody) accentBody.classList.toggle('accent-muted', !unifiedBrand);
    }

    // 加载页面设计配置到UI(续)  
    populatePageDesignUI() {
        if (!this.config.page_design) {
            const useOriginalCheckbox = document.getElementById('use-original-styles');
            if (useOriginalCheckbox) {
                useOriginalCheckbox.checked = true;
                this.togglePageDesignSections(true);
            }
            return;
        }

        const pd = this.config.page_design;

        const unifiedBrand = document.getElementById('unified-brand-style');
        if (unifiedBrand) {
            unifiedBrand.checked = pd.unified_brand_style !== false;
        }

        // 使用原始样式开关     
        const useOriginalCheckbox = document.getElementById('use-original-styles');
        if (useOriginalCheckbox) {
            if (pd.use_original_styles !== undefined) {
                useOriginalCheckbox.checked = pd.use_original_styles;
            } else {
                useOriginalCheckbox.checked = true;
            }

            this.togglePageDesignSections(useOriginalCheckbox.checked);
        }

        // 容器    
        if (pd.container) {
            document.getElementById('container-max-width').value = pd.container.max_width || 750;
            document.getElementById('container-margin-h').value = pd.container.margin_horizontal || 10;
            document.getElementById('container-bg-color').value = pd.container.background_color || '#f8f9fa';
        }

        // 卡片    
        if (pd.card) {
            document.getElementById('card-border-radius').value = pd.card.border_radius || 12;
            document.getElementById('card-padding').value = pd.card.padding || 24;
            document.getElementById('card-bg-color').value = pd.card.background_color || '#ffffff';
            document.getElementById('card-box-shadow').value = pd.card.box_shadow || '0 4px 16px rgba(0,0,0,0.06)';
        }

        // 排版    
        if (pd.typography) {
            document.getElementById('typography-font-size').value = pd.typography.base_font_size || 16;
            document.getElementById('typography-line-height').value = pd.typography.line_height || 1.6;
            document.getElementById('typography-heading-scale').value = pd.typography.heading_scale || 1.5;
            document.getElementById('typography-text-color').value = pd.typography.text_color || '#333333';
            document.getElementById('typography-heading-color').value = pd.typography.heading_color || '#333333';
        }

        // 间距    
        if (pd.spacing) {
            document.getElementById('spacing-section-margin').value = pd.spacing.section_margin || 24;
            document.getElementById('spacing-element-margin').value = pd.spacing.element_margin || 16;
        }

        // 色彩    
        if (pd.accent) {
            document.getElementById('accent-primary-color').value = pd.accent.primary_color || '#3a7bd5';
            document.getElementById('accent-secondary-color').value = pd.accent.secondary_color || '#00b09b';
            document.getElementById('accent-highlight-bg').value = pd.accent.highlight_bg || '#f0f7ff';
        }

        this.syncAllPageDesignColorLabels();
        this.updatePageDesignAccentPreview();
        this.updatePageDesignUIState();
    }

    togglePageDesignSections(useOriginal) {
        const wrap = document.getElementById('page-design-styles-wrap');
        if (wrap) {
            wrap.classList.toggle('is-disabled', useOriginal);
        }

        const inputs = wrap?.querySelectorAll('input:not([type="checkbox"]), select, textarea') || [];
        inputs.forEach((input) => {
            input.disabled = useOriginal;
        });
    }

    // 保存页面设计配置  
    async savePageDesignConfig() {
        const pageDesignConfig = {
            unified_brand_style: document.getElementById('unified-brand-style')?.checked !== false,
            use_original_styles: document.getElementById('use-original-styles')?.checked || false,
            container: {
                max_width: parseInt(document.getElementById('container-max-width')?.value || 750),
                margin_horizontal: parseInt(document.getElementById('container-margin-h')?.value || 10),
                background_color: document.getElementById('container-bg-color')?.value || '#f8f9fa'
            },
            card: {
                border_radius: parseInt(document.getElementById('card-border-radius')?.value || 12),
                box_shadow: document.getElementById('card-box-shadow')?.value || '0 4px 16px rgba(0,0,0,0.06)',
                padding: parseInt(document.getElementById('card-padding')?.value || 24),
                background_color: document.getElementById('card-bg-color')?.value || '#ffffff'
            },
            typography: {
                base_font_size: parseInt(document.getElementById('typography-font-size')?.value || 16),
                line_height: parseFloat(document.getElementById('typography-line-height')?.value || 1.6),
                heading_scale: parseFloat(document.getElementById('typography-heading-scale')?.value || 1.5),
                text_color: document.getElementById('typography-text-color')?.value || '#333333',
                heading_color: document.getElementById('typography-heading-color')?.value || '#333333'
            },
            spacing: {
                section_margin: parseInt(document.getElementById('spacing-section-margin')?.value || 24),
                element_margin: parseInt(document.getElementById('spacing-element-margin')?.value || 16)
            },
            accent: {
                primary_color: document.getElementById('accent-primary-color')?.value || '#3a7bd5',
                secondary_color: document.getElementById('accent-secondary-color')?.value || '#2563a8',
                highlight_bg: document.getElementById('accent-highlight-bg')?.value || '#f0f7ff'
            }
        };

        await this.updateConfig({ page_design: pageDesignConfig });
        const success = await this.saveConfig();

        if (success) {
            const saveBtn = document.getElementById('save-page-design-config');
            if (saveBtn) {
                saveBtn.classList.remove('has-changes');
                saveBtn.innerHTML = '保存设置';
            }
        }

        window.app?.showNotification(
            success ? '页面设计配置已保存' : '保存配置失败',
            success ? 'success' : 'error'
        );
    }

    toggleGrapesJSTheme(designTheme) {
        const linkId = 'grapesjs-theme-override-link';
        const existingLink = document.getElementById(linkId);

        if (designTheme === 'follow-system') {
            // 跟随系统: 确保 CSS 已加载  
            if (!existingLink) {
                const link = document.createElement('link');
                link.id = linkId;
                link.rel = 'stylesheet';
                link.href = '/static/css/themes/grapesjs-theme-override.css';
                document.head.appendChild(link);
            }
        } else if (designTheme === 'default') {
            // 默认主题: 移除自定义 CSS  
            if (existingLink) {
                existingLink.remove();
            }
        }
    }

    populateUI() {
        // ========== 填充发布平台 ==========  
        const publishPlatformSelect = document.getElementById('publish-platform');
        if (publishPlatformSelect && this.config.publish_platform) {
            publishPlatformSelect.value = this.config.publish_platform;
        }

        // ========== 填充文章格式 ==========  
        const articleFormatSelect = document.getElementById('article-format');
        if (articleFormatSelect && this.config.article_format) {
            articleFormatSelect.value = this.config.article_format;
        }

        // ========== 填充自动发布 ==========  
        const autoPublishCheckbox = document.getElementById('auto-publish');
        if (autoPublishCheckbox && this.config.auto_publish !== undefined) {
            autoPublishCheckbox.checked = this.config.auto_publish;
        }

        // ========== 填充格式化发布 ==========  
        const formatPublishCheckbox = document.getElementById('format-publish');
        if (formatPublishCheckbox && this.config.format_publish !== undefined) {
            formatPublishCheckbox.checked = this.config.format_publish;
            formatPublishCheckbox.disabled = this.config.article_format === 'html';
        }

        const autoDeleteCheckbox = document.getElementById('auto-delete-published');
        if (autoDeleteCheckbox && this.config.auto_delete_published !== undefined) {
            autoDeleteCheckbox.checked = this.config.auto_delete_published;
        }

        // ========== 填充使用模板 ==========  
        const useTemplateCheckbox = document.getElementById('use-template');
        if (useTemplateCheckbox && this.config.use_template !== undefined) {
            useTemplateCheckbox.checked = this.config.use_template;
        }

        // ========== 填充模板分类 ==========    
        const templateCategorySelect = document.getElementById('config-template-category');
        if (templateCategorySelect) {
            templateCategorySelect.value = this.config.template_category || '';
            templateCategorySelect.disabled = !this.config.use_template;

            // 触发级联加载模板列表  
            if (this.config.template_category) {
                this.loadTemplatesByCategory(this.config.template_category).then(templates => {
                    const templateSelect = document.getElementById('template');
                    if (templateSelect) {
                        // 清空现有选项  
                        templateSelect.innerHTML = '';

                        // 添加"随机模板"选项  
                        const randomOption = document.createElement('option');
                        randomOption.value = '';
                        randomOption.textContent = '随机模板';
                        templateSelect.appendChild(randomOption);

                        // 添加模板选项  
                        templates.forEach(template => {
                            const option = document.createElement('option');
                            option.value = template;
                            option.textContent = template;
                            templateSelect.appendChild(option);
                        });

                        // 设置当前选中的模板  
                        templateSelect.value = this.config.template || '';
                        templateSelect.disabled = !this.config.use_template;
                    }
                });
            }
        }

        const useCompressCheckbox = document.getElementById('use-compress');
        if (useCompressCheckbox && this.config.use_compress !== undefined) {
            useCompressCheckbox.checked = this.config.use_compress;
        }

        // ========== 填充模板选择 ==========  
        const templateSelect = document.getElementById('template');
        if (templateSelect) {
            templateSelect.value = this.config.template || '';
            // 关键:根据use_template设置禁用状态  
            templateSelect.disabled = !this.config.use_template;
        }

        // ========== 6. 填充搜索数量配置 ==========  
        const maxSearchResultsInput = document.getElementById('max-search-results');
        if (maxSearchResultsInput && this.config.aiforge_search_max_results !== undefined) {
            maxSearchResultsInput.value = this.config.aiforge_search_max_results;
        }

        const minSearchResultsInput = document.getElementById('min-search-results');
        if (minSearchResultsInput && this.config.aiforge_search_min_results !== undefined) {
            minSearchResultsInput.value = this.config.aiforge_search_min_results;
        }

        // ========== 7. 填充文章长度配置 ==========  
        const minArticleLenInput = document.getElementById('min-article-len');
        if (minArticleLenInput && this.config.min_article_len !== undefined) {
            minArticleLenInput.value = this.config.min_article_len;
        }

        const maxArticleLenInput = document.getElementById('max-article-len');
        if (maxArticleLenInput && this.config.max_article_len !== undefined) {
            maxArticleLenInput.value = this.config.max_article_len;
        }

        // ========== 7.1 填充文章配图数量 ==========
        const articleImageCountInput = document.getElementById('article-image-count');
        if (articleImageCountInput) {
            const settings = this.config.img_api?.settings || {};
            const count = settings.article_image_count ?? settings.fast_mode_prompt_count ?? 3;
            articleImageCountInput.value = count;
        }

        // ========== 8. 填充生成鲜度控制 ==========
        const strictFreshnessCheckbox = document.getElementById('strict-freshness');
        if (strictFreshnessCheckbox) {
            strictFreshnessCheckbox.checked = this.config.strict_freshness !== false;
        }

        // ========== 9. 填充并发模式控制 (V18.0) ==========
        const serialModeCheckbox = document.getElementById('serial-mode-forced');
        if (serialModeCheckbox && this.config.swarm_settings) {
            serialModeCheckbox.checked = this.config.swarm_settings.serial_mode_forced !== false;
        }

        // ========== 8. 填充界面配置 ==========  
        const themeSelector = document.getElementById('theme-selector');
        if (themeSelector) {
            themeSelector.value = this.getTheme();
        }

        const windowModeSelector = document.getElementById('window-mode-selector');
        if (windowModeSelector) {
            windowModeSelector.value = this.getWindowMode();
        }
        // 填充设计主题选择器  
        const designThemeSelector = document.getElementById('design-theme-selector');
        if (designThemeSelector) {
            designThemeSelector.value = this.uiConfig.designTheme || 'follow-system';
        }

        // ========== 填充选题来源配置 ==========  
        this.populatePlatformsUI();

        // ========== 填充微信公众号配置 ==========  
        this.populateWeChatUI();

        // ========== 填充大模型API配置 ==========  
        this.populateAPIUI();

        this.populateImgAPIUI();

        this.populateAIForgeUI();

        this.populateCreativeUI();

        // 添加页面设计UI填充  
        this.populatePageDesignUI();

        // 绑定自定义API事件
        this.bindCustomAPIEvents();
    }

    // 填充选题来源UI  
    populatePlatformsUI() {
        const platformListBody = document.getElementById('platform-list-body');
        if (!platformListBody || !this.config.platforms) return;

        // 清空现有内容  
        platformListBody.innerHTML = '';

        // 生成平台行  
        this.config.platforms.forEach((platform, index) => {
            const row = document.createElement('tr');
            row.dataset.platformIndex = index;

            // 启用复选框列 - 使用统一的checkbox-label样式  
            const enabledCell = document.createElement('td');
            const checkboxLabel = document.createElement('label');
            checkboxLabel.className = 'checkbox-label';
            checkboxLabel.style.justifyContent = 'center';
            checkboxLabel.style.margin = '0';

            const enabledCheckbox = document.createElement('input');
            enabledCheckbox.type = 'checkbox';
            enabledCheckbox.checked = platform.enabled !== false;
            enabledCheckbox.addEventListener('change', async (e) => {
                await this.updatePlatformEnabled(index, e.target.checked);
            });

            const checkboxCustom = document.createElement('span');
            checkboxCustom.className = 'checkbox-custom';

            checkboxLabel.appendChild(enabledCheckbox);
            checkboxLabel.appendChild(checkboxCustom);
            enabledCell.appendChild(checkboxLabel);

            // 平台名称列  
            const nameCell = document.createElement('td');
            nameCell.className = 'platform-name';
            nameCell.textContent = platform.name;

            // 权重输入框列  
            const weightCell = document.createElement('td');
            const weightInput = document.createElement('input');
            weightInput.type = 'number';
            weightInput.className = 'platform-weight-input';
            weightInput.value = platform.weight;
            weightInput.min = '0';
            weightInput.max = '1';
            weightInput.step = '0.01';
            weightInput.disabled = platform.enabled === false;
            weightInput.addEventListener('change', async (e) => {
                await this.updatePlatformWeight(index, parseFloat(e.target.value));
            });
            weightCell.appendChild(weightInput);

            // 说明列  
            const descCell = document.createElement('td');
            descCell.className = 'platform-description';
            descCell.textContent = this.getPlatformDescription(platform.name);

            // 组装行  
            row.appendChild(enabledCell);
            row.appendChild(nameCell);
            row.appendChild(weightCell);
            row.appendChild(descCell);

            platformListBody.appendChild(row);
        });
    }

    // 填充微信公众号UI  
    populateWeChatUI() {
        const container = document.getElementById('wechat-credentials-container');
        if (!container) return;

        const credentials = this.config.wechat?.credentials || [];

        // 清空现有内容  
        container.innerHTML = '';

        // 生成凭证卡片  
        credentials.forEach((credential, index) => {
            const card = this.createWeChatCredentialCard(credential, index);
            container.appendChild(card);
        });

        // V13.0 Optimization: 延迟加载服务器 IP，不阻塞首屏渲染
        setTimeout(() => this.loadServerIP(), 1500);
    }

    // 异步加载服务器出口IP (v2: 显示来源+缓存状态)
    async loadServerIP() {
        const ipDisplay = document.getElementById('server-outbound-ip');
        if (!ipDisplay) return;

        try {
            const response = await fetch('/api/config/wechat/server-ip');
            const result = await response.json();

            if (result.status === 'success' && result.ip) {
                ipDisplay.textContent = result.ip;
                ipDisplay.style.color = '#22c55e'; // v2: 成功时绿色
                ipDisplay.title = `来源: ${result.source || '未知'}${result.cached ? ' (缓存)' : ' (实时)'}`;
            } else {
                ipDisplay.textContent = '获取失败';
                ipDisplay.style.color = '#ef4444';
                ipDisplay.title = result.message || '无法获取IP';
            }
        } catch (error) {
            ipDisplay.textContent = '网络错误';
            ipDisplay.style.color = '#ef4444';
            ipDisplay.title = error.message;
        }
    }

    // 创建表单组辅助方法      
    createFormGroup(label, type, id, value, placeholder, required = false, readonly = false) {
        const group = document.createElement('div');
        group.className = 'form-group';

        const labelEl = document.createElement('label');
        labelEl.setAttribute('for', id);
        labelEl.textContent = label;
        if (required) {
            const requiredSpan = document.createElement('span');
            requiredSpan.className = 'required';
            requiredSpan.textContent = ' *';
            labelEl.appendChild(requiredSpan);
        }

        const input = document.createElement('input');
        input.type = type;
        input.id = id;
        input.className = 'form-control';

        if (value !== undefined && value !== null) {
            input.value = value;
        } else {
            input.value = '';
        }

        if (placeholder) {
            input.placeholder = placeholder;
            input.title = placeholder;
        }

        if (readonly) {
            input.readOnly = true;
        }

        // ✅ 通用的值变化检测逻辑      
        let originalValue = input.value;
        input.addEventListener('blur', async (e) => {
            // ✅ 只在值真正改变时才更新    
            if (e.target.value !== originalValue) {
                originalValue = e.target.value;
                e.stopPropagation();

                // ✅ 微信公众号凭证      
                const wechatMatch = id.match(/wechat-\w+-(\d+)/);
                if (wechatMatch) {
                    const index = parseInt(wechatMatch[1]);
                    await this.updateWeChatCredential(index);
                    return;
                }

                // ✅ 大模型API配置(只读字段不更新)  
                const apiMatch = id.match(/api-(\w+)-(key-name|api-base)/);
                if (apiMatch) {
                    // KEY名称和API BASE是只读的,不需要更新    
                    return;
                }

                // ✅ 图片API配置      
                const imgApiMatch = id.match(/img-api-(\w+)-(api-key|model|api-base)/);
                if (imgApiMatch) {
                    const [, provider, rawField] = imgApiMatch;
                    const field = rawField === 'api-key' ? 'api_key' : rawField === 'api-base' ? 'api_base' : rawField;
                    await this.updateImgAPIProviderField(provider, field, e.target.value);
                    return;
                }

                // ✅ AIForge LLM配置  
                const aiforgeMatch = id.match(/aiforge-(\w+)-(type|model|api-key|base-url|timeout|max-tokens)/);
                if (aiforgeMatch) {
                    const [, provider, field] = aiforgeMatch;
                    await this.updateAIForgeLLMProviderField(provider, field, e.target.value);
                    return;
                }
            } else {
                e.stopPropagation();
            }
        });

        group.appendChild(labelEl);
        group.appendChild(input);

        return group;
    }

    // 更新群发选项联动逻辑  
    updateSendallOptions(index, callSendallEnabled) {
        const sendallCheckbox = document.getElementById(`wechat-sendall-${index}`);
        const tagIdInput = document.getElementById(`wechat-tag-id-${index}`);

        if (sendallCheckbox) {
            sendallCheckbox.disabled = !callSendallEnabled;
        }

        if (tagIdInput) {
            const sendallChecked = sendallCheckbox?.checked !== false;
            tagIdInput.disabled = !callSendallEnabled || sendallChecked;
        }

        // 更新配置  
        this.updateWeChatCredential(index);
    }

    // 更新单个凭证配置  
    async updateWeChatCredential(index) {
        const credentials = [...(this.config.wechat?.credentials || [])];

        const credential = {
            appid: document.getElementById(`wechat-appid-${index}`)?.value || '',
            appsecret: document.getElementById(`wechat-appsecret-${index}`)?.value || '',
            author: document.getElementById(`wechat-author-${index}`)?.value || '',
            draft_only: document.getElementById(`wechat-draft-only-${index}`)?.checked || false,
            call_sendall: document.getElementById(`wechat-call-sendall-${index}`)?.checked || false,
            sendall: document.getElementById(`wechat-sendall-${index}`)?.checked !== false,
            tag_id: parseInt(document.getElementById(`wechat-tag-id-${index}`)?.value || 0)
        };

        credentials[index] = credential;

        await this.updateConfig({
            wechat: { credentials }
        });
    }

    // 添加新凭证  
    addWeChatCredential() {
        const credentials = [...(this.config.wechat?.credentials || [])];

        // 添加默认凭证  
        credentials.push({
            appid: '',
            appsecret: '',
            author: '',
            draft_only: false,
            call_sendall: false,
            sendall: true,
            tag_id: 0
        });

        // 更新配置  
        this.updateConfig({
            wechat: { credentials }
        }).then(() => {
            // 刷新UI  
            this.populateWeChatUI();

            window.app?.showNotification(
                '已添加新凭证,请填写后保存',
                'info'
            );
        });
    }

    // 删除凭证  
    deleteWeChatCredential(index) {
        if (index === 0) {
            window.app?.showNotification(
                '第一个凭证不能删除',
                'warning'
            );
            return;
        }

        const credentials = [...(this.config.wechat?.credentials || [])];
        credentials.splice(index, 1);

        this.updateConfig({
            wechat: { credentials }
        }).then(() => {
            this.populateWeChatUI();

            window.app?.showNotification(
                '凭证已删除',
                'info'
            );
        });
    }

    // 保存微信配置  
    async saveWeChatConfig() {
        // 验证必填字段  
        const credentials = this.config.wechat?.credentials || [];

        for (let i = 0; i < credentials.length; i++) {
            const cred = credentials[i];

            // 如果启用了自动发布,检查必填字段  
            if (this.config.auto_publish) {
                if (!cred.appid || !cred.appsecret || !cred.author) {
                    window.app?.showNotification(
                        `凭证 ${i + 1} 缺少必填字段(AppID/AppSecret/作者)`,
                        'error'
                    );
                    return;
                }
            }
        }

        // 调用通用保存方法  
        const success = await this.saveConfig();

        if (success) {
            const saveBtn = document.getElementById('save-wechat-config');
            if (saveBtn) {
                saveBtn.classList.remove('has-changes');
                saveBtn.innerHTML = '保存配置';
            }
        }

        window.app?.showNotification(
            success ? '微信配置已保存' : '保存微信配置失败',
            success ? 'success' : 'error'
        );
    }

    // 创建微信凭证卡片  
    createWeChatCredentialCard(credential, index) {
        const card = document.createElement('div');
        card.className = 'wechat-credential-card';
        card.dataset.credentialIndex = index;

        // 标题栏  
        const header = document.createElement('div');
        header.className = 'credential-header';

        const title = document.createElement('div');
        title.className = 'credential-title';
        title.textContent = `凭证 ${index + 1}`;

        // 测试按钮
        const testBtn = document.createElement('button');
        testBtn.className = 'test-btn';
        testBtn.id = `wechat-test-btn-${index}`;
        testBtn.innerHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span>测试连接</span>
        `;
        testBtn.addEventListener('click', () => this.testWeChatCredential(index));

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'credential-delete-btn';
        deleteBtn.textContent = '删除';
        deleteBtn.disabled = index === 0; // 第一个凭证不能删除  
        deleteBtn.addEventListener('click', () => {
            this.deleteWeChatCredential(index);
        });

        header.appendChild(title);
        header.appendChild(testBtn);
        header.appendChild(deleteBtn);

        // 表单内容  
        const form = document.createElement('div');
        form.className = 'credential-form';

        // 行1: AppID、AppSecret、作者在同一行  
        const row1 = document.createElement('div');
        row1.className = 'form-row';

        const appidGroup = this.createFormGroup(
            'AppID',
            'text',
            `wechat-appid-${index}`,
            credential.appid || '',
            '微信公众号AppID',
            true
        );
        appidGroup.classList.add('form-group-third');

        const appsecretGroup = this.createFormGroup(
            'AppSecret',
            'password',
            `wechat-appsecret-${index}`,
            credential.appsecret || '',
            '微信公众号AppSecret',
            true
        );
        appsecretGroup.classList.add('form-group-third');

        const authorGroup = this.createFormGroup(
            '作者',
            'text',
            `wechat-author-${index}`,
            credential.author || '',
            '文章作者名称'
        );
        authorGroup.classList.add('form-group-third');

        row1.appendChild(appidGroup);
        row1.appendChild(appsecretGroup);
        row1.appendChild(authorGroup);

        // 状态显示区域
        const statusRow = document.createElement('div');
        statusRow.className = 'form-row';
        statusRow.id = `wechat-status-row-${index}`;

        const statusDiv = document.createElement('div');
        statusDiv.className = 'credential-status';
        statusDiv.id = `wechat-status-${index}`;
        statusDiv.style.display = 'none';

        statusRow.appendChild(statusDiv);

        // 行2: 发布选项
        const row2 = document.createElement('div');
        row2.className = 'form-row';

        const publishOptionsDiv = document.createElement('div');
        publishOptionsDiv.className = 'sendall-options';

        // 仅保存草稿复选框
        const draftOnlyGroup = document.createElement('div');
        draftOnlyGroup.className = 'form-group';

        const draftOnlyLabel = document.createElement('label');
        draftOnlyLabel.className = 'checkbox-label';
        draftOnlyLabel.title = '勾选后文章仅保存到草稿箱，不自动发布';

        const draftOnlyCheckbox = document.createElement('input');
        draftOnlyCheckbox.type = 'checkbox';
        draftOnlyCheckbox.id = `wechat-draft-only-${index}`;
        draftOnlyCheckbox.checked = credential.draft_only || false;
        draftOnlyCheckbox.addEventListener('change', async (e) => {
            // 如果启用仅保存草稿，禁用群发选项
            const callSendallCheckbox = document.getElementById(`wechat-call-sendall-${index}`);
            const sendallCheckbox = document.getElementById(`wechat-sendall-${index}`);
            if (callSendallCheckbox) {
                callSendallCheckbox.disabled = e.target.checked;
            }
            if (sendallCheckbox) {
                sendallCheckbox.disabled = e.target.checked;
            }
            await this.updateWeChatCredential(index);
        });

        const draftOnlyCustom = document.createElement('span');
        draftOnlyCustom.className = 'checkbox-custom';

        const draftOnlyText = document.createTextNode('仅保存草稿');

        draftOnlyLabel.appendChild(draftOnlyCheckbox);
        draftOnlyLabel.appendChild(draftOnlyCustom);
        draftOnlyLabel.appendChild(draftOnlyText);
        draftOnlyGroup.appendChild(draftOnlyLabel);

        const draftOnlyHelp = document.createElement('small');
        draftOnlyHelp.className = 'form-help';
        draftOnlyHelp.textContent = '不自动发布，需后台手动发布';
        draftOnlyGroup.appendChild(draftOnlyHelp);

        // 启用群发复选框  
        const callSendallGroup = document.createElement('div');
        callSendallGroup.className = 'form-group';

        const callSendallLabel = document.createElement('label');
        callSendallLabel.className = 'checkbox-label';
        callSendallLabel.title = '1. 启用群发,群发才生效\n2. 否则不启用,需要网页后台群发';

        const callSendallCheckbox = document.createElement('input');
        callSendallCheckbox.type = 'checkbox';
        callSendallCheckbox.id = `wechat-call-sendall-${index}`;
        callSendallCheckbox.checked = credential.call_sendall || false;
        callSendallCheckbox.disabled = credential.draft_only || false;
        callSendallCheckbox.addEventListener('change', (e) => {
            this.updateSendallOptions(index, e.target.checked);
        });

        const callSendallCustom = document.createElement('span');
        callSendallCustom.className = 'checkbox-custom';

        const callSendallText = document.createTextNode('启用群发');

        callSendallLabel.appendChild(callSendallCheckbox);
        callSendallLabel.appendChild(callSendallCustom);
        callSendallLabel.appendChild(callSendallText);
        callSendallGroup.appendChild(callSendallLabel);

        const callSendallHelp = document.createElement('small');
        callSendallHelp.className = 'form-help';
        callSendallHelp.textContent = '仅对已认证公众号生效';
        callSendallGroup.appendChild(callSendallHelp);
        // 群发复选框  
        const sendallGroup = document.createElement('div');
        sendallGroup.className = 'form-group';

        const sendallLabel = document.createElement('label');
        sendallLabel.className = 'checkbox-label';
        sendallLabel.title = '1. 认证号群发数量有限,群发可控\n2. 非认证号,此选项无效(不支持群发)';

        // 群发复选框  
        const sendallCheckbox = document.createElement('input');
        sendallCheckbox.type = 'checkbox';
        sendallCheckbox.id = `wechat-sendall-${index}`;
        sendallCheckbox.checked = credential.sendall !== false;
        sendallCheckbox.disabled = !credential.call_sendall;
        sendallCheckbox.addEventListener('change', async (e) => {
            const tagIdInput = document.getElementById(`wechat-tag-id-${index}`);
            if (tagIdInput) {
                tagIdInput.disabled = e.target.checked;
            }
            await this.updateWeChatCredential(index);
        });

        const sendallCustom = document.createElement('span');
        sendallCustom.className = 'checkbox-custom';

        const sendallText = document.createTextNode('群发');

        sendallLabel.appendChild(sendallCheckbox);
        sendallLabel.appendChild(sendallCustom);
        sendallLabel.appendChild(sendallText);
        sendallGroup.appendChild(sendallLabel);

        const sendallHelp = document.createElement('small');
        sendallHelp.className = 'form-help';
        sendallHelp.textContent = '发送给所有关注者';
        sendallGroup.appendChild(sendallHelp);

        // 标签组ID部分  
        const tagIdGroup = this.createFormGroup(
            '标签组ID',
            'number',
            `wechat-tag-id-${index}`,
            credential.tag_id || 0,
            '群发的标签组ID'
        );
        const tagIdInput = tagIdGroup.querySelector('input');
        tagIdInput.classList.add('tag-id-input');  // 添加特定宽度类  
        // form-control类已经在createFormGroup中添加,确保高度一致  
        tagIdInput.disabled = !credential.call_sendall || credential.sendall !== false;
        tagIdInput.addEventListener('change', async () => {
            await this.updateWeChatCredential(index);
        });

        publishOptionsDiv.appendChild(draftOnlyGroup);
        publishOptionsDiv.appendChild(callSendallGroup);
        publishOptionsDiv.appendChild(sendallGroup);
        publishOptionsDiv.appendChild(tagIdGroup);
        row2.appendChild(publishOptionsDiv);

        // 组装表单  
        form.appendChild(row1);
        form.appendChild(statusRow);
        form.appendChild(row2);

        // 组装卡片  
        card.appendChild(header);
        card.appendChild(form);

        return card;
    }

    // 测试微信凭证
    async testWeChatCredential(index) {
        const appidInput = document.getElementById(`wechat-appid-${index}`);
        const appsecretInput = document.getElementById(`wechat-appsecret-${index}`);
        const statusDiv = document.getElementById(`wechat-status-${index}`);
        const testBtn = document.getElementById(`wechat-test-btn-${index}`);

        if (!appidInput || !appsecretInput) return;

        const appid = appidInput.value.trim();
        const appsecret = appsecretInput.value.trim();

        if (!appid || !appsecret) {
            window.app?.showNotification('请先填写AppID和AppSecret', 'warning');
            return;
        }

        // 显示测试中状态
        testBtn.disabled = true;
        testBtn.innerHTML = '<div class="status-spinner"></div><span>测试中...</span>';

        if (statusDiv) {
            statusDiv.style.display = 'flex';
            statusDiv.className = 'credential-status testing';
            statusDiv.innerHTML = '<div class="status-spinner"></div><span>正在验证...</span>';
        }

        try {
            const response = await fetch('/api/config/test-wechat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ appid, appsecret })
            });

            const result = await response.json();

            if (result.status === 'success') {
                testBtn.className = 'test-btn success';
                testBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    <span>验证成功</span>
                `;

                if (statusDiv) {
                    statusDiv.className = 'credential-status verified';
                    statusDiv.innerHTML = `
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                            <polyline points="22 4 12 14.01 9 11.01"/>
                        </svg>
                        <span>${result.message}</span>
                    `;
                }
            } else if (result.status === 'warning') {
                testBtn.className = 'test-btn';
                testBtn.style.borderColor = '#eab308';
                testBtn.style.color = '#eab308';
                testBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                        <line x1="12" y1="9" x2="12" y2="13"/>
                        <line x1="12" y1="17" x2="12.01" y2="17"/>
                    </svg>
                    <span>未认证</span>
                `;

                if (statusDiv) {
                    statusDiv.className = 'credential-status unverified';
                    statusDiv.innerHTML = `
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                        <span>${result.message}</span>
                    `;
                }
            } else {
                // v2: 微信检测到的真实IP，在抛异常前先更新IP显示
                if (result.details && result.details.server_ip) {
                    const ipDisplay = document.getElementById('server-outbound-ip');
                    if (ipDisplay) {
                        ipDisplay.textContent = result.details.server_ip;
                        ipDisplay.style.color = '#f59e0b'; // 橙色标识微信检测的IP
                        ipDisplay.title = '来源: 微信API检测 (真实IP)';
                    }
                }
                throw new Error(result.message);
            }

        } catch (error) {
            testBtn.className = 'test-btn error';
            testBtn.innerHTML = `
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="15" y1="9" x2="9" y2="15"/>
                    <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <span>验证失败</span>
            `;

            if (statusDiv) {
                statusDiv.className = 'credential-status error';
                statusDiv.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    <span>${error.message}</span>
                `;
            }
        } finally {
            testBtn.disabled = false;
        }
    }

    // 更新平台启用状态  
    async updatePlatformEnabled(index, enabled) {
        const platforms = [...this.config.platforms];
        platforms[index] = { ...platforms[index], enabled };

        await this.updateConfig({ platforms });

        // 更新权重输入框的禁用状态  
        const row = document.querySelector(`tr[data-platform-index="${index}"]`);
        if (row) {
            const weightInput = row.querySelector('.platform-weight-input');
            if (weightInput) {
                weightInput.disabled = !enabled;
            }
        }
    }

    // 更新平台权重  
    async updatePlatformWeight(index, weight) {
        const platforms = [...this.config.platforms];
        platforms[index] = { ...platforms[index], weight };

        await this.updateConfig({ platforms });
    }

    // 获取平台描述  
    getPlatformDescription(platformName) {
        const descriptions = {
            '微博': '社交媒体热搜话题',
            '抖音': '短视频平台热点',
            '小红书': '生活方式分享平台',
            '今日头条': '新闻资讯聚合',
            '百度热点': '搜索引擎热搜',
            '哔哩哔哩': '视频弹幕网站',
            '快手': '短视频社交平台',
            '虎扑': '体育社区论坛',
            '豆瓣小组': '文化兴趣社区',
            '澎湃新闻': '专业新闻媒体',
            '知乎热榜': '问答社区热榜'
        };
        return descriptions[platformName] || '热搜话题来源';
    }

    getLLMProviderDisplayName(key) {
        if (!key) return '未选择';
        if (key === 'SiliconFlow') return '硅基流动';
        const custom = (this.customAPIs || []).find(
            (c) => c && (c.provider_key === key || c.name === key)
        );
        if (custom?.name) return custom.name;
        if (key.startsWith('CustomAPI_')) return custom?.name || '自定义 API';
        return key;
    }

    getLLMProviderOptions() {
        const api = this.config?.api || {};
        const deleted = api.deleted_providers || [];
        const options = [];
        const seen = new Set();

        Object.keys(api).forEach((key) => {
            if (key === 'api_type' || key === 'deleted_providers' || key === 'custom') return;
            if (deleted.includes(key)) return;
            if (seen.has(key)) return;
            seen.add(key);
            const customIndex = (api.custom || []).findIndex(
                (c) => c && c.provider_key === key
            );
            options.push({
                key,
                display: this.getLLMProviderDisplayName(key),
                kind: customIndex >= 0 ? 'custom' : 'builtin',
                customIndex: customIndex >= 0 ? customIndex : undefined,
            });
        });

        (api.custom || []).forEach((entry, index) => {
            if (!entry) return;
            const key = entry.provider_key;
            if (key && seen.has(key)) return;
            if (!key) {
                const virtualKey = `__custom_index_${index}`;
                options.push({
                    key: virtualKey,
                    display: entry.name || `自定义 API ${index + 1}`,
                    kind: 'custom',
                    customIndex: index,
                });
            }
        });

        options.sort((a, b) => {
            if (a.kind !== b.kind) return a.kind === 'builtin' ? -1 : 1;
            return a.display.localeCompare(b.display, 'zh-CN');
        });
        return options;
    }

    resolveAPIProviderOption(selectedKey) {
        return this.getLLMProviderOptions().find((p) => p.key === selectedKey);
    }

    isAPIProviderCurrent(option, currentAPIType) {
        if (!option || !currentAPIType) return false;
        if (option.kind === 'custom' && option.customIndex !== undefined) {
            const entry = this.customAPIs[option.customIndex];
            const key = entry?.provider_key || option.key;
            return currentAPIType === key;
        }
        return currentAPIType === option.key;
    }

    renderAPIProviderToolbar(providers, currentAPIType) {
        const toolbar = document.getElementById('api-provider-toolbar');
        if (!toolbar) return;

        if (!providers.length) {
            toolbar.innerHTML = `
                <div class="llm-api-toolbar-empty">
                    <p>暂无可用厂商</p>
                    <button type="button" class="btn btn-primary btn-sm" id="add-custom-api-btn">+ 添加自定义 API</button>
                </div>
            `;
            toolbar.querySelector('#add-custom-api-btn')?.addEventListener('click', () => this.addCustomAPI());
            return;
        }

        const selectedKey = this._selectedAPIProvider;
        const selected = providers.find((p) => p.key === selectedKey) || providers[0];
        this._selectedAPIProvider = selected.key;
        const isCurrent = this.isAPIProviderCurrent(selected, currentAPIType);
        const isCustom = selected.kind === 'custom';

        const optionsHtml = providers
            .map((p) => {
                const active = this.isAPIProviderCurrent(p, currentAPIType);
                const tag = p.kind === 'custom' ? ' [自定义]' : '';
                const suffix = active ? ' ✓' : '';
                return `<option value="${p.key}" ${p.key === selected.key ? 'selected' : ''}>${p.display}${tag}${suffix}</option>`;
            })
            .join('');

        const currentLabel = this.getLLMProviderDisplayName(currentAPIType);
        const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

        toolbar.innerHTML = `
            <div class="llm-api-toolbar-grid">
                <div class="llm-api-toolbar-main">
                    <label class="llm-api-picker-label" for="api-provider-select">配置厂商</label>
                    <select id="api-provider-select" class="form-control llm-api-provider-select" aria-label="选择大模型厂商">${optionsHtml}</select>
                    <div class="llm-api-status-chip ${isCurrent ? 'is-active' : ''}" role="status">
                        <span class="llm-api-status-dot" aria-hidden="true"></span>
                        <div class="llm-api-status-copy">
                            <span class="llm-api-status-name">${esc(selected.display)}</span>
                            <span class="llm-api-status-meta">${isCurrent ? '写作中使用' : '未设为当前'}</span>
                        </div>
                    </div>
                </div>
                <div class="llm-api-toolbar-actions">
                    <button type="button" class="btn btn-primary btn-sm" id="set-current-api-provider" ${isCurrent ? 'disabled' : ''}>
                        ${isCurrent ? '✓ 当前使用' : '设为当前使用'}
                    </button>
                    <button type="button" class="btn btn-secondary btn-sm" id="test-api-provider">测试连接</button>
                    <button type="button" class="btn btn-ghost btn-sm" id="add-custom-api-btn">+ 自定义</button>
                    <button type="button" class="btn btn-ghost btn-sm llm-api-btn-danger" id="delete-api-provider" title="删除当前厂商配置">删除</button>
                </div>
            </div>
            <div class="llm-api-global-bar">
                <span class="llm-api-global-label">全局写作</span>
                <strong id="current-api-type-label" class="llm-api-global-value">${esc(currentLabel)}</strong>
                <span class="llm-api-global-sep">·</span>
                <span class="llm-api-global-hint">${isCustom ? 'OpenAI 兼容接口' : '内置厂商'} · 切换下拉不丢失已填内容</span>
            </div>
        `;

        toolbar.querySelector('#api-provider-select')?.addEventListener('change', (e) => {
            this._selectedAPIProvider = e.target.value;
            this.populateAPIUI();
        });
        toolbar.querySelector('#set-current-api-provider')?.addEventListener('click', () => {
            this.applySelectedAsCurrentAPI();
        });
        toolbar.querySelector('#test-api-provider')?.addEventListener('click', () => {
            this.testSelectedAPIProvider();
        });
        toolbar.querySelector('#delete-api-provider')?.addEventListener('click', () => {
            this.deleteSelectedAPIProvider();
        });
        toolbar.querySelector('#add-custom-api-btn')?.addEventListener('click', () => {
            this.addCustomAPI();
        });
    }

    createLLMFormSection(title, description = '') {
        const section = document.createElement('section');
        section.className = 'api-form-section';
        const head = document.createElement('div');
        head.className = 'api-form-section-head';
        const titleEl = document.createElement('h4');
        titleEl.className = 'api-form-section-title';
        titleEl.textContent = title;
        head.appendChild(titleEl);
        if (description) {
            const desc = document.createElement('p');
            desc.className = 'api-form-section-desc';
            desc.textContent = description;
            head.appendChild(desc);
        }
        const body = document.createElement('div');
        body.className = 'api-form-section-body';
        section.appendChild(head);
        section.appendChild(body);
        return { section, body };
    }

    async applySelectedAsCurrentAPI() {
        const option = this.resolveAPIProviderOption(this._selectedAPIProvider);
        if (!option) return;
        if (option.kind === 'custom' && option.customIndex !== undefined) {
            await this.setCurrentCustomAPI(option.customIndex);
            return;
        }
        await this.setCurrentAPIProvider(option.key);
    }

    _setToolbarTestButtonLoading(loading) {
        const btn = document.getElementById('test-api-provider');
        if (!btn) return;
        if (loading) {
            if (!btn.dataset.defaultLabel) {
                btn.dataset.defaultLabel = btn.textContent.trim();
            }
            btn.disabled = true;
            btn.textContent = '测试中…';
        } else {
            btn.disabled = false;
            btn.textContent = btn.dataset.defaultLabel || '测试连接';
        }
    }

    async testSelectedAPIProvider() {
        const option = this.resolveAPIProviderOption(this._selectedAPIProvider);
        if (!option) {
            window.app?.showNotification('请先选择要测试的厂商', 'warning');
            return;
        }

        this._setToolbarTestButtonLoading(true);
        try {
            if (option.kind === 'custom' && option.customIndex !== undefined) {
                await this.testCustomAPI(option.customIndex, { fromToolbar: true });
            } else {
                await this.testBuiltinAPIProvider(option.key);
            }
        } catch (error) {
            console.error('测试 API 失败:', error);
            window.app?.showNotification(`测试失败: ${error.message || error}`, 'error');
        } finally {
            this._setToolbarTestButtonLoading(false);
        }
    }

    async testBuiltinAPIProvider(providerKey) {
        const providerData = this.config?.api?.[providerKey];
        if (!providerData) {
            window.app?.showNotification('未找到该厂商配置', 'error');
            return;
        }

        const apiKeys = providerData.api_key || [];
        const keyIndex = Number(providerData.key_index) || 0;
        const apiKey = (apiKeys[keyIndex] || apiKeys[0] || '').trim();
        const apiBase = (providerData.api_base || '').trim();
        const models = providerData.model || [];
        const modelIndex = Number(providerData.model_index) || 0;
        const model = (models[modelIndex] || models[0] || '').trim();

        if (!apiKey) {
            window.app?.showNotification('请先添加并选中 API KEY（在 API KEY 下拉框中点「点击添加」）', 'warning');
            return;
        }
        if (!apiBase) {
            window.app?.showNotification('缺少 API Base 地址', 'warning');
            return;
        }

        const response = await fetch('/api/config/test-custom-api', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: providerKey,
                api_base: apiBase,
                api_key: apiKey,
                model: model || 'gpt-3.5-turbo',
                provider: providerData.provider || 'openai',
            }),
        });

        const result = await response.json().catch(() => ({}));
        if (result.status === 'success') {
            window.app?.showNotification(result.message || '连接成功', 'success');
            try {
                await this.fetchAPIModels(providerKey, { quietSuccess: true });
            } catch (_) {
                /* 拉取模型列表失败不影响连通性结果 */
            }
            return;
        }

        window.app?.showNotification(result.message || '连接失败，请检查 Key 与 Base URL', 'error');
    }

    async deleteSelectedAPIProvider() {
        const option = this.resolveAPIProviderOption(this._selectedAPIProvider);
        if (!option) return;
        const label = option.display;
        if (!confirm(`确定要删除「${label}」的配置吗？\n\n删除后可通过「恢复默认」找回内置厂商。`)) {
            return;
        }
        if (option.kind === 'custom' && option.customIndex !== undefined) {
            await this.deleteCustomAPI(option.customIndex);
            return;
        }
        await this.deleteAPIProvider(option.key);
    }

    // 填充大模型API UI（下拉选择厂商，仅展示当前厂商表单）
    populateAPIUI() {
        this.initCustomAPIs();

        const container = document.getElementById('api-providers-container');
        if (!container || !this.config.api) return;

        const currentAPIType = this.config.api.api_type;
        const providers = this.getLLMProviderOptions();

        if (
            !this._selectedAPIProvider
            || !providers.some((p) => p.key === this._selectedAPIProvider)
        ) {
            const preferred = providers.find((p) => this.isAPIProviderCurrent(p, currentAPIType));
            this._selectedAPIProvider = preferred?.key || providers[0]?.key || null;
        }

        this.renderAPIProviderToolbar(providers, currentAPIType);

        container.innerHTML = '';
        if (!providers.length) return;

        const selected = this.resolveAPIProviderOption(this._selectedAPIProvider);
        if (!selected) return;

        if (selected.kind === 'custom' && selected.customIndex !== undefined) {
            const entry = this.customAPIs[selected.customIndex];
            if (entry) {
                const card = this.createCustomAPICard(entry, selected.customIndex, true);
                container.appendChild(card);
            }
            return;
        }

        const providerData = this.config.api[selected.key];
        if (providerData) {
            const card = this.createAPIProviderCard(
                selected.key,
                selected.display,
                providerData,
                currentAPIType,
                true
            );
            container.appendChild(card);
        }
    }

    // 创建API提供商卡片
    createAPIProviderCard(providerKey, providerDisplay, providerData, currentAPIType, compactToolbar = false) {
        const card = document.createElement('div');
        card.className = 'api-provider-card llm-api-detail-card';
        if (providerKey === currentAPIType) {
            card.classList.add('active');
        }

        const header = document.createElement('div');
        header.className = 'provider-header';

        if (!compactToolbar) {
            const titleGroup = document.createElement('div');
            titleGroup.className = 'provider-title-group';
            const name = document.createElement('div');
            name.className = 'provider-name';
            name.textContent = providerDisplay;
            const badge = document.createElement('span');
            badge.className = `provider-badge ${providerKey === currentAPIType ? 'active' : 'inactive'}`;
            badge.textContent = providerKey === currentAPIType ? '当前使用' : '未使用';
            titleGroup.appendChild(name);
            titleGroup.appendChild(badge);
            header.appendChild(titleGroup);

            const toggleBtn = document.createElement('button');
            toggleBtn.className = `provider-toggle-btn ${providerKey === currentAPIType ? 'active' : ''}`;
            toggleBtn.textContent = providerKey === currentAPIType ? '当前使用' : '设为当前';
            toggleBtn.disabled = providerKey === currentAPIType;
            toggleBtn.addEventListener('click', async () => {
                await this.setCurrentAPIProvider(providerKey);
            });

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'provider-delete-btn';
            deleteBtn.textContent = '删除';
            deleteBtn.title = '删除此API提供商';
            deleteBtn.onclick = async () => {
                if (confirm(`确定要删除 "${providerDisplay}" API吗？\n\n删除后可通过恢复默认恢复。`)) {
                    await this.deleteAPIProvider(providerKey);
                }
            };
            header.appendChild(toggleBtn);
            header.appendChild(deleteBtn);
        }

        const form = document.createElement('div');
        form.className = 'provider-form llm-api-form';

        // 行1: KEY名称和API BASE同一行,各占一半  
        const row1 = document.createElement('div');
        row1.className = 'form-row';

        const keyNameGroup = this.createFormGroup(
            'KEY名称',
            'text',
            `api-${providerKey}-key-name`,
            providerData.key || '',
            '',
            false,
            true  // 只读  
        );
        keyNameGroup.classList.add('form-group-half');

        const apiBaseGroup = this.createFormGroup(
            'API BASE',
            'text',
            `api-${providerKey}-api-base`,
            providerData.api_base || '',
            '',
            false,
            true  // 只读  
        );
        apiBaseGroup.classList.add('form-group-half');

        /*
        const keyNameGroup = this.createFormGroup(    
            'KEY名称',    
            'text',    
            `api-${providerKey}-key-name`,    
            providerData.key || '',    
            '',    
            false,    
            false
        );    
        keyNameGroup.classList.add('form-group-half');  
        const keyNameInput = keyNameGroup.querySelector('input');  
        if (keyNameInput) {  
            keyNameInput.disabled = true;  
            keyNameInput.style.userSelect = 'none';  
            keyNameInput.style.cursor = 'not-allowed';  
        }  
        
        const apiBaseGroup = this.createFormGroup(    
            'API BASE',    
            'text',    
            `api-${providerKey}-api-base`,    
            providerData.api_base || '',    
            '',    
            false,    
            false  
        );    
        apiBaseGroup.classList.add('form-group-half');  
        const apiBaseInput = apiBaseGroup.querySelector('input');  
        if (apiBaseInput) {  
            apiBaseInput.disabled = true;  
            apiBaseInput.style.userSelect = 'none';  
            apiBaseInput.style.cursor = 'not-allowed';  
        }
         */
        row1.appendChild(keyNameGroup);
        row1.appendChild(apiBaseGroup);

        // 行2: KEY选择和模型选择同一行,各占一半  
        const row2 = document.createElement('div');
        row2.className = 'form-row';

        // 左侧: KEY选择  
        const keySelectGroup = document.createElement('div');
        keySelectGroup.className = 'form-group form-group-half';

        const keySelectLabel = document.createElement('label');
        keySelectLabel.textContent = 'API KEY';
        const keyRequiredSpan = document.createElement('span');
        keyRequiredSpan.className = 'required';
        keyRequiredSpan.textContent = ' *';
        keySelectLabel.appendChild(keyRequiredSpan);

        const keySelect = this.createEditableSelect(
            providerKey,
            'API KEY',
            providerData.api_key || [],
            providerData.key_index || 0
        );

        keySelectGroup.appendChild(keySelectLabel);
        keySelectGroup.appendChild(keySelect);

        // 右侧: 模型选择  
        const modelSelectGroup = document.createElement('div');
        modelSelectGroup.className = 'form-group form-group-half';

        const modelSelectLabel = document.createElement('label');
        modelSelectLabel.className = 'model-label-with-refresh';
        modelSelectLabel.innerHTML = `
            <span>模型 <span class="required">*</span></span>
            <button type="button" class="model-refresh-btn-inline" onclick="window.configManager.fetchAPIModels('${providerKey}')" title="检测/刷新模型列表">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
            </button>
        `;
        // modelSelectLabel.textContent = '模型';
        // const modelRequiredSpan = document.createElement('span');
        // modelRequiredSpan.className = 'required';
        // modelRequiredSpan.textContent = ' *';
        // modelSelectLabel.appendChild(modelRequiredSpan);

        const modelSelect = this.createEditableSelect(
            providerKey,
            '模型',
            providerData.model || [],
            providerData.model_index || 0
        );

        modelSelectGroup.appendChild(modelSelectLabel);
        modelSelectGroup.appendChild(modelSelect);

        row2.appendChild(keySelectGroup);
        row2.appendChild(modelSelectGroup);

        // 行3: 视觉模型选择（占一半满宽即可，或者可以和其他放一起，这里独占一行左半）
        const row3 = document.createElement('div');
        row3.className = 'form-row';

        const visionModelSelectGroup = document.createElement('div');
        visionModelSelectGroup.className = 'form-group form-group-half';

        const visionModelSelectLabel = document.createElement('label');
        visionModelSelectLabel.textContent = '视觉模型（可选）';

        const visionModelSelect = this.createEditableSelect(
            providerKey,
            '视觉模型',
            providerData.vision_model || [],
            providerData.vision_model_index || 0
        );

        visionModelSelectGroup.appendChild(visionModelSelectLabel);
        visionModelSelectGroup.appendChild(visionModelSelect);

        row3.appendChild(visionModelSelectGroup);

        // 备用模型选择（与视觉模型同行，右侧）
        const fallbackModelSelectGroup = document.createElement('div');
        fallbackModelSelectGroup.className = 'form-group form-group-half';

        const fallbackModelSelectLabel = document.createElement('label');
        fallbackModelSelectLabel.textContent = '备用模型（可选）';
        fallbackModelSelectLabel.title = '当主模型调用失败时自动切换到此模型';

        const fallbackIndex = providerData.fallback_model_index ?? -1;
        const fallbackModelSelect = this.createEditableSelect(
            providerKey,
            '备用模型',
            providerData.model || [],
            fallbackIndex
        );

        fallbackModelSelectGroup.appendChild(fallbackModelSelectLabel);
        fallbackModelSelectGroup.appendChild(fallbackModelSelect);

        row3.appendChild(fallbackModelSelectGroup);

        // 行4: 模板设计模型 和 语义精修模型 (V11.2 新增)
        const row4 = document.createElement('div');
        row4.className = 'form-row';

        // 左侧: 模板设计模型
        const designerModelSelectGroup = document.createElement('div');
        designerModelSelectGroup.className = 'form-group form-group-half';

        const designerModelSelectLabel = document.createElement('label');
        designerModelSelectLabel.textContent = '模板设计模型';
        designerModelSelectLabel.title = '专门用于生成视觉模板和设计方案的模型';

        const designerIndex = providerData.designer_model_index ?? -1;
        const designerModelSelect = this.createEditableSelect(
            providerKey,
            '模板设计模型',
            providerData.model || [],
            designerIndex
        );

        designerModelSelectGroup.appendChild(designerModelSelectLabel);
        designerModelSelectGroup.appendChild(designerModelSelect);

        // 右侧: 语义精修模型
        const refinerModelSelectGroup = document.createElement('div');
        refinerModelSelectGroup.className = 'form-group form-group-half';

        const refinerModelSelectLabel = document.createElement('label');
        refinerModelSelectLabel.textContent = '语义精修模型';
        refinerModelSelectLabel.title = '用于对生成的内容进行深度加工、润色和纠错的模型';

        const refinerIndex = providerData.refiner_model_index ?? -1;
        const refinerModelSelect = this.createEditableSelect(
            providerKey,
            '语义精修模型',
            providerData.model || [],
            refinerIndex
        );

        refinerModelSelectGroup.appendChild(refinerModelSelectLabel);
        refinerModelSelectGroup.appendChild(refinerModelSelect);

        row4.appendChild(designerModelSelectGroup);
        row4.appendChild(refinerModelSelectGroup);

        if (compactToolbar) {
            keySelectGroup.classList.remove('form-group-half');
            keySelectGroup.classList.add('form-group-full');
            modelSelectGroup.classList.remove('form-group-half');
            modelSelectGroup.classList.add('form-group-full');

            const keyOnlyRow = document.createElement('div');
            keyOnlyRow.className = 'form-row';
            keyOnlyRow.appendChild(keySelectGroup);

            const connSec = this.createLLMFormSection(
                '连接与认证',
                '点击 API KEY 添加密钥（一行一个）；下方为厂商预设接口信息'
            );
            connSec.body.appendChild(keyOnlyRow);
            row1.classList.add('api-endpoint-meta');
            connSec.body.appendChild(row1);

            const modelSec = this.createLLMFormSection(
                '模型',
                '主模型用于写稿；点击刷新可拉取厂商可用模型列表'
            );
            const modelRow = document.createElement('div');
            modelRow.className = 'form-row';
            modelRow.appendChild(modelSelectGroup);
            modelSec.body.appendChild(modelRow);

            const advDetails = document.createElement('details');
            advDetails.className = 'api-form-advanced';
            advDetails.innerHTML = '<summary>高级选项（视觉 / 备用 / 模板 / 精修）</summary>';
            advDetails.appendChild(row3);
            advDetails.appendChild(row4);

            form.appendChild(connSec.section);
            form.appendChild(modelSec.section);
            form.appendChild(advDetails);
        } else {
            form.appendChild(row1);
            form.appendChild(row2);
            form.appendChild(row3);
            form.appendChild(row4);
        }

        if (!compactToolbar) {
            card.appendChild(header);
        }
        card.appendChild(form);

        return card;
    }

    // 创建自定义下拉框  
    createEditableSelect(providerKey, type, items, selectedIndex) {
        const container = document.createElement('div');
        container.className = 'editable-select';

        const validItems = items.filter(item => item && item.trim() !== '');

        // 当前选中值显示  
        const display = document.createElement('div');
        display.className = 'select-display';
        // 如果选中的是空字符串或索引超出有效范围,显示"-- 点击添加 --"  
        const selectedItem = validItems[selectedIndex];
        const isOrchestrationModel = type === '备用模型' || type === '模板设计模型' || type === '语义精修模型';
        display.textContent = selectedItem || (isOrchestrationModel ? '-- 默认为主模型 --' : '-- 点击添加 --');

        // 下拉选项容器  
        const dropdown = document.createElement('div');
        dropdown.className = 'select-dropdown';
        dropdown.style.display = 'none';

        const closeDropdown = () => {
            dropdown.style.display = 'none';
            dropdown.classList.remove('is-fixed');
            dropdown.style.top = '';
            dropdown.style.left = '';
            dropdown.style.width = '';
            dropdown.style.maxHeight = '';
            if (dropdown.parentElement === document.body) {
                container.appendChild(dropdown);
            }
            window.removeEventListener('scroll', closeDropdown, true);
            window.removeEventListener('resize', closeDropdown);
        };

        const positionDropdown = () => {
            const rect = display.getBoundingClientRect();
            const gap = 4;
            const maxH = Math.min(360, Math.floor(window.innerHeight * 0.5));
            dropdown.style.width = `${Math.max(rect.width, 160)}px`;
            dropdown.style.left = `${rect.left}px`;
            dropdown.style.maxHeight = `${maxH}px`;
            const dropdownHeight = Math.min(dropdown.scrollHeight, maxH);
            const spaceBelow = window.innerHeight - rect.bottom - gap;
            const spaceAbove = rect.top - gap;
            if (dropdownHeight > spaceBelow && spaceAbove >= spaceBelow) {
                dropdown.style.top = `${Math.max(gap, rect.top - dropdownHeight - gap)}px`;
            } else {
                dropdown.style.top = `${rect.bottom + gap}px`;
            }
        };

        const openDropdown = () => {
            renderOptions();
            document.body.appendChild(dropdown);
            dropdown.classList.add('is-fixed');
            dropdown.style.display = 'block';
            positionDropdown();
            window.addEventListener('scroll', closeDropdown, true);
            window.addEventListener('resize', closeDropdown);
        };

        // 渲染选项列表  
        const renderOptions = () => {
            dropdown.innerHTML = '';

            const addOption = document.createElement('div');
            addOption.className = 'select-option select-option-add';
            if (type === '备用模型' || type === '模板设计模型' || type === '语义精修模型') {
                addOption.textContent = '-- 默认为主模型 --';
                addOption.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    display.textContent = '-- 默认为主模型 --';
                    closeDropdown();

                    let fieldName = '';
                    if (type === '模板设计模型') fieldName = 'designer_model_index';
                    else if (type === '语义精修模型') fieldName = 'refiner_model_index';
                    else fieldName = 'fallback_model_index';

                    await this.updateConfig({
                        api: {
                            [providerKey]: {
                                ...this.config.api[providerKey],
                                [fieldName]: -1
                            }
                        }
                    });
                });
            } else {
                addOption.textContent = '-- 点击添加 --';
                addOption.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showAddInput();
                });
            }
            dropdown.appendChild(addOption);

            // 现有选项  
            validItems.forEach((item, index) => {
                const option = document.createElement('div');
                option.className = 'select-option';
                option.textContent = item;

                // 点击选项  
                option.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    display.textContent = item;
                    closeDropdown();

                    const originalIndex = items.indexOf(item);
                    let fieldName = '';
                    if (type === 'API KEY') fieldName = 'key_index';
                    else if (type === '视觉模型') fieldName = 'vision_model_index';
                    else if (type === '备用模型') fieldName = 'fallback_model_index';
                    else if (type === '模板设计模型') fieldName = 'designer_model_index';
                    else if (type === '语义精修模型') fieldName = 'refiner_model_index';
                    else fieldName = 'model_index';

                    await this.updateConfig({
                        api: {
                            [providerKey]: {
                                ...this.config.api[providerKey],
                                [fieldName]: originalIndex
                            }
                        }
                    });
                });

                // 右键菜单  
                option.addEventListener('contextmenu', (e) => {
                    const originalIndex = items.indexOf(item);
                    this.showContextMenu(e, providerKey, type, originalIndex, item);
                });

                dropdown.appendChild(option);
            });
        };

        // 显示添加输入框  
        const showAddInput = () => {
            dropdown.innerHTML = '';

            const isKeyType = type === 'API KEY';
            const input = document.createElement(isKeyType ? 'textarea' : 'input');
            if (!isKeyType) input.type = 'text';
            input.className = isKeyType ? 'select-textarea' : 'select-input';
            input.placeholder = isKeyType ? '输入API Key，一行一个支持负载均衡' : `输入新的${type}`;
            if (isKeyType) {
                input.rows = 5;
                // 如果是 API KEY，填充当前所有 key（换行分隔）
                input.value = items.join('\n');
            }

            // 监听保存
            const handleSave = async () => {
                const rawValue = input.value.trim();
                if (rawValue) {
                    if (isKeyType) {
                        // 一行一个，过滤空行
                        const newKeys = rawValue.split('\n').map(k => k.trim()).filter(k => k !== '');
                        await this.setAPIKeys(providerKey, newKeys);
                    } else {
                        if (type === '视觉模型') {
                            await this.addVisionModel(providerKey, rawValue);
                        } else {
                            await this.addModel(providerKey, rawValue);
                        }
                    }
                    closeDropdown();
                }
            };

            input.addEventListener('keydown', async (e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey || !isKeyType)) {
                    await handleSave();
                } else if (e.key === 'Escape') {
                    renderOptions();
                }
            });

            input.addEventListener('blur', async () => {
                if (isKeyType) {
                    await handleSave();
                } else if (!input.value.trim()) {
                    renderOptions();
                }
            });

            input.addEventListener('click', (e) => {
                e.stopPropagation();
            });

            dropdown.appendChild(input);
            setTimeout(() => input.focus(), 0);
            if (dropdown.classList.contains('is-fixed')) {
                positionDropdown();
            }
        };

        // 初始化选项  
        renderOptions();

        // 点击显示框切换下拉框  
        display.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // 如果是API KEY类型，弹出大窗口编辑框
            if (type === 'API KEY') {
                this.showAPIKeyEditor(providerKey, items);
                return;
            }
            
            const isVisible = dropdown.style.display === 'block';
            if (isVisible) {
                closeDropdown();
            } else {
                openDropdown();
            }
        });

        // 点击外部关闭  
        document.addEventListener('click', (e) => {
            if (!container.contains(e.target) && !dropdown.contains(e.target)) {
                closeDropdown();
            }
        });

        container.appendChild(display);
        container.appendChild(dropdown);

        return container;
    }

    // 显示API Key编辑弹窗（大窗口模式）
    showAPIKeyEditor(providerKey, currentKeys) {
        // 移除已存在的弹窗
        const existingModal = document.getElementById('api-key-editor-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // 创建弹窗遮罩
        const modalOverlay = document.createElement('div');
        modalOverlay.id = 'api-key-editor-modal';
        modalOverlay.className = 'modal-overlay';
        modalOverlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';

        // 创建弹窗容器
        const modal = document.createElement('div');
        modal.className = 'modal-content';
        modal.style.cssText = 'background:#fff;border-radius:8px;width:600px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 4px 20px rgba(0,0,0,0.3);';

        // 标题栏
        const header = document.createElement('div');
        header.style.cssText = 'padding:16px 20px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;';
        header.innerHTML = `
            <h3 style="margin:0;font-size:16px;color:#333;">编辑 API KEY</h3>
            <button class="modal-close-btn" style="background:none;border:none;font-size:20px;cursor:pointer;color:#999;padding:0;width:30px;height:30px;">×</button>
        `;

        // 提示文字
        const hint = document.createElement('div');
        hint.style.cssText = 'padding:12px 20px;background:#fffbe6;border-bottom:1px solid #ffe58f;font-size:12px;color:#666;';
        hint.innerHTML = '💡 <strong>提示：</strong>一行一个KEY，支持自动负载均衡。当第一个KEY失效时会自动切换到下一个。';

        // 内容区域（带行号）
        const content = document.createElement('div');
        content.style.cssText = 'padding:20px;flex:1;overflow:hidden;display:flex;';

        // 行号容器
        const lineNumbers = document.createElement('div');
        lineNumbers.id = 'key-editor-line-numbers';
        lineNumbers.style.cssText = 'width:40px;background:#f5f5f5;border-right:1px solid #ddd;padding:12px 8px;text-align:right;color:#999;font-size:13px;line-height:1.6;user-select:none;overflow-y:auto;font-family:monospace;';
        lineNumbers.textContent = '1';

        // 文本区域
        const textarea = document.createElement('textarea');
        textarea.id = 'key-editor-textarea';
        textarea.style.cssText = 'flex:1;border:1px solid #ddd;border-left:none;padding:12px;font-size:13px;line-height:1.6;resize:none;outline:none;font-family:monospace;';
        textarea.placeholder = '在此输入API KEY，一行一个...';
        textarea.value = currentKeys.join('\n');

        // 更新行号
        const updateLineNumbers = () => {
            const lines = textarea.value.split('\n').length;
            let nums = '';
            for (let i = 1; i <= lines; i++) {
                nums += i + '\n';
            }
            lineNumbers.textContent = nums;
        };
        textarea.addEventListener('input', updateLineNumbers);
        textarea.addEventListener('scroll', () => {
            lineNumbers.scrollTop = textarea.scrollTop;
        });
        updateLineNumbers();

        content.appendChild(lineNumbers);
        content.appendChild(textarea);

        // 按钮栏
        const footer = document.createElement('div');
        footer.style.cssText = 'padding:16px 20px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:12px;';
        footer.innerHTML = `
            <button class="modal-cancel-btn" style="padding:8px 20px;border:1px solid #ddd;background:#fff;border-radius:4px;cursor:pointer;font-size:14px;">取消</button>
            <button class="modal-confirm-btn" style="padding:8px 20px;border:none;background:#1890ff;color:#fff;border-radius:4px;cursor:pointer;font-size:14px;">确定</button>
        `;

        // 组装弹窗
        modal.appendChild(header);
        modal.appendChild(hint);
        modal.appendChild(content);
        modal.appendChild(footer);
        modalOverlay.appendChild(modal);
        document.body.appendChild(modalOverlay);

        // 事件处理
        const closeModal = () => {
            modalOverlay.remove();
        };

        const confirmSave = async () => {
            const rawValue = textarea.value.trim();
            const newKeys = rawValue.split('\n').map(k => k.trim()).filter(k => k !== '');
            await this.setAPIKeys(providerKey, newKeys);
            closeModal();
        };

        header.querySelector('.modal-close-btn').addEventListener('click', closeModal);
        footer.querySelector('.modal-cancel-btn').addEventListener('click', closeModal);
        footer.querySelector('.modal-confirm-btn').addEventListener('click', confirmSave);
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });

        // 聚焦文本框
        setTimeout(() => textarea.focus(), 100);
    }

    // 显示图片API Key编辑弹窗（大窗口模式）
    showImgAPIKeyEditor(providerKey, currentKeys) {
        // 移除已存在的弹窗
        const existingModal = document.getElementById('img-api-key-editor-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // 创建弹窗遮罩
        const modalOverlay = document.createElement('div');
        modalOverlay.id = 'img-api-key-editor-modal';
        modalOverlay.className = 'modal-overlay';
        modalOverlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';

        // 创建弹窗容器
        const modal = document.createElement('div');
        modal.className = 'modal-content';
        modal.style.cssText = 'background:#fff;border-radius:8px;width:600px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 4px 20px rgba(0,0,0,0.3);';

        // 标题栏
        const header = document.createElement('div');
        header.style.cssText = 'padding:16px 20px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;';
        header.innerHTML = `
            <h3 style="margin:0;font-size:16px;color:#333;">编辑图片API KEY</h3>
            <button class="modal-close-btn" style="background:none;border:none;font-size:20px;cursor:pointer;color:#999;padding:0;width:30px;height:30px;">×</button>
        `;

        // 提示文字
        const hint = document.createElement('div');
        hint.style.cssText = 'padding:12px 20px;background:#fffbe6;border-bottom:1px solid #ffe58f;font-size:12px;color:#666;';
        hint.innerHTML = '💡 <strong>提示：</strong>一行一个KEY，支持自动负载均衡。当第一个KEY失效时会自动切换到下一个。';

        // 内容区域（带行号）
        const content = document.createElement('div');
        content.style.cssText = 'padding:20px;flex:1;overflow:hidden;display:flex;';

        // 行号容器
        const lineNumbers = document.createElement('div');
        lineNumbers.id = 'img-key-editor-line-numbers';
        lineNumbers.style.cssText = 'width:40px;background:#f5f5f5;border-right:1px solid #ddd;padding:12px 8px;text-align:right;color:#999;font-size:13px;line-height:1.6;user-select:none;overflow-y:auto;font-family:monospace;';
        lineNumbers.textContent = '1';

        // 文本区域
        const textarea = document.createElement('textarea');
        textarea.id = 'img-key-editor-textarea';
        textarea.style.cssText = 'flex:1;border:1px solid #ddd;border-left:none;padding:12px;font-size:13px;line-height:1.6;resize:none;outline:none;font-family:monospace;';
        textarea.placeholder = '在此输入API KEY，一行一个...';
        textarea.value = currentKeys.join('\n');

        // 更新行号
        const updateLineNumbers = () => {
            const lines = textarea.value.split('\n').length;
            let nums = '';
            for (let i = 1; i <= lines; i++) {
                nums += i + '\n';
            }
            lineNumbers.textContent = nums;
        };
        textarea.addEventListener('input', updateLineNumbers);
        textarea.addEventListener('scroll', () => {
            lineNumbers.scrollTop = textarea.scrollTop;
        });
        updateLineNumbers();

        content.appendChild(lineNumbers);
        content.appendChild(textarea);

        // 按钮栏
        const footer = document.createElement('div');
        footer.style.cssText = 'padding:16px 20px;border-top:1px solid #eee;display:flex;justify-content:flex-end;gap:12px;';
        footer.innerHTML = `
            <button class="modal-cancel-btn" style="padding:8px 20px;border:1px solid #ddd;background:#fff;border-radius:4px;cursor:pointer;font-size:14px;">取消</button>
            <button class="modal-confirm-btn" style="padding:8px 20px;border:none;background:#1890ff;color:#fff;border-radius:4px;cursor:pointer;font-size:14px;">确定</button>
        `;

        // 组装弹窗
        modal.appendChild(header);
        modal.appendChild(hint);
        modal.appendChild(content);
        modal.appendChild(footer);
        modalOverlay.appendChild(modal);
        document.body.appendChild(modalOverlay);

        // 事件处理
        const closeModal = () => {
            modalOverlay.remove();
        };

        const confirmSave = async () => {
            const rawValue = textarea.value.trim();
            const newKeys = rawValue.split('\n').map(k => k.trim()).filter(k => k !== '');
            const apiKeyValue = newKeys.join('\n');
            
            // 更新到配置
            await this.updateImgAPIField(providerKey, 'api_key', apiKeyValue);
            
            // 同时更新DOM中的输入框显示
            const inputEl = document.getElementById(`img-api-${providerKey}-api-key`);
            if (inputEl) {
                inputEl.value = apiKeyValue;
                inputEl.classList.add('masked');
                const keyCount = newKeys.length;
                const statusText =
                    keyCount > 1 ? `已配置（${keyCount} 个）` : keyCount === 1 ? '已配置' : '';
                const toggle = inputEl.closest('.api-key-field')?.querySelector('.api-key-toggle');
                if (toggle) toggle.textContent = apiKeyValue ? '显示' : '';
                const status = inputEl.closest('.api-key-field')?.querySelector('.api-key-status');
                if (status) {
                    status.textContent = statusText;
                } else if (statusText && inputEl.closest('.api-key-field')) {
                    const label = inputEl.closest('.api-key-field').querySelector('label');
                    if (label && !label.querySelector('.api-key-status')) {
                        const span = document.createElement('span');
                        span.className = 'api-key-status';
                        span.textContent = statusText;
                        label.appendChild(document.createTextNode(' '));
                        label.appendChild(span);
                    }
                }
            }

            closeModal();
        };

        header.querySelector('.modal-close-btn').addEventListener('click', closeModal);
        footer.querySelector('.modal-cancel-btn').addEventListener('click', closeModal);
        footer.querySelector('.modal-confirm-btn').addEventListener('click', confirmSave);
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });

        // 聚焦文本框
        setTimeout(() => textarea.focus(), 100);
    }

    // 显示右键菜单    
    showContextMenu(e, providerKey, type, index, item) {
        e.preventDefault();

        // 移除已存在的菜单  
        const existingMenu = document.querySelector('.context-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        // 创建菜单  
        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.style.left = `${e.pageX}px`;
        menu.style.top = `${e.pageY}px`;

        // 删除选项  
        const deleteItem = document.createElement('div');
        deleteItem.className = 'context-menu-item';
        deleteItem.textContent = '删除';
        deleteItem.addEventListener('click', async () => {
            // 使用自定义确认弹窗而非系统confirm  
            window.dialogManager.showConfirm(
                `确定删除这个${type}吗?`,
                async () => {
                    if (type === 'API KEY') {
                        await this.deleteAPIKey(providerKey, index);
                    } else if (type === '视觉模型') {
                        await this.deleteVisionModel(providerKey, index);
                    } else {
                        await this.deleteModel(providerKey, index);
                    }
                }
            );
            menu.remove();
        });

        menu.appendChild(deleteItem);
        document.body.appendChild(menu);

        // 点击外部关闭菜单  
        setTimeout(() => {
            const closeMenu = () => {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            };
            document.addEventListener('click', closeMenu);
        }, 0);
    }

    // 更新API选择    
    async updateAPISelection(providerKey, type, index) {
        const fieldName = type === 'API KEY' ? 'key_index' : 'model_index';
        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    [fieldName]: index
                }
            }
        });
    }

    // 设置 API KEY 列表 (V19.0 支持负载均衡)
    async setAPIKeys(providerKey, keys) {
        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    api_key: keys
                }
            }
        });
        this.populateAPIUI();
    }

    // 添加API KEY    
    async addAPIKey(providerKey, value) {
        const apiKeys = [...(this.config.api[providerKey].api_key || [])];
        apiKeys.push(value || '');

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    api_key: apiKeys
                }
            }
        });

        this.populateAPIUI();
    }

    // 删除API KEY    
    async deleteAPIKey(providerKey, index) {
        const apiKeys = [...(this.config.api[providerKey].api_key || [])];
        apiKeys.splice(index, 1);

        let keyIndex = this.config.api[providerKey].key_index;
        if (keyIndex >= apiKeys.length) {
            keyIndex = Math.max(0, apiKeys.length - 1);
        }

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    api_key: apiKeys,
                    key_index: keyIndex
                }
            }
        });

        this.populateAPIUI();
    }

    // 更新指定索引的KEY    
    async updateAPIKeyAtIndex(providerKey, index, value) {
        const apiKeys = [...(this.config.api[providerKey].api_key || [])];
        apiKeys[index] = value;

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    api_key: apiKeys
                }
            }
        });
    }

    // 添加模型    
    async addModel(providerKey, value) {
        const models = [...(this.config.api[providerKey].model || [])];
        models.push(value || '');

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    model: models
                }
            }
        });

        this.populateAPIUI();
    }

    // 添加视觉模型
    async addVisionModel(providerKey, value) {
        const models = [...(this.config.api[providerKey].vision_model || [])];
        models.push(value || '');

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    vision_model: models
                }
            }
        });

        this.populateAPIUI();
    }

    // 删除模型    
    async deleteModel(providerKey, index) {
        const models = [...(this.config.api[providerKey].model || [])];
        models.splice(index, 1);

        // 如果删除的是当前选中的模型,重置索引    
        let modelIndex = this.config.api[providerKey].model_index;
        if (modelIndex >= models.length) {
            modelIndex = Math.max(0, models.length - 1);
        }

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    model: models,
                    model_index: modelIndex
                }
            }
        });

        this.populateAPIUI();
    }

    // 删除视觉模型
    async deleteVisionModel(providerKey, index) {
        const models = [...(this.config.api[providerKey].vision_model || [])];
        models.splice(index, 1);

        let modelIndex = this.config.api[providerKey].vision_model_index;
        if (modelIndex >= models.length) {
            modelIndex = Math.max(0, models.length - 1);
        }

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    vision_model: models,
                    vision_model_index: modelIndex
                }
            }
        });

        this.populateAPIUI();
    }

    // 更新指定索引的模型    
    async updateModelAtIndex(providerKey, index, value) {
        const models = [...(this.config.api[providerKey].model || [])];
        models[index] = value;

        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    model: models
                }
            }
        });
    }

    // 更新API选择(当用户从下拉框选择时)    
    async updateAPISelection(providerKey, type, index) {
        const fieldName = type === 'API KEY' ? 'key_index' : 'model_index';
        await this.updateConfig({
            api: {
                [providerKey]: {
                    ...this.config.api[providerKey],
                    [fieldName]: index
                }
            }
        });
    }

    // 设置当前API提供商    
    async setCurrentAPIProvider(providerKey) {
        await this.updateConfig({
            api: {
                ...this.config.api,
                api_type: providerKey
            }
        });

        // 刷新UI以更新激活状态    
        this.populateAPIUI();

        window.app?.showNotification(
            `已切换到 ${providerKey === 'SiliconFlow' ? '硅基流动' : providerKey}`,
            'success'
        );
    }

    // 删除API提供商（从配置中移除，并加入黑名单防止重启复活）
    async deleteAPIProvider(providerKey) {
        // 创建新的配置对象，确保完全删除该提供商
        const newApiConfig = {};
        for (const key of Object.keys(this.config.api)) {
            if (key !== providerKey && key !== 'api_type') {
                newApiConfig[key] = this.config.api[key];
            }
        }
        // 保留api_type
        if (this.config.api.api_type) {
            newApiConfig.api_type = this.config.api.api_type;
        }

        // ⭐ 加入黑名单，确保重启后不会被 default_config 还原
        const deletedProviders = newApiConfig.deleted_providers || [];
        if (!deletedProviders.includes(providerKey)) {
            deletedProviders.push(providerKey);
        }
        newApiConfig.deleted_providers = deletedProviders;

        // 如果删除的是当前使用的API，需要切换到其他可用的
        if (providerKey === this.config.api.api_type) {
            const availableProviders = Object.keys(newApiConfig).filter(k => k !== 'api_type' && k !== 'deleted_providers');
            newApiConfig.api_type = availableProviders.length > 0 ? availableProviders[0] : 'OpenAI';
        }

        // 直接更新本地配置
        this.config.api = newApiConfig;

        await this.updateConfig({
            api: newApiConfig
        });

        // ⚡ 自动保存到文件，确保 deleted_providers 持久化
        await this.saveConfig();

        if (this._selectedAPIProvider === providerKey) {
            this._selectedAPIProvider = null;
        }
        this.populateAPIUI();

        window.app?.showNotification(
            `已删除 ${providerKey}`,
            'info'
        );
    }

    // 保存API配置    
    async saveAPIConfig() {
        await this.persistCustomAPIsToConfig();
        await this.syncCustomProviderSnapshots();
        const success = await this.saveConfig();

        if (success) {
            // 清除未保存提示    
            const saveBtn = document.getElementById('save-api-config');
            if (saveBtn) {
                saveBtn.classList.remove('has-changes');
                saveBtn.innerHTML = '保存配置';
            }
        }

        window.app?.showNotification(
            success ? 'API配置已保存' : '保存API配置失败',
            success ? 'success' : 'error'
        );
    }

    // 恢复默认API配置    
    async resetAPIConfig() {
        // 使用自定义确认弹窗  
        window.dialogManager.showConfirm(
            '确定要恢复默认API配置吗？这将清除所有自定义设置。',
            async () => {
                try {
                    const response = await fetch(`${this.apiEndpoint}/default`);
                    if (!response.ok) throw new Error('获取默认配置失败');

                    const result = await response.json();
                    const defaultAPI = result.data.api;

                    // 更新配置到内存  
                    await this.updateConfig({ api: defaultAPI });

                    // 刷新UI  
                    this.populateAPIUI();

                    window.app?.showNotification('已恢复默认API配置', 'success');
                } catch (error) {
                    window.app?.showNotification('恢复默认配置失败', 'error');
                }
            }
        );
    }

    bindConfigNavigation() {
        const links = document.querySelectorAll('.nav-sublink');
        links.forEach((link, index) => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const configType = link.dataset.config;
                this.showConfigPanel(configType);
            });
        });
    }

    _markGeneralConfigDirty() {
        const saveBtn = document.getElementById('save-general-config');
        if (saveBtn && !saveBtn.classList.contains('has-changes')) {
            saveBtn.classList.add('has-changes');
            saveBtn.innerHTML = '保存设置 <span style="color: var(--warning-color);">(有未保存更改)</span>';
        }
    }

    _clearGeneralConfigDirty() {
        const saveBtn = document.getElementById('save-general-config');
        if (saveBtn) {
            saveBtn.classList.remove('has-changes');
            saveBtn.innerHTML = '保存设置';
        }
    }

    async saveGeneralConfig() {
        const uiSuccess = await this.saveUIConfig(this.uiConfig);
        const baseSuccess = await this.saveConfig();
        const success = uiSuccess && baseSuccess;
        if (success) {
            this._clearGeneralConfigDirty();
        }
        window.app?.showNotification(
            success ? '常规设置已保存' : '保存常规设置失败',
            success ? 'success' : 'error'
        );
        return success;
    }

    async resetGeneralConfig() {
        if (!confirm('确定恢复界面与基础参数为默认值？')) {
            return;
        }
        const oldWindowMode = this.uiConfig.windowMode;
        this.uiConfig = {
            theme: 'light',
            windowMode: 'STANDARD',
            designTheme: 'follow-system'
        };

        const themeSelector = document.getElementById('theme-selector');
        const windowModeSelector = document.getElementById('window-mode-selector');
        const designThemeSelector = document.getElementById('design-theme-selector');
        if (themeSelector) themeSelector.value = 'light';
        if (windowModeSelector) windowModeSelector.value = 'STANDARD';
        if (designThemeSelector) designThemeSelector.value = 'follow-system';

        if (window.themeManager) window.themeManager.applyTheme('light', false);
        if (window.windowModeManager) window.windowModeManager.applyMode('STANDARD');
        this.toggleGrapesJSTheme('follow-system');

        const uiOk = await this.saveUIConfig(this.uiConfig);
        const baseOk = await this.resetToDefault();
        if (uiOk && baseOk) {
            this._clearGeneralConfigDirty();
            this.populateUI();
        }
        if (uiOk && oldWindowMode !== 'STANDARD') {
            window.windowModeManager?.showRestartNotification();
        }
        window.app?.showNotification(
            uiOk && baseOk ? '已恢复默认常规设置' : '恢复默认失败',
            uiOk && baseOk ? 'info' : 'error'
        );
    }

    showConfigPanel(panelType) {
        if (panelType === 'ui' || panelType === 'base') {
            panelType = 'general';
        }
        const configContent = document.querySelector('.config-content');
        const targetPanel = document.getElementById(`config-${panelType}`);

        this.currentPanel = panelType;

        // 关键:在任何DOM操作之前立即重置滚动位置  
        if (configContent) {
            configContent.scrollTop = 0;
        }

        // 隐藏所有配置面板  
        document.querySelectorAll('.config-panel').forEach(panel => {
            if (panel !== targetPanel) {
                panel.classList.remove('active');
                panel.style.display = 'none';
            }
        });

        // 显示目标面板  
        if (targetPanel) {
            targetPanel.style.display = 'block';
            targetPanel.offsetHeight; // 强制重排  
            targetPanel.classList.add('active');
        }

        // 更新导航状态  
        document.querySelectorAll('.config-nav-item').forEach(item => {
            item.classList.remove('active');
        });

        const activeNavItem = document.querySelector(`[data-config="${panelType}"]`)?.parentElement;
        if (activeNavItem) {
            activeNavItem.classList.add('active');
        }

        this.populateUI();
    }

    // ========== UI配置管理(localStorage) ==========  

    loadUIConfig() {
        try {
            const saved = localStorage.getItem('aiwritex_ui_config');
            const defaultConfig = {
                theme: 'light',
                windowMode: 'STANDARD',
                designTheme: 'follow-system'
            };

            if (saved) {
                return { ...defaultConfig, ...JSON.parse(saved) };
            }
            return defaultConfig;
        } catch (e) {
            return { theme: 'light', windowMode: 'STANDARD', designTheme: 'follow-system' };
        }
    }

    async saveUIConfig(updates) {
        try {
            const newConfig = updates.theme !== undefined && updates.windowMode !== undefined && updates.designTheme !== undefined
                ? updates
                : { ...this.uiConfig, ...updates };

            // 1. 保存到 localStorage      
            localStorage.setItem('aiwritex_ui_config', JSON.stringify(newConfig));
            this.uiConfig = newConfig;

            // 2. 同步到后端文件(持久化)      
            const response = await fetch('/api/config/ui-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newConfig)
            });

            if (!response.ok) {
                throw new Error('保存失败');
            }

            return true;
        } catch (e) {
            return false;
        }
    }

    getUIConfig() {
        return this.uiConfig;
    }

    getTheme() {
        return this.uiConfig.theme;
    }

    setTheme(theme) {
        return this.saveUIConfig({ theme: theme });
    }

    getWindowMode() {
        return this.uiConfig.windowMode;
    }

    setWindowMode(mode) {
        return this.saveUIConfig({ windowMode: mode });
    }

    // ========== 业务配置管理(后端API) ==========  

    async loadConfig() {
        try {
            const response = await fetch(this.apiEndpoint);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            this.config = result.data;

            if (this.config.img_api?.custom) this.customImgAPIs = this.config.img_api.custom;
            this.initCustomAPIs();

            return true;
        } catch (error) {
            console.error('加载配置失败:', error);
            return false;
        }
    }

    // 加载动态选项数据  
    async loadDynamicOptions() {
        try {
            // 加载发布平台列表  
            const platformsResponse = await fetch('/api/config/platforms');
            if (platformsResponse.ok) {
                const result = await platformsResponse.json();
                this.platforms = result.data;
                this.populatePlatformOptions();
            }

            // 加载模板分类列表  
            const categoriesResponse = await fetch('/api/config/template-categories');
            if (categoriesResponse.ok) {
                const result = await categoriesResponse.json();
                this.templateCategories = result.data;
                this.populateTemplateCategoryOptions();
            }
        } catch (error) {
        }
    }

    // 填充发布平台选项  
    populatePlatformOptions() {
        const publishPlatformSelect = document.getElementById('publish-platform');
        if (!publishPlatformSelect || !this.platforms) return;

        // 清空现有选项  
        publishPlatformSelect.innerHTML = '';

        // 添加平台选项  
        this.platforms.forEach(platform => {
            const option = document.createElement('option');
            option.value = platform.value;
            option.textContent = platform.label;
            publishPlatformSelect.appendChild(option);
        });

        // 禁用选择器(只支持微信)  
        publishPlatformSelect.disabled = true;
    }

    // 填充模板分类选项  
    populateTemplateCategoryOptions() {
        const templateCategorySelect = document.getElementById('config-template-category');
        if (!templateCategorySelect || !this.templateCategories) return;

        // 清空现有选项  
        templateCategorySelect.innerHTML = '';

        // 添加"随机分类"选项  
        const randomOption = document.createElement('option');
        randomOption.value = '';
        randomOption.textContent = '随机分类';
        templateCategorySelect.appendChild(randomOption);

        // 添加分类选项  
        this.templateCategories.forEach(category => {
            const option = document.createElement('option');
            option.value = category;
            option.textContent = category;
            templateCategorySelect.appendChild(option);
        });
    }

    // 加载指定分类的模板列表  
    async loadTemplatesByCategory(category) {
        try {
            if (!category || category === '随机分类') {
                return [];
            }

            const response = await fetch(`/api/config/templates/${encodeURIComponent(category)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            return result.data || [];
        } catch (error) {
            return [];
        }
    }

    // ============ 自定义API管理功能 ============

    // 存储自定义API配置（在方法中初始化）

    // 初始化自定义API（合并 secrets 恢复后的 config 与本地缓存中的 Key）
    initCustomAPIs() {
        let list = [];
        if (this.config.api && Array.isArray(this.config.api.custom)) {
            list = JSON.parse(JSON.stringify(this.config.api.custom));
        }
        const stored = localStorage.getItem('custom_apis');
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                if (Array.isArray(parsed)) {
                    list = this._mergeCustomAPIEntries(list, parsed);
                }
            } catch (e) {
                /* ignore */
            }
        }
        this.customAPIs = list;
        this._hydrateCustomAPIKeysFromProviderEntries();
        this.saveCustomAPIs();
        this.syncCustomAPICurrentFlags();
    }

    _mergeCustomAPIEntries(primary, fallback) {
        const result = Array.isArray(primary) ? [...primary] : [];
        const hasKeys = (item) => {
            const k = item?.api_key;
            if (Array.isArray(k)) return k.some((x) => String(x || '').trim());
            return Boolean(String(k || '').trim());
        };
        (fallback || []).forEach((fb, index) => {
            if (!fb || !hasKeys(fb)) return;
            const pk = fb.provider_key || '';
            let target = pk
                ? result.find((x) => x && x.provider_key === pk)
                : result[index];
            if (!target) {
                result.push({ ...fb });
                return;
            }
            if (!hasKeys(target)) {
                target.api_key = fb.api_key;
            }
        });
        return result;
    }

    _hydrateCustomAPIKeysFromProviderEntries() {
        const api = this.config?.api || {};
        this.customAPIs.forEach((entry) => {
            if (!entry) return;
            const pk = entry.provider_key;
            if (!pk || !api[pk] || !Array.isArray(api[pk].api_key)) return;
            const hasLocal = Array.isArray(entry.api_key)
                ? entry.api_key.some((k) => String(k || '').trim())
                : Boolean(String(entry.api_key || '').trim());
            if (!hasLocal && api[pk].api_key.length) {
                entry.api_key = [...api[pk].api_key];
            }
        });
    }

    _escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    createCustomApiKeyField(index, api) {
        const raw = Array.isArray(api.api_key) ? api.api_key.join('\n') : (api.api_key || '');
        const hasKey = String(raw).trim().length > 0;
        const wrap = document.createElement('div');
        wrap.className = 'form-group form-group-full api-key-field';
        wrap.innerHTML = `
            <div class="api-key-field-head">
                <label>API KEY <span class="api-key-hint-inline">（一行一个，保存后重启仍有效）</span></label>
                <button type="button" class="btn btn-ghost btn-xs api-key-toggle" title="显示/隐藏密钥">${
                    hasKey ? '显示' : ''
                }</button>
            </div>
            <textarea class="api-key-input masked" rows="3" placeholder="请输入 API Key" autocomplete="off">${this._escapeHtml(
                raw
            )}</textarea>
        `;
        const textarea = wrap.querySelector('textarea');
        const toggle = wrap.querySelector('.api-key-toggle');
        textarea.addEventListener('change', (e) => {
            this.updateCustomAPI(index, 'api_key', e.target.value);
        });
        if (toggle) {
            toggle.addEventListener('click', () => {
                const masked = textarea.classList.toggle('masked');
                toggle.textContent = masked ? '显示' : '隐藏';
            });
        }
        return wrap;
    }

    async syncCustomProviderSnapshots() {
        const updates = {};
        for (const api of this.customAPIs || []) {
            if (!api?.provider_key) continue;
            const pk = api.provider_key;
            const snap = this.config.api?.[pk];
            if (!snap || typeof snap !== 'object') continue;
            const keys = api.api_key;
            const hasKeys = Array.isArray(keys)
                ? keys.some((k) => String(k || '').trim())
                : Boolean(String(keys || '').trim());
            if (!hasKeys) continue;
            updates[pk] = {
                ...snap,
                api_key: Array.isArray(keys) ? keys : String(keys).split('\n').map((k) => k.trim()).filter(Boolean),
                api_base: api.api_base || snap.api_base,
            };
            if (api.model) {
                updates[pk].model = Array.isArray(snap.model)
                    ? snap.model.includes(api.model)
                        ? snap.model
                        : [api.model, ...snap.model]
                    : [api.model];
            }
        }
        if (Object.keys(updates).length) {
            await this.updateConfig({ api: updates });
        }
    }

    syncCustomAPICurrentFlags() {
        const currentApiType = this.config?.api?.api_type || '';
        this.customAPIs.forEach((api, index) => {
            if (api) {
                const customProviderKey = api.provider_key || api.name || '';
                api.isCurrent = Boolean(currentApiType && customProviderKey === currentApiType);
            }
        });
    }

    async persistCustomAPIsToConfig() {
        await this.updateConfig({
            api: {
                ...this.config.api,
                custom: this.customAPIs
            }
        });
    }

    // 保存自定义API到localStorage
    saveCustomAPIs() {
        localStorage.setItem('custom_apis', JSON.stringify(this.customAPIs));
    }

    // 兼容旧调用：同步状态并刷新大模型 API 面板
    renderCustomAPIs() {
        this.syncCustomAPICurrentFlags();
        if (this.currentPanel === 'api') {
            this.populateAPIUI();
        }
    }

    // 创建自定义API卡片
    createCustomAPICard(api, index, compactToolbar = false) {
        const card = document.createElement('div');
        card.className = 'custom-api-card api-provider-card llm-api-detail-card';
        if (this.customAPIs[index]?.isCurrent) {
            card.classList.add('active');
        }
        card.dataset.index = index;

        const header = document.createElement('div');
        header.className = 'custom-api-card-header';

        const title = document.createElement('div');
        title.className = 'custom-api-card-title';
        const isCurrent = this.customAPIs[index]?.isCurrent;
        title.innerHTML = `${api.name || `自定义API ${index + 1}`}${isCurrent ? '<span class="current-api-badge">当前使用</span>' : ''}`;

        const actions = document.createElement('div');
        actions.className = 'custom-api-card-actions';

        if (!compactToolbar) {
            const useBtn = document.createElement('button');
            useBtn.className = `btn-use ${isCurrent ? 'active' : ''}`;
            useBtn.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> ${isCurrent ? '当前使用' : '设为当前'}`;
            useBtn.onclick = () => this.setCurrentCustomAPI(index);

            const testBtn = document.createElement('button');
            testBtn.className = 'btn-test';
            testBtn.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 测试`;
            testBtn.onclick = () => this.testCustomAPI(index);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn-delete';
            deleteBtn.textContent = '删除';
            deleteBtn.onclick = () => this.deleteCustomAPI(index);

            actions.appendChild(useBtn);
            actions.appendChild(testBtn);
            actions.appendChild(deleteBtn);
        }

        header.appendChild(title);
        if (!compactToolbar) {
            header.appendChild(actions);
        }

        const form = document.createElement('div');
        form.className = 'custom-api-form llm-api-form';

        const nameGroup = document.createElement('div');
        nameGroup.className = 'form-group';
        nameGroup.innerHTML = `
            <label>API名称</label>
            <input type="text" value="${api.name || ''}" placeholder="例如: 我的OpenAI" onchange="window.configManager.updateCustomAPI(${index}, 'name', this.value)">
        `;

        const typeGroup = document.createElement('div');
        typeGroup.className = 'form-group';
        const currentType = api.provider || api.type || 'openai';
        typeGroup.innerHTML = `
            <label>模型类型</label>
            <select onchange="window.configManager.updateCustomAPI(${index}, 'provider', this.value)">
                <option value="openai" ${currentType === 'openai' ? 'selected' : ''}>OpenAI兼容</option>
                <option value="ollama" ${currentType === 'ollama' ? 'selected' : ''}>Ollama本地模型</option>
                <option value="gemini" ${currentType === 'gemini' ? 'selected' : ''}>Gemini兼容</option>
                <option value="anthropic" ${currentType === 'anthropic' ? 'selected' : ''}>Claude兼容</option>
                <option value="custom" ${currentType === 'custom' ? 'selected' : ''}>其他自定义</option>
            </select>
        `;

        // API Base
        const baseGroup = document.createElement('div');
        baseGroup.className = 'form-group form-group-full';
        baseGroup.innerHTML = `
            <label>API BASE</label>
            <input type="text" value="${api.api_base || ''}" placeholder="例如: https://api.openai.com/v1 (末尾加#强制使用原始地址)" onchange="window.configManager.updateCustomAPI(${index}, 'api_base', this.value)">
            <small style="color:#888;font-size:11px;">💡 提示：系统会自动补全/v1路径，如需强制使用原始地址请在末尾添加#</small>
        `;

        const keyGroup = this.createCustomApiKeyField(index, api);

        // 模型选择
        const modelGroup = document.createElement('div');
        modelGroup.className = 'form-group form-group-full';
        const modelOptions = (api.models || []).map(m => `<option value="${m}" ${api.model === m ? 'selected' : ''}>${m}</option>`).join('');
        modelGroup.innerHTML = `
            <label>模型</label>
            <div class="model-select-wrapper">
                <select onchange="window.configManager.updateCustomAPI(${index}, 'model', this.value)">
                    <option value="">请先测试API获取模型</option>
                    ${modelOptions}
                </select>
                <button type="button" class="model-dropdown-btn" onclick="window.configManager.fetchModels(${index})" title="刷新模型列表">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
                    刷新模型
                </button>
            </div>
            <input type="text" value="${api.model || ''}" placeholder="或手动输入模型名称" style="margin-top:8px" onchange="window.configManager.updateCustomAPI(${index}, 'model', this.value)">
        `;

        const resultDiv = document.createElement('div');
        resultDiv.className = 'test-result';
        resultDiv.id = `test-result-${index}`;
        resultDiv.style.display = 'none';

        if (compactToolbar) {
            const basicSec = this.createLLMFormSection('基本信息', '自定义 OpenAI 兼容接口');
            const basicRow = document.createElement('div');
            basicRow.className = 'form-row';
            basicRow.appendChild(nameGroup);
            basicRow.appendChild(typeGroup);
            basicSec.body.appendChild(basicRow);

            const connSec = this.createLLMFormSection('连接与认证', 'Base 地址与 API Key（一行一个 Key）');
            connSec.body.appendChild(baseGroup);
            connSec.body.appendChild(keyGroup);

            const modelSec = this.createLLMFormSection('模型', '测试连接成功后可刷新模型列表');
            modelSec.body.appendChild(modelGroup);

            form.appendChild(basicSec.section);
            form.appendChild(connSec.section);
            form.appendChild(modelSec.section);
            form.appendChild(resultDiv);
        } else {
            form.appendChild(nameGroup);
            form.appendChild(typeGroup);
            form.appendChild(baseGroup);
            form.appendChild(keyGroup);
            form.appendChild(modelGroup);
            form.appendChild(resultDiv);
        }

        if (!compactToolbar) {
            card.appendChild(header);
        }
        card.appendChild(form);

        return card;
    }

    // 添加自定义API
    async addCustomAPI() {
        this.customAPIs.push({
            name: '',
            provider: 'openai',
            api_base: '',
            api_key: '',
            model: '',
            models: [],
            tested: false
        });
        this._selectedAPIProvider = `__custom_index_${this.customAPIs.length - 1}`;
        this.saveCustomAPIs();
        await this.persistCustomAPIsToConfig();
        this.populateAPIUI();
    }

    // 删除自定义API
    async deleteCustomAPI(index) {
        if (confirm('确定要删除这个自定义API吗?')) {
            if (this.customAPIs[index]?.isCurrent) {
                this.customAPIs.forEach((api, i) => {
                    if (api) api.isCurrent = false;
                });
            }
            this.customAPIs.splice(index, 1);
            this._selectedAPIProvider = null;
            this.saveCustomAPIs();
            await this.persistCustomAPIsToConfig();
            this.populateAPIUI();
        }
    }

    // 设置当前使用的自定义API
    async setCurrentCustomAPI(index) {
        const api = this.customAPIs[index];
        if (!api || !api.api_key || !api.api_base) {
            alert('请先填写API BASE和API KEY');
            return;
        }

        // 清除所有卡的当前状态
        this.customAPIs.forEach((a, i) => {
            if (a) a.isCurrent = (i === index);
        });
        this.saveCustomAPIs();
        this.renderCustomAPIs();

        try {
            // 将自定义API添加到后端配置
            const customProviderKey = api.name || `CustomAPI_${Date.now()}`;
            api.provider_key = customProviderKey;

            const apiKeys = Array.isArray(api.api_key) ? api.api_key : (api.api_key ? api.api_key.split('\n').map(k => k.trim()).filter(k => k !== '') : []);
            this.saveCustomAPIs();
            await this.persistCustomAPIsToConfig();

            // 更新后端配置
            await this.updateConfig({
                api: {
                    ...this.config.api,
                    api_type: customProviderKey,
                    [customProviderKey]: {
                        key: "OPENAI_API_KEY",
                        api_key: apiKeys,
                        key_index: 0,
                        model: api.model ? [api.model] : ['gpt-3.5-turbo'],
                        model_index: 0,
                        api_base: api.api_base,
                        provider: api.provider || api.type || 'openai'
                    }
                }
            });

            // 保存配置到文件
            await this.saveConfig();

            // 重新加载配置
            await this.loadConfig();

            this.populateAPIUI();

            window.app?.showNotification(
                `已将 "${api.name || '自定义API'}" 设为当前使用`,
                'success'
            );
        } catch (error) {
            console.error('更新后端配置失败:', error);
            alert('设置当前API失败: ' + error.message);
        }
    }

    // 更新自定义API
    async updateCustomAPI(index, field, value) {
        if (this.customAPIs[index]) {
            if (field === 'api_key') {
                this.customAPIs[index][field] = value.split('\n').map(k => k.trim()).filter(k => k !== '');
            } else {
                this.customAPIs[index][field] = value;
            }
            this.customAPIs[index].tested = false;
            this.saveCustomAPIs();
            await this.persistCustomAPIsToConfig();
        }
    }

    // 测试自定义API
    async testCustomAPI(index, options = {}) {
        const api = this.customAPIs[index];
        if (!api) {
            window.app?.showNotification('未找到自定义 API 配置', 'error');
            return;
        }

        const cardTestBtn = document.querySelector(`.custom-api-card[data-index="${index}"] .btn-test`);
        const resultDiv = document.getElementById(`test-result-${index}`);
        const fromToolbar = Boolean(options.fromToolbar);

        const setCardBtnLoading = (loading) => {
            if (!cardTestBtn || fromToolbar) return;
            cardTestBtn.disabled = loading;
            cardTestBtn.textContent = loading ? '测试中...' : '测试';
        };

        const showResult = (ok, message) => {
            const text = ok ? `✅ ${message}` : `❌ ${message}`;
            if (resultDiv) {
                resultDiv.style.display = 'block';
                resultDiv.className = ok ? 'test-result success' : 'test-result error';
                resultDiv.textContent = text;
            }
            window.app?.showNotification(message, ok ? 'success' : 'error');
        };

        let apiKey = api.api_key;
        if (Array.isArray(apiKey)) {
            apiKey = apiKey[0] || '';
        }
        apiKey = String(apiKey || '').trim();

        if (!api.api_base?.trim()) {
            showResult(false, '请先填写 API Base');
            return;
        }
        if (!apiKey) {
            showResult(false, '请先填写 API KEY');
            return;
        }

        setCardBtnLoading(true);

        try {
            const response = await fetch('/api/config/test-custom-api', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: api.name,
                    api_base: api.api_base,
                    api_key: apiKey,
                    model: api.model,
                    provider: api.provider || api.type || 'openai',
                }),
            });

            const result = await response.json().catch(() => ({}));

            if (result.status === 'success') {
                showResult(true, result.message || '连接成功');
                this.customAPIs[index].tested = true;
                this.customAPIs.forEach((entry, i) => {
                    if (entry) entry.isCurrent = i === index;
                });
                this.saveCustomAPIs();
                try {
                    await this.fetchModels(index);
                } catch (_) {
                    /* 刷新模型列表失败不覆盖成功提示 */
                }
            } else {
                this.customAPIs[index].tested = false;
                showResult(false, result.message || '未知错误，请检查配置');
            }
        } catch (error) {
            this.customAPIs[index].tested = false;
            showResult(false, error.message || '网络异常');
        } finally {
            setCardBtnLoading(false);
        }
    }

    // 测试ComfyUI连接
    async testComfyUI() {
        const apiBaseInput = document.getElementById('img-api-comfyui-api-base');
        const apiBase = apiBaseInput?.value?.trim() || '';

        if (!apiBase) {
            window.app?.showNotification('请填写 ComfyUI 服务地址', 'error');
            return;
        }

        const testBtn = document.getElementById('test-comfyui-btn');
        let resultDiv = document.getElementById('comfyui-test-result');
        if (!resultDiv) {
            const wrap = document.getElementById('img-api-providers-container');
            if (wrap) {
                resultDiv = document.createElement('div');
                resultDiv.id = 'comfyui-test-result';
                resultDiv.className = 'test-result';
                resultDiv.style.display = 'none';
                resultDiv.style.marginTop = '12px';
                wrap.appendChild(resultDiv);
            }
        }

        if (testBtn) {
            testBtn.disabled = true;
            testBtn.innerHTML = `<svg class="spinner" viewBox="0 0 24 24" width="14" height="14"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="30 70"/></svg> 测试中...`;
        }

        try {
            const response = await fetch('/api/config/test-comfyui', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_base: apiBase })
            });

            const result = await response.json();

            if (resultDiv) {
                resultDiv.style.display = 'block';
                if (result.status === 'success') {
                    resultDiv.className = 'test-result success';
                    resultDiv.textContent = '✅ ' + result.message;
                } else {
                    resultDiv.className = 'test-result error';
                    resultDiv.textContent = '❌ ' + result.message;
                }
            }
            if (result.status === 'success') {
                window.app?.showNotification('ComfyUI 连接成功', 'success');
            } else {
                window.app?.showNotification(result.message || 'ComfyUI 连接失败', 'error');
            }
        } catch (error) {
            if (resultDiv) {
                resultDiv.style.display = 'block';
                resultDiv.className = 'test-result error';
                resultDiv.textContent = '❌ 测试失败: ' + error.message;
            }
            window.app?.showNotification('测试失败: ' + error.message, 'error');
        } finally {
            if (testBtn) {
                testBtn.disabled = false;
                testBtn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 测试连接`;
            }
        }
    }

    // 测试内置图片API连通性 (Ali, ModelScope)
    async testBuiltinImgAPI(providerKey) {
        const apiKey = document.getElementById(`img-api-${providerKey}-api-key`)?.value || '';
        const model = document.getElementById(`img-api-${providerKey}-model`)?.value || document.getElementById(`img-api-${providerKey}-model-input`)?.value || '';

        let apiBase = '';
        if (providerKey === 'ali') apiBase = 'https://dashscope.aliyuncs.com/compatible-mode/v1';
        else if (providerKey === 'modelscope') apiBase = 'https://api-inference.modelscope.cn/v1';
        else if (providerKey === 'agnes') apiBase = 'https://apihub.agnes-ai.com/v1';

        if (!apiKey) {
            window.app?.showNotification('请先填写 API Key', 'warning');
            return;
        }

        if (!model && providerKey !== 'picsum') {
            window.app?.showNotification('请先选择或输入模型名称', 'warning');
            return;
        }

        const btn = document.getElementById(`btn-test-builtin-img-${providerKey}`);
        const resultContainer = document.getElementById(`test-result-builtin-img-${providerKey}`);

        if (!resultContainer) {
            console.error('Test result container not found for:', providerKey);
            return;
        }

        const statusDiv = resultContainer.querySelector('.test-status');
        const previewImg = resultContainer.querySelector('img');

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner"></span> 测试中...`;
        }

        resultContainer.style.display = 'block';
        statusDiv.className = 'test-status info';
        statusDiv.innerHTML = '<i class="spinner"></i> 正在发送请求并生成图片 (可能需要 10-60 秒)...';
        previewImg.style.display = 'none';

        try {
            const response = await fetch('/api/config/test-custom-img-api', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_base: apiBase,
                    api_key: apiKey,
                    model: model,
                    provider: providerKey
                })
            });

            const result = await response.json();

            if (result.status === 'success') {
                statusDiv.className = 'test-status success';
                statusDiv.innerHTML = `✅ ${result.message}`;

                if (result.url) {
                    previewImg.src = result.url;
                    previewImg.style.display = 'block';
                }

                window.app?.showNotification(`${providerKey} 连接成功`, 'success');
            } else {
                statusDiv.className = 'test-status error';
                statusDiv.innerHTML = `❌ ${result.message}`;
                window.app?.showNotification(result.message || '测试失败', 'error');
            }
        } catch (error) {
            statusDiv.className = 'test-status error';
            statusDiv.innerHTML = `请求异常: ${error.message}`;
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 测试`;
            }
        }
    }

    async fetchModels(index) {
        const api = this.customAPIs[index];
        if (!api) return;
        let apiKey = api.api_key;
        if (Array.isArray(apiKey)) apiKey = apiKey[0] || '';
        if (!api.api_base?.trim() || !String(apiKey || '').trim()) {
            window.app?.showNotification('请先填写 API Base 和 API KEY', 'warning');
            return;
        }

        try {
            const response = await fetch('/api/config/list-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_base: api.api_base,
                    api_key: Array.isArray(api.api_key) ? (api.api_key[0] || '') : api.api_key,
                    provider: api.provider || api.type || 'openai'
                })
            });

            const result = await response.json();

            if (result.status === 'success' && result.models) {
                this.customAPIs[index].models = result.models;

                // 自动识别视觉模型
                const visionRegex = /vision|vl|multimodal|gpt-4o|claude-3|gemini/i;
                const detectedVisionModels = result.models.filter(m => visionRegex.test(m));
                if (detectedVisionModels.length > 0) {
                    // 如果原先没有视觉模型或已经包含了，我们进行合并/更新
                    const existingVisionModels = this.customAPIs[index].vision_model || [];
                    const newVisionModels = [...new Set([...existingVisionModels, ...detectedVisionModels])];
                    this.customAPIs[index].vision_model = newVisionModels;
                    console.log(`已自动识别并添加 ${detectedVisionModels.length} 个视觉模型到 "${this.customAPIs[index].name}"`);
                }

                this.saveCustomAPIs();
                this.renderCustomAPIs();

                window.app?.showNotification(`检测成功! 识别到 ${detectedVisionModels.length} 个视觉模型`, 'success');
            }
        } catch (error) {
            console.error('获取模型列表失败:', error);
            window.app?.showNotification('获取获取失败: ' + error.message, 'error');
        }
    }

    // 内置API提供商获取模型列表
    async fetchAPIModels(providerKey, options = {}) {
        const { quietSuccess = false } = options;
        const providerData = this.config.api[providerKey];
        if (!providerData) return;

        const apiKeys = providerData.api_key || [];
        const keyIndex = Number(providerData.key_index) || 0;
        const apiKey = (apiKeys[keyIndex] || apiKeys[0] || '').trim();
        const apiBase = (providerData.api_base || '').trim();

        if (!apiKey || !apiBase) {
            if (!quietSuccess) {
                window.app?.showNotification('请先配置并选中 API KEY', 'warning');
            }
            return;
        }

        // 按钮加载反馈
        const btn = document.querySelector(`.model-refresh-btn-inline[onclick*="${providerKey}"]`);
        if (btn) btn.classList.add('spinning');

        try {
            const response = await fetch('/api/config/list-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_base: apiBase,
                    api_key: apiKey
                })
            });

            const result = await response.json();

            if (result.status === 'success' && result.models) {
                // 1. 过滤识别视觉模型
                const visionRegex = /vision|vl|multimodal|gpt-4o|claude-3|gemini/i;
                const detectedVisionModels = result.models.filter(m => visionRegex.test(m));

                // 2. 更新配置
                const updateData = {
                    api: {
                        [providerKey]: {
                            ...providerData,
                            model: result.models,
                        }
                    }
                };

                // 合并视觉模型（如果不存则创建）
                if (detectedVisionModels.length > 0) {
                    const existingVisionModels = providerData.vision_model || [];
                    const newVisionModels = [...new Set([...existingVisionModels, ...detectedVisionModels])];
                    updateData.api[providerKey].vision_model = newVisionModels;
                }

                await this.updateConfig(updateData);
                this.populateAPIUI();

                if (!quietSuccess) {
                    window.app?.showNotification(
                        `检测完成! 共 ${result.models.length} 个模型，其中 ${detectedVisionModels.length} 个视觉模型`,
                        'success'
                    );
                }
            } else if (!quietSuccess) {
                window.app?.showNotification('未获取到模型列表: ' + (result.message || '未知错误'), 'error');
            }
        } catch (error) {
            console.error('检测模型失败:', error);
            if (!quietSuccess) {
                window.app?.showNotification('网络错误: ' + error.message, 'error');
            }
            throw error;
        } finally {
            if (btn) btn.classList.remove('spinning');
        }
    }

    // 绑定自定义API事件（添加按钮已移至厂商工具栏，由 populateAPIUI 绑定）
    bindCustomAPIEvents() {
        this.initCustomAPIs();
    }

    getImgProviderOptions() {
        const builtins = [
            { key: 'picsum', display: 'Picsum（随机图）', kind: 'builtin' },
            { key: 'ali', display: '阿里百炼', kind: 'builtin' },
            { key: 'modelscope', display: '魔搭 ModelScope', kind: 'builtin' },
            { key: 'agnes', display: 'Agnes AI', kind: 'builtin' },
            { key: 'comfyui', display: 'ComfyUI（本地）', kind: 'builtin' },
        ];
        const customs = (this.customImgAPIs || []).map((api, index) => ({
            key: `custom:${index}`,
            display: api.name || `自定义图片 API ${index + 1}`,
            kind: 'custom',
            customIndex: index,
        }));
        return [...builtins, ...customs];
    }

    getCurrentImgAPIProviderKey() {
        const t = this.config?.img_api?.api_type;
        if (t === 'custom') {
            const idx = this.config.img_api.custom_index ?? 0;
            return `custom:${idx}`;
        }
        return t || 'picsum';
    }

    resolveImgProviderOption(selectedKey) {
        return this.getImgProviderOptions().find((p) => p.key === selectedKey);
    }

    isImgProviderCurrent(option, currentKey) {
        if (!option) return false;
        if (option.kind === 'custom' && option.customIndex !== undefined) {
            return (
                this.config.img_api?.api_type === 'custom'
                && (this.config.img_api.custom_index ?? 0) === option.customIndex
            );
        }
        return this.config.img_api?.api_type === option.key;
    }

    getImgProviderDisplayName(providerKey) {
        if (!providerKey) return '未设置';
        if (String(providerKey).startsWith('custom:')) {
            const idx = parseInt(String(providerKey).split(':')[1], 10);
            const api = this.customImgAPIs[idx];
            return api?.name || `自定义图片 API ${idx + 1}`;
        }
        const map = {
            picsum: 'Picsum（随机图）',
            ali: '阿里百炼',
            modelscope: '魔搭 ModelScope',
            agnes: 'Agnes AI',
            comfyui: 'ComfyUI',
        };
        return map[providerKey] || providerKey;
    }

    renderImgAPIProviderToolbar(providers, currentProviderKey) {
        const toolbar = document.getElementById('img-api-provider-toolbar');
        if (!toolbar) return;

        if (!providers.length) {
            toolbar.innerHTML = `
                <div class="img-api-toolbar-empty">
                    <p>暂无可用配图服务</p>
                    <button type="button" class="btn btn-primary btn-sm" id="add-custom-img-api">+ 自定义</button>
                </div>
            `;
            toolbar.querySelector('#add-custom-img-api')?.addEventListener('click', () => this.addCustomImgAPI());
            return;
        }

        const selectedKey = this._selectedImgAPIProvider;
        const selected = providers.find((p) => p.key === selectedKey) || providers[0];
        this._selectedImgAPIProvider = selected.key;
        const isCurrent = this.isImgProviderCurrent(selected, currentProviderKey);
        const isCustom = selected.kind === 'custom';

        const optionsHtml = providers
            .map((p) => {
                const active = this.isImgProviderCurrent(p, currentProviderKey);
                const tag = p.kind === 'custom' ? ' [自定义]' : '';
                const suffix = active ? ' ✓' : '';
                return `<option value="${p.key}" ${p.key === selected.key ? 'selected' : ''}>${p.display}${tag}${suffix}</option>`;
            })
            .join('');

        const currentLabel = this.getImgProviderDisplayName(currentProviderKey);
        const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
        const canTest = selected.key !== 'picsum';

        toolbar.innerHTML = `
            <div class="img-api-toolbar-grid">
                <div class="img-api-toolbar-main">
                    <label class="img-api-picker-label" for="img-api-provider-select">配图服务</label>
                    <select id="img-api-provider-select" class="form-control img-api-provider-select" aria-label="选择图片生成服务">${optionsHtml}</select>
                    <div class="img-api-status-chip ${isCurrent ? 'is-active' : ''}" role="status">
                        <span class="img-api-status-dot" aria-hidden="true"></span>
                        <div class="img-api-status-copy">
                            <span class="img-api-status-name">${esc(selected.display)}</span>
                            <span class="img-api-status-meta">${isCurrent ? '配图使用中' : '未设为当前'}</span>
                        </div>
                    </div>
                </div>
                <div class="img-api-toolbar-actions">
                    <button type="button" class="btn btn-primary btn-sm" id="set-current-img-api-provider" ${isCurrent ? 'disabled' : ''}>
                        ${isCurrent ? '✓ 当前使用' : '设为当前使用'}
                    </button>
                    <button type="button" class="btn btn-secondary btn-sm" id="test-img-api-provider" ${canTest ? '' : 'disabled'} title="${canTest ? '测试连接并生成预览图' : 'Picsum 无需测试'}">测试连接</button>
                    <button type="button" class="btn btn-ghost btn-sm" id="add-custom-img-api">+ 自定义</button>
                    <button type="button" class="btn btn-ghost btn-sm img-api-btn-danger" id="delete-img-api-provider" ${isCustom ? '' : 'disabled'} title="删除自定义配图服务">删除</button>
                </div>
            </div>
            <div class="img-api-global-bar">
                <span>当前配图</span>
                <strong id="current-img-api-type-label" class="img-api-global-value">${esc(currentLabel)}</strong>
                <span>·</span>
                <span>${isCustom ? 'OpenAI 兼容文生图' : '内置服务'} · 切换下拉不丢失已填内容</span>
            </div>
        `;

        toolbar.querySelector('#img-api-provider-select')?.addEventListener('change', (e) => {
            this._selectedImgAPIProvider = e.target.value;
            this.populateImgAPIUI();
        });
        toolbar.querySelector('#set-current-img-api-provider')?.addEventListener('click', () => {
            this.applySelectedAsCurrentImgAPI();
        });
        toolbar.querySelector('#test-img-api-provider')?.addEventListener('click', () => {
            this.testSelectedImgAPIProvider();
        });
        toolbar.querySelector('#add-custom-img-api')?.addEventListener('click', () => {
            this.addCustomImgAPI();
        });
        toolbar.querySelector('#delete-img-api-provider')?.addEventListener('click', () => {
            this.deleteSelectedImgAPIProvider();
        });
    }

    async applySelectedAsCurrentImgAPI() {
        const option = this.resolveImgProviderOption(this._selectedImgAPIProvider);
        if (!option) return;
        if (option.kind === 'custom' && option.customIndex !== undefined) {
            await this.setCurrentCustomImgAPI(option.customIndex);
            return;
        }
        await this.setCurrentImgAPIProvider(option.key);
    }

    _setImgToolbarTestLoading(loading) {
        const btn = document.getElementById('test-img-api-provider');
        if (!btn) return;
        if (loading) {
            if (!btn.dataset.defaultLabel) {
                btn.dataset.defaultLabel = btn.textContent.trim();
            }
            btn.disabled = true;
            btn.textContent = '测试中…';
        } else {
            const canTest = this._selectedImgAPIProvider !== 'picsum';
            btn.disabled = !canTest;
            btn.textContent = btn.dataset.defaultLabel || '测试连接';
        }
    }

    async testSelectedImgAPIProvider() {
        const option = this.resolveImgProviderOption(this._selectedImgAPIProvider);
        if (!option) {
            window.app?.showNotification('请先选择配图服务', 'warning');
            return;
        }
        if (option.key === 'picsum') {
            window.app?.showNotification('Picsum 为免费随机图，无需测试', 'info');
            return;
        }
        this._setImgToolbarTestLoading(true);
        try {
            if (option.kind === 'custom' && option.customIndex !== undefined) {
                await this.testCustomImgAPI(option.customIndex);
            } else if (['ali', 'modelscope', 'agnes'].includes(option.key)) {
                await this.testBuiltinImgAPI(option.key);
            } else if (option.key === 'comfyui') {
                await this.testComfyUI();
            }
        } finally {
            this._setImgToolbarTestLoading(false);
        }
    }

    async deleteSelectedImgAPIProvider() {
        const option = this.resolveImgProviderOption(this._selectedImgAPIProvider);
        if (!option || option.kind !== 'custom' || option.customIndex === undefined) return;
        await this.deleteCustomImgAPI(option.customIndex);
    }

    buildImgAPISettingsForm() {
        const settings = this.config.img_api?.settings || {};
        const wrap = document.createElement('div');
        wrap.className = 'img-api-settings-grid';

        const mk = (label, type, id, value, placeholder) => {
            const g = this.createFormGroup(label, type, id, value, placeholder, false);
            return g;
        };

        wrap.appendChild(mk('普通超时（秒）', 'number', 'img-api-settings-default-timeout', settings.default_timeout_seconds ?? 60, '默认 60'));
        wrap.appendChild(mk('极速超时（秒）', 'number', 'img-api-settings-fast-timeout', settings.fast_mode_timeout_seconds ?? 45, '默认 45'));
        wrap.appendChild(mk('文章配图数量', 'number', 'img-api-settings-article-image-count', settings.article_image_count ?? settings.fast_mode_prompt_count ?? 3, '1–12，含封面'));
        wrap.appendChild(mk('提示词截取长度', 'number', 'img-api-settings-fast-prompt-excerpt', settings.fast_mode_prompt_excerpt_length ?? 120, '默认 120'));

        const fallback = document.createElement('label');
        fallback.className = 'checkbox-label img-api-settings-fallback';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.id = 'img-api-settings-allow-placeholder-fallback';
        cb.checked = settings.allow_placeholder_fallback !== false;
        const spanCustom = document.createElement('span');
        spanCustom.className = 'checkbox-custom';
        const spanText = document.createElement('span');
        spanText.textContent = '允许自动回退到 Picsum 占位图';
        fallback.appendChild(cb);
        fallback.appendChild(spanCustom);
        fallback.appendChild(spanText);
        wrap.appendChild(fallback);

        const hint = document.createElement('p');
        hint.className = 'img-api-settings-hint';
        hint.textContent = '关闭占位图回退后，ComfyUI 工作流缺失或失败时将保留原占位符，不再自动替换为随机图。';
        wrap.appendChild(hint);

        return wrap;
    }

    /** 将当前可见的配图服务表单同步到内存配置（切换服务商前调用，避免 KEY 丢失） */
    syncVisibleImgAPIProviderFromDOM() {
        const selected = this.resolveImgProviderOption(this._selectedImgAPIProvider);
        if (!selected) return;

        if (selected.kind === 'custom' && selected.customIndex !== undefined) {
            const idx = selected.customIndex;
            const card = document.querySelector(`.custom-api-card[data-index="${idx}"]`);
            if (!card || !this.customImgAPIs[idx]) return;
            const api = this.customImgAPIs[idx];
            const nameInput = card.querySelector('input[placeholder*="Stable"]') || card.querySelector('.custom-api-form input[type="text"]');
            const baseInput = card.querySelector('input[placeholder="https://api.openai.com/v1"]');
            const keyInput = card.querySelector('input[type="password"]');
            const modelInput = document.getElementById(`custom-img-model-input-${idx}`);
            if (nameInput) api.name = nameInput.value;
            if (baseInput) api.api_base = baseInput.value;
            if (keyInput) api.api_key = keyInput.value;
            if (modelInput) api.model = modelInput.value;
            const modelSelect = document.getElementById(`custom-img-model-select-${idx}`);
            if (modelSelect?.value) api.model = modelSelect.value;
            return;
        }

        if (selected.key && selected.key !== 'picsum') {
            this._mergeImgProviderFromDOM(selected.key);
        }
    }

    _mergeImgProviderFromDOM(providerKey) {
        if (!this.config.img_api) this.config.img_api = {};
        const existing = { ...(this.config.img_api[providerKey] || {}) };
        const keyEl = document.getElementById(`img-api-${providerKey}-api-key`);
        const baseEl = document.getElementById(`img-api-${providerKey}-api-base`);
        const modelInput = document.getElementById(`img-api-${providerKey}-model-input`);
        const modelSelect = document.getElementById(`img-api-${providerKey}-model`);
        if (keyEl) existing.api_key = keyEl.value;
        if (baseEl) existing.api_base = baseEl.value;
        if (modelInput?.value) existing.model = modelInput.value;
        else if (modelSelect?.value) existing.model = modelSelect.value;
        this.config.img_api[providerKey] = existing;
    }

    /** 保存时合并 DOM 与内存：仅当前可见表单从 DOM 读取，其余保留已存配置 */
    _pickImgAPIProviderConfig(providerKey, defaults = {}) {
        const existing = {
            ...(defaults || {}),
            ...(this.config.img_api?.[providerKey] || {}),
        };
        const keyEl = document.getElementById(`img-api-${providerKey}-api-key`);
        const baseEl = document.getElementById(`img-api-${providerKey}-api-base`);
        const modelInput = document.getElementById(`img-api-${providerKey}-model-input`);
        const modelSelect = document.getElementById(`img-api-${providerKey}-model`);
        return {
            ...existing,
            api_key: keyEl ? keyEl.value : (existing.api_key || ''),
            model: modelInput?.value || modelSelect?.value || existing.model || '',
            api_base: baseEl ? baseEl.value : (existing.api_base || ''),
        };
    }

    createImgApiKeyField(providerKey, apiKeyRaw, label = 'API KEY') {
        const raw = String(apiKeyRaw || '');
        const hasKey = raw.trim().length > 0;
        const keyCount = raw.split('\n').map((k) => k.trim()).filter(Boolean).length;
        const wrap = document.createElement('div');
        wrap.className = 'form-group form-group-full api-key-field';
        wrap.innerHTML = `
            <div class="api-key-field-head">
                <label>${label}${
                    hasKey
                        ? ` <span class="api-key-status">已配置${keyCount > 1 ? `（${keyCount} 个）` : ''}</span>`
                        : ''
                }</label>
                <div class="api-key-field-actions">
                    <button type="button" class="btn btn-ghost btn-xs api-key-toggle" title="显示/隐藏密钥">${
                        hasKey ? '显示' : ''
                    }</button>
                    <button type="button" class="btn btn-ghost btn-xs api-key-edit-btn" title="大窗口编辑">编辑</button>
                </div>
            </div>
            <textarea id="img-api-${providerKey}-api-key" class="api-key-input masked form-control" rows="3" placeholder="请输入 API Key，一行一个支持负载均衡" autocomplete="off">${this._escapeHtml(
                raw
            )}</textarea>
        `;
        const textarea = wrap.querySelector('textarea');
        const toggle = wrap.querySelector('.api-key-toggle');
        const editBtn = wrap.querySelector('.api-key-edit-btn');
        textarea.addEventListener('change', async () => {
            await this.updateImgAPIField(providerKey, 'api_key', textarea.value);
        });
        textarea.addEventListener('blur', async () => {
            await this.updateImgAPIField(providerKey, 'api_key', textarea.value);
        });
        if (toggle) {
            toggle.addEventListener('click', () => {
                const masked = textarea.classList.toggle('masked');
                toggle.textContent = masked ? '显示' : '隐藏';
            });
        }
        if (editBtn) {
            editBtn.addEventListener('click', (e) => {
                e.preventDefault();
                const keys = textarea.value.split('\n').map((k) => k.trim()).filter(Boolean);
                this.showImgAPIKeyEditor(providerKey, keys.length ? keys : []);
            });
        }
        return wrap;
    }

    // 填充图片 API UI（下拉 + 单卡表单）
    populateImgAPIUI() {
        this.loadCustomImgAPIs();
        this.syncVisibleImgAPIProviderFromDOM();

        const settingsBody = document.getElementById('img-api-settings-body');
        if (settingsBody) {
            settingsBody.innerHTML = '';
            settingsBody.appendChild(this.buildImgAPISettingsForm());
        }

        const container = document.getElementById('img-api-providers-container');
        if (!container || !this.config.img_api) return;

        const currentProviderKey = this.getCurrentImgAPIProviderKey();
        const providers = this.getImgProviderOptions();

        if (
            !this._selectedImgAPIProvider
            || !providers.some((p) => p.key === this._selectedImgAPIProvider)
        ) {
            const preferred = providers.find((p) => this.isImgProviderCurrent(p, currentProviderKey));
            this._selectedImgAPIProvider = preferred?.key || providers[0]?.key || null;
        }

        this.renderImgAPIProviderToolbar(providers, currentProviderKey);

        container.innerHTML = '';
        if (!providers.length) return;

        const selected = this.resolveImgProviderOption(this._selectedImgAPIProvider);
        if (!selected) return;

        if (selected.kind === 'custom' && selected.customIndex !== undefined) {
            const api = this.customImgAPIs[selected.customIndex];
            if (api) {
                const card = this.createCustomImgAPICard(api, selected.customIndex, true);
                container.appendChild(card);
            }
            return;
        }

        let providerData = this.config.img_api?.[selected.key];
        // 确保内置提供商始终有默认数据，避免新添加的提供商（如agnes）因配置缺失而不渲染表单
        const builtinDefaults = {
            'ali': { api_key: '', model: 'wanx2.0-t2i-turbo', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
            'modelscope': { api_key: '', model: 'Tongyi-MAI/Z-Image-Turbo', api_base: 'https://api-inference.modelscope.cn/v1' },
            'agnes': { api_key: '', model: 'agnes-image-2.1-flash', api_base: 'https://apihub.agnes-ai.com/v1' },
            'comfyui': { api_key: '', model: '', api_base: '' },
            'picsum': { api_key: '', model: '' },
        };
        if (!providerData && builtinDefaults[selected.key]) {
            providerData = builtinDefaults[selected.key];
            if (!this.config.img_api) this.config.img_api = {};
            this.config.img_api[selected.key] = providerData;
        }
        if (providerData) {
            const card = this.createImgAPIProviderCard(
                selected.key,
                selected.display,
                providerData,
                currentProviderKey,
                true
            );
            container.appendChild(card);
        }
    }

    // 加载自定义图片API配置
    loadCustomImgAPIs() {
        // 优先从后端配置加载（如果已经同步过）
        if (this.config.img_api && Array.isArray(this.config.img_api.custom) && this.config.img_api.custom.length > 0) {
            this.customImgAPIs = this.config.img_api.custom;
            // 同步到 localStorage 保持本地副本
            this.saveCustomImgAPIs();
        } else {
            // 否则从 localStorage 加载
            const stored = localStorage.getItem('custom_img_apis');
            if (stored) {
                try {
                    this.customImgAPIs = JSON.parse(stored);
                } catch (e) {
                    this.customImgAPIs = [];
                }
            }
        }
        // 注意：此处不再调用 renderCustomImgAPIs，
        // 而是由父级流程（如 populateImgAPIUI）统一调度渲染
    }

    // 保存自定义图片API到localStorage
    saveCustomImgAPIs() {
        localStorage.setItem('custom_img_apis', JSON.stringify(this.customImgAPIs));
    }

    renderCustomImgAPIs() {
        this.populateImgAPIUI();
    }

    // 创建自定义图片API卡片
    createCustomImgAPICard(api, index, compactToolbar = false) {
        const currentKey = this.getCurrentImgAPIProviderKey();
        const isCurrent = this.config.img_api?.api_type === 'custom'
            && (this.config.img_api.custom_index ?? 0) === index;

        const card = document.createElement('div');
        card.className = 'api-provider-card img-api-detail-card custom-api-card';
        card.dataset.index = index;
        if (isCurrent) {
            card.classList.add('active');
        }

        const header = document.createElement('div');
        header.className = 'custom-api-card-header';

        if (!compactToolbar) {
            const title = document.createElement('div');
            title.className = 'custom-api-card-title';
            title.textContent = api.name || `自定义图片API ${index + 1}`;

            const actions = document.createElement('div');
            actions.className = 'custom-api-card-actions';

            const useBtn = document.createElement('button');
            useBtn.className = `btn-use ${isCurrent ? 'active' : ''}`;
            useBtn.textContent = isCurrent ? '当前使用' : '设为当前';
            useBtn.onclick = () => this.setCurrentCustomImgAPI(index);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn-delete';
            deleteBtn.textContent = '删除';
            deleteBtn.onclick = () => this.deleteCustomImgAPI(index);

            actions.appendChild(useBtn);
            actions.appendChild(deleteBtn);
            header.appendChild(title);
            header.appendChild(actions);
        }

        const form = document.createElement('div');
        form.className = 'custom-api-form img-api-form';

        const { section: secBasic, body: basicBody } = this.createLLMFormSection(
            '基本信息',
            '服务名称与请求地址预览'
        );
        const nameGroup = document.createElement('div');
        nameGroup.className = 'form-group form-group-full';
        nameGroup.innerHTML = `
            <div class="api-preview-header">
                <label>服务名称</label>
                <div class="api-full-url-preview" id="img-api-url-preview-${index}">
                    请求预览：<span>${this.getImgAPIPullURL(api)}</span>
                </div>
            </div>
            <input type="text" value="${api.name || ''}" placeholder="例如：我的 Stable Diffusion" onchange="window.configManager.updateCustomImgAPI(${index}, 'name', this.value)">
        `;
        basicBody.appendChild(nameGroup);

        const { section: secAuth, body: authBody } = this.createLLMFormSection(
            '连接与认证',
            'OpenAI 兼容文生图接口'
        );
        const baseGroup = document.createElement('div');
        baseGroup.className = 'form-group form-group-full';
        baseGroup.innerHTML = `
            <label>API Base</label>
            <input type="text" value="${api.api_base || ''}" placeholder="https://api.openai.com/v1" onchange="window.configManager.updateCustomImgAPI(${index}, 'api_base', this.value)">
            <p class="field-help">末尾加 # 可强制使用原始地址，不自动补全路径</p>
        `;
        const keyGroup = document.createElement('div');
        keyGroup.className = 'form-group form-group-full';
        keyGroup.innerHTML = `
            <label>API KEY</label>
            <input type="password" value="${api.api_key || ''}" placeholder="Bearer Token" onchange="window.configManager.updateCustomImgAPI(${index}, 'api_key', this.value)">
        `;
        authBody.appendChild(baseGroup);
        authBody.appendChild(keyGroup);

        const { section: secModel, body: modelBody } = this.createLLMFormSection(
            '模型',
            '选择或输入文生图模型名'
        );
        const imgModelOptions = (api.models || []).map(m => `<option value="${m}" ${api.model === m ? 'selected' : ''}>${m}</option>`).join('');
        const modelGroup = document.createElement('div');
        modelGroup.className = 'form-group form-group-full';
        modelGroup.innerHTML = `
            <label>图片生成模型</label>
            <div class="model-select-wrapper">
                <select id="custom-img-model-select-${index}" onchange="window.configManager.updateCustomImgAPI(${index}, 'model', this.value)">
                    <option value="">请先刷新列表或手动输入</option>
                    ${imgModelOptions}
                </select>
                <button type="button" class="api-action-btn btn-fetch" onclick="window.configManager.fetchImgModels(${index})" title="获取模型列表">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
                </button>
            </div>
            <input type="text" id="custom-img-model-input-${index}" value="${api.model || ''}" placeholder="如 flux-pro、dall-e-3" style="margin-top:8px" onchange="window.configManager.updateCustomImgAPI(${index}, 'model', this.value)">
            <div id="test-result-custom-img-${index}" class="test-result-container" style="display: none; margin-top: 15px;">
                <div class="test-status"></div>
                <div class="test-image-preview" style="margin-top: 10px; text-align: center;">
                    <img src="" style="max-width: 100%; border-radius: 8px; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                </div>
            </div>
        `;
        modelBody.appendChild(modelGroup);

        form.appendChild(secBasic);
        form.appendChild(secAuth);
        form.appendChild(secModel);
        card.appendChild(header);
        card.appendChild(form);

        return card;
    }

    // 添加自定义图片API
    addCustomImgAPI() {
        this.customImgAPIs.push({
            name: '',
            api_base: '',
            api_key: '',
            model: '',
            models: [],
            isCurrent: false,
            tested: false
        });
        this.saveCustomImgAPIs();
        this._selectedImgAPIProvider = `custom:${this.customImgAPIs.length - 1}`;
        this.populateImgAPIUI();
    }

    // 删除自定义图片API
    deleteCustomImgAPI(index) {
        if (confirm('确定要删除这个自定义图片API吗?')) {
            if (this.customImgAPIs[index]?.isCurrent) {
                this.customImgAPIs.forEach((api, i) => {
                    if (api) api.isCurrent = false;
                });
            }
            this.customImgAPIs.splice(index, 1);
            this.saveCustomImgAPIs();
            this._selectedImgAPIProvider = this.getImgProviderOptions()[0]?.key || 'picsum';
            this.populateImgAPIUI();
        }
    }

    // 获取图片API模型列表（复用 /api/config/list-models 端点）
    async fetchImgModels(index) {
        const api = this.customImgAPIs[index];
        if (!api.api_base || !api.api_key) {
            alert('请先填写API BASE和API KEY');
            return;
        }

        try {
            const response = await fetch('/api/config/list-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_base: api.api_base,
                    api_key: api.api_key
                })
            });

            const result = await response.json();

            if (result.status === 'success' && result.models) {
                this.customImgAPIs[index].models = result.models;
                this.saveCustomImgAPIs();
                // 重新渲染图片API面板
                this.populateImgAPIUI();
                window.app?.showNotification(`已获取 ${result.models.length} 个模型`, 'success');
            } else {
                window.app?.showNotification(result.message || '未能获取模型列表，请手动输入', 'warning');
            }
        } catch (error) {
            console.error('获取图片模型列表失败:', error);
            window.app?.showNotification('获取模型列表失败', 'error');
        }
    }

    // 测试自定义图片API连通性
    async testCustomImgAPI(index) {
        const api = this.customImgAPIs[index];
        if (!api.api_base || !api.api_key) {
            window.app?.showNotification('请先填写 API 地址和 API Key', 'warning');
            return;
        }

        if (!api.model) {
            window.app?.showNotification('请先填写或选择模型名称', 'warning');
            const modelInput = document.getElementById(`custom-img-model-input-${index}`);
            if (modelInput) modelInput.focus();
            return;
        }

        const btn = document.getElementById(`btn-test-custom-img-${index}`);
        const resultContainer = document.getElementById(`test-result-custom-img-${index}`);

        if (!resultContainer) {
            console.error('Test result container not found for index:', index);
            return;
        }

        const statusDiv = resultContainer.querySelector('.test-status');
        const previewImg = resultContainer.querySelector('img');

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner"></span> 正在测试...`;
            btn.classList.add('spinning');
        }

        resultContainer.style.display = 'block';
        statusDiv.className = 'test-status info';
        statusDiv.innerHTML = '<i class="spinner"></i> 正在发送请求并生成图片 (可能需要 10-60 秒)...';
        previewImg.style.display = 'none';

        try {
            const response = await fetch('/api/config/test-custom-img-api', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_base: api.api_base,
                    api_key: api.api_key,
                    model: api.model
                })
            });

            const result = await response.json();

            if (result.status === 'success') {
                statusDiv.className = 'test-status success';
                statusDiv.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" style="margin-right:5px"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>${result.message}`;

                if (result.url) {
                    previewImg.src = result.url;
                    previewImg.style.display = 'block';
                }

                window.app?.showNotification('测试连接成功', 'success');
            } else {
                statusDiv.className = 'test-status error';
                statusDiv.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" style="margin-right:5px"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>${result.message}`;
                window.app?.showNotification(result.message || '测试连接失败', 'error');
            }
        } catch (error) {
            console.error('测试自定义图片API失败:', error);
            statusDiv.className = 'test-status error';
            statusDiv.innerHTML = `请求异常: ${error.message}`;
            window.app?.showNotification('请求异常', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 测试连接`;
                btn.classList.remove('spinning');
            }
        }
    }

    // 设置当前使用的自定义图片API
    async setCurrentCustomImgAPI(index) {
        const api = this.customImgAPIs[index];
        if (!api.name || !api.api_base) {
            window.app?.showNotification('请先填写API名称和接口地址', 'warning');
            return;
        }

        if (!api.model) {
            window.app?.showNotification('请先选择或输入模型名称', 'warning');
            return;
        }

        this.customImgAPIs.forEach((a, i) => {
            if (a) a.isCurrent = (i === index);
        });

        // 更新主配置，确保同步整个列表
        const imgApiConfig = { ...this.config.img_api };
        imgApiConfig.api_type = 'custom';
        imgApiConfig.custom_index = index;
        imgApiConfig.custom = this.customImgAPIs; // 同步整个列表以持久化

        await this.updateConfig({ img_api: imgApiConfig });

        this.saveCustomImgAPIs();
        this._selectedImgAPIProvider = `custom:${index}`;
        this.populateImgAPIUI();

        window.app?.showNotification(`已将${api.name}设为当前使用`, 'success');
    }
    // 更新自定义图片API字段
    updateCustomImgAPI(index, field, value) {
        if (this.customImgAPIs[index]) {
            this.customImgAPIs[index][field] = value;

            // 如果更新的是 model，同步更新下拉框和输入框
            if (field === 'model') {
                const select = document.getElementById(`custom-img-model-select-${index}`);
                const input = document.getElementById(`custom-img-model-input-${index}`);
                if (select && select.value !== value) select.value = value;
                if (input && input.value !== value) input.value = value;
            }

            // 实时更新 URL 预览
            const previewSpan = document.querySelector(`#img-api-url-preview-${index} span`);
            if (previewSpan) {
                previewSpan.textContent = this.getImgAPIPullURL(this.customImgAPIs[index]);
            }

            this.saveCustomImgAPIs();

            // 如果是当前正在使用的，也同步到 config 的 img_api（以便即时生效）
            if (this.customImgAPIs[index].isCurrent) {
                this.config.img_api.custom_index = index;
            }
        }
    }

    // 获取完整 API 调用预览地址
    getImgAPIPullURL(api) {
        if (!api.api_base) return '等待配置地址...';
        let base = api.api_base.trim().replace(/\/+$/, '');
        if (!base.endsWith('images/generations') && !base.endsWith('image-synthesis')) {
            return `${base}/images/generations`;
        }
        return base;
    }

    // 创建图片API提供商卡片
    createImgAPIProviderCard(providerKey, providerDisplay, providerData, currentProviderKey, compactToolbar = false) {
        const card = document.createElement('div');
        card.className = 'api-provider-card img-api-detail-card';
        if (providerKey === currentProviderKey) {
            card.classList.add('active');
        }

        const form = document.createElement('div');
        form.className = 'provider-form img-api-form';

        if (providerKey === 'picsum') {
            const { section, body } = this.createLLMFormSection(
                '说明',
                '免费随机图服务，无需配置 Key 与模型'
            );
            const note = document.createElement('p');
            note.className = 'img-api-settings-hint';
            note.style.margin = '0';
            note.textContent = '适合先跑通配图流程；画质与主题匹配度一般。设为当前使用后即可在生成文章时自动插入随机图。';
            body.appendChild(note);
            form.appendChild(section);
        } else {
            const { section: secAuth, body: authBody } = this.createLLMFormSection(
                '连接与认证',
                providerKey === 'comfyui' ? '本地 ComfyUI 服务地址' : 'API KEY 与接口地址'
            );

            if (['modelscope', 'ali', 'agnes', 'comfyui'].includes(providerKey)) {
                const apiBaseUrl = providerData.api_base || '';
                const baseUrlGroup = this.createFormGroup(
                    'API Base',
                    'text',
                    `img-api-${providerKey}-api-base`,
                    apiBaseUrl,
                    'API Base URL',
                    providerKey !== 'comfyui'
                );
                baseUrlGroup.classList.add('form-group-full');
                authBody.appendChild(baseUrlGroup);
            }

            if (providerKey !== 'comfyui') {
                authBody.appendChild(
                    this.createImgApiKeyField(providerKey, providerData.api_key || '', 'API KEY')
                );
            } else {
                authBody.appendChild(
                    this.createImgApiKeyField(
                        providerKey,
                        providerData.api_key || '',
                        'API KEY（可选）'
                    )
                );
            }
            form.appendChild(secAuth);

            const { section: secModel, body: modelBody } = this.createLLMFormSection(
                '模型',
                '文生图模型，可刷新列表或手动输入'
            );
            const builtinModels = (providerData.models || [])
                .map((m) => `<option value="${m}" ${providerData.model === m ? 'selected' : ''}>${m}</option>`)
                .join('');
            const modelGroup = document.createElement('div');
            modelGroup.className = 'form-group form-group-full';
            modelGroup.innerHTML = `
                <label>图片生成模型</label>
                <div class="model-select-wrapper">
                    <select id="img-api-${providerKey}-model" onchange="window.configManager.updateImgAPIField('${providerKey}', 'model', this.value)">
                        <option value="${providerData.model || ''}">${providerData.model || '请先刷新模型列表'}</option>
                        ${builtinModels}
                    </select>
                    <button type="button" class="model-dropdown-btn" onclick="window.configManager.fetchImgBuiltinModels('${providerKey}')" title="刷新模型列表">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
                    </button>
                </div>
                <input type="text" value="${providerData.model || ''}" placeholder="或手动输入模型名称" style="margin-top:8px" id="img-api-${providerKey}-model-input" onchange="window.configManager.updateImgAPIField('${providerKey}', 'model', this.value); document.getElementById('img-api-${providerKey}-model').value = this.value;">
                <div id="test-result-builtin-img-${providerKey}" class="test-result-container" style="display: none; margin-top: 15px;">
                    <div class="test-status"></div>
                    <div class="test-image-preview" style="margin-top: 10px; text-align: center;">
                        <img src="" style="max-width: 100%; border-radius: 8px; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                    </div>
                </div>
            `;
            modelBody.appendChild(modelGroup);
            form.appendChild(secModel);

            if (providerKey === 'comfyui') {
                const helpDiv = document.createElement('div');
                helpDiv.className = 'img-api-callout';
                helpDiv.innerHTML = `<strong>提示：</strong>请确保本机 ComfyUI 已启动并开启 <strong>Enable API</strong>。
                <a href="https://github.com/comfyanonymous/ComfyUI" target="_blank" rel="noopener">ComfyUI 文档</a>
                · 生成图保存在项目 <strong>image/</strong> 目录。测试连接请用工具栏「测试连接」。`;
                form.appendChild(helpDiv);
                const testResultDiv = document.createElement('div');
                testResultDiv.id = 'comfyui-test-result';
                testResultDiv.className = 'test-result';
                testResultDiv.style.display = 'none';
                testResultDiv.style.marginTop = '10px';
                form.appendChild(testResultDiv);
            }
        }

        card.appendChild(form);
        return card;
    }

    // 获取内置图片 API 提供商的模型列表
    async fetchImgBuiltinModels(providerKey) {
        const providerData = this.config.img_api?.[providerKey];
        if (!providerData) return;

        const apiBase = providerData.api_base || '';
        const apiKey = providerData.api_key || document.getElementById(`img-api-${providerKey}-api-key`)?.value || '';

        if (!apiBase || !apiKey) {
            alert('请先填写API KEY');
            return;
        }

        try {
            const response = await fetch('/api/config/list-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_base: apiBase, api_key: apiKey })
            });

            const result = await response.json();

            if (result.status === 'success' && result.models) {
                if (!this.config.img_api[providerKey].models) {
                    this.config.img_api[providerKey].models = [];
                }
                this.config.img_api[providerKey].models = result.models;
                this.populateImgAPIUI();
                window.app?.showNotification(`已获取 ${result.models.length} 个模型`, 'success');
            } else {
                window.app?.showNotification(result.message || '未能获取模型列表，请手动输入', 'warning');
            }
        } catch (error) {
            console.error('获取图片模型列表失败:', error);
            window.app?.showNotification('获取模型列表失败', 'error');
        }
    }

    // 实时更新内置图片API字段
    async updateImgAPIField(providerKey, field, value) {
        if (this.config.img_api && this.config.img_api[providerKey]) {
            this.config.img_api[providerKey][field] = value;

            // 实时同步到后端内存
            await this.updateConfig({
                img_api: {
                    [providerKey]: {
                        [field]: value
                    }
                }
            });
        }
    }

    // 切换当前图片API提供商  
    async setCurrentImgAPIProvider(providerKey) {
        await this.updateConfig({
            img_api: {
                ...this.config.img_api,
                api_type: providerKey
            }
        });

        // 刷新UI  
        this.populateImgAPIUI();

        let providerName = providerKey;
        if (providerKey === 'picsum') providerName = 'Picsum(随机)';
        else if (providerKey === 'ali') providerName = '阿里百炼';
        else if (providerKey === 'modelscope') providerName = '魔搭社区';
        else if (providerKey === 'agnes') providerName = 'Agnes AI';
        else if (providerKey === 'comfyui') providerName = 'ComfyUI';

        window.app?.showNotification(
            `已切换到${providerName}`,
            'success'
        );
    }

    // 更新图片API提供商字段  
    async updateImgAPIProviderField(providerKey, field, value) {
        await this.updateConfig({
            img_api: {
                ...this.config.img_api,
                [providerKey]: {
                    ...this.config.img_api[providerKey],
                    [field]: value
                }
            }
        });
    }
    // 保存图片API配置  
    async saveImgAPIConfig() {
        this.syncVisibleImgAPIProviderFromDOM();

        // 收集所有提供商的配置（未在页面展示的从内存保留，避免切换后保存清空其他 KEY）
        const imgApiConfig = {
            api_type: this.config.img_api.api_type,
            picsum: this._pickImgAPIProviderConfig('picsum'),
            ali: this._pickImgAPIProviderConfig('ali', {
                api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            }),
            modelscope: this._pickImgAPIProviderConfig('modelscope', {
                api_base: 'https://api-inference.modelscope.cn/v1',
            }),
            agnes: this._pickImgAPIProviderConfig('agnes', {
                api_base: 'https://apihub.agnes-ai.com/v1',
                model: 'agnes-image-2.1-flash',
            }),
            comfyui: this._pickImgAPIProviderConfig('comfyui'),
            settings: {
                default_timeout_seconds: parseInt(document.getElementById('img-api-settings-default-timeout')?.value || '60', 10),
                fast_mode_timeout_seconds: parseInt(document.getElementById('img-api-settings-fast-timeout')?.value || '45', 10),
                article_image_count: parseInt(
                    document.getElementById('img-api-settings-article-image-count')?.value
                    || document.getElementById('article-image-count')?.value
                    || String(this.config.img_api?.settings?.article_image_count ?? 3),
                    10
                ),
                fast_mode_prompt_count: parseInt(document.getElementById('img-api-settings-article-image-count')?.value || '3', 10),
                fast_mode_prompt_excerpt_length: parseInt(document.getElementById('img-api-settings-fast-prompt-excerpt')?.value || '120', 10),
                allow_placeholder_fallback: !!document.getElementById('img-api-settings-allow-placeholder-fallback')?.checked
            }
        };

        imgApiConfig.settings.default_timeout_seconds = Math.max(5, Math.min(600, imgApiConfig.settings.default_timeout_seconds || 60));
        imgApiConfig.settings.fast_mode_timeout_seconds = Math.max(5, Math.min(600, imgApiConfig.settings.fast_mode_timeout_seconds || 45));
        imgApiConfig.settings.article_image_count = Math.max(1, Math.min(12, imgApiConfig.settings.article_image_count || 3));
        imgApiConfig.settings.fast_mode_prompt_count = imgApiConfig.settings.article_image_count;
        imgApiConfig.settings.fast_mode_prompt_excerpt_length = Math.max(40, Math.min(300, imgApiConfig.settings.fast_mode_prompt_excerpt_length || 120));

        // 始终同步自定义列表到后端，确保数据持久化
        imgApiConfig.custom = this.customImgAPIs || [];

        // 如果当前是自定义模式，额外确保 api_type 和 custom_index 正确
        if (this.config.img_api.api_type === 'custom') {
            imgApiConfig.api_type = 'custom';
            imgApiConfig.custom_index = this.config.img_api.custom_index === undefined ? 0 : this.config.img_api.custom_index;
        }

        // 验证:如果选择阿里,必须填写API KEY  
        if (imgApiConfig.api_type === 'ali' && !imgApiConfig.ali.api_key.trim()) {
            window.app?.showNotification('阿里API需要配置API KEY', 'error');
            return;
        }

        // 验证:如果选择ComfyUI,必须填写API地址  
        if (imgApiConfig.api_type === 'comfyui' && !imgApiConfig.comfyui.api_base.trim()) {
            window.app?.showNotification('ComfyUI需要配置API地址', 'error');
            return;
        }

        // 更新配置  
        await this.updateConfig({ img_api: imgApiConfig });

        // 保存到文件  
        const success = await this.saveConfig();

        if (success) {
            // 清除未保存提示  
            const saveBtn = document.getElementById('save-img-api-config');
            if (saveBtn) {
                saveBtn.classList.remove('has-changes');
                saveBtn.innerHTML = '保存设置';
            }
        }

        window.app?.showNotification(
            success ? '图片API配置已保存' : '保存图片API配置失败',
            success ? 'success' : 'error'
        );
    }

    // 恢复默认图片API配置  
    async resetImgAPIConfig() {
        window.dialogManager.showConfirm(
            '确定要恢复默认图片API配置吗？这将清除所有自定义设置。',
            async () => {
                try {
                    const response = await fetch(`${this.apiEndpoint}/default`);
                    if (!response.ok) throw new Error('获取默认配置失败');

                    const result = await response.json();
                    const defaultImgAPI = result.data.img_api;

                    await this.updateConfig({ img_api: defaultImgAPI });
                    this.populateImgAPIUI();

                    window.app?.showNotification('已恢复默认图片API配置', 'success');
                } catch (error) {
                    window.app?.showNotification('恢复默认配置失败', 'error');
                }
            }
        );
    }

    // ========== AIForge自定义LLM提供商方法 ==========

    // 加载AIForge自定义提供商
    loadAiforgeCustomProviders() {
        const stored = localStorage.getItem('aiforge_custom_providers');
        if (stored) {
            try {
                this.aiforgeCustomProviders = JSON.parse(stored);
            } catch (e) {
                this.aiforgeCustomProviders = [];
            }
        }
        this.renderAiforgeCustomProviders();
    }

    // 保存AIForge自定义提供商到localStorage
    saveAiforgeCustomProviders() {
        localStorage.setItem('aiforge_custom_providers', JSON.stringify(this.aiforgeCustomProviders));
    }

    // 渲染AIForge自定义提供商卡片
    renderAiforgeCustomProviders() {
        const container = document.getElementById('aiforge-llm-providers-container');
        if (!container) return;

        container.innerHTML = '';

        // 先渲染预置的LLM提供商
        const aiforgeConfig = this.config.aiforge_config;
        if (this.config.aiforge_config && this.config.aiforge_config.llm) {
            const currentProvider = this.config.aiforge_config.default_llm_provider;
            const providers = Object.keys(this.config.aiforge_config.llm).map(key => ({
                key: key,
                display: key.charAt(0).toUpperCase() + key.slice(1)
            }));

            providers.forEach(provider => {
                const providerData = this.config.aiforge_config.llm[provider.key];
                if (providerData) {
                    const card = this.createAIForgeLLMProviderCard(
                        provider.key,
                        provider.display,
                        providerData,
                        currentProvider
                    );
                    container.appendChild(card);
                }
            });
        }

        // 再渲染自定义提供商
        this.aiforgeCustomProviders.forEach((api, index) => {
            const card = this.createAiforgeCustomProviderCard(api, index);
            container.appendChild(card);
        });
    }

    // 创建AIForge自定义提供商卡片
    createAiforgeCustomProviderCard(api, index) {
        const card = document.createElement('div');
        card.className = 'custom-api-card';
        card.dataset.index = index;

        const header = document.createElement('div');
        header.className = 'custom-api-card-header';

        const title = document.createElement('div');
        title.className = 'custom-api-card-title';
        title.textContent = api.name || `自定义LLM ${index + 1}`;

        const actions = document.createElement('div');
        actions.className = 'custom-api-card-actions';

        // 设为当前使用按钮
        const useBtn = document.createElement('button');
        const isCurrent = this.aiforgeCustomProviders[index]?.isCurrent;
        useBtn.className = `btn-use ${isCurrent ? 'active' : ''}`;
        useBtn.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> ${isCurrent ? '当前使用' : '设为当前'}`;
        useBtn.onclick = () => this.setCurrentAiforgeCustomProvider(index);

        // 测试按钮
        const testBtn = document.createElement('button');
        testBtn.className = 'btn-test';
        testBtn.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 测试`;
        testBtn.onclick = () => this.testAiforgeCustomProvider(index);

        // 删除按钮
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn-delete';
        deleteBtn.textContent = '删除';
        deleteBtn.onclick = () => this.deleteAiforgeCustomProvider(index);

        actions.appendChild(useBtn);
        actions.appendChild(testBtn);
        actions.appendChild(deleteBtn);
        header.appendChild(title);
        header.appendChild(actions);

        // 表单
        const form = document.createElement('div');
        form.className = 'custom-api-form';

        // 名称
        const nameGroup = document.createElement('div');
        nameGroup.className = 'form-group form-group-full';
        nameGroup.innerHTML = `
            <label>LLM名称</label>
            <input type="text" value="${api.name || ''}" placeholder="例如: 我的OpenAI" onchange="window.configManager.updateAiforgeCustomProvider(${index}, 'name', this.value)">
        `;

        // API Base
        const baseGroup = document.createElement('div');
        baseGroup.className = 'form-group form-group-full';
        baseGroup.innerHTML = `
            <label>API BASE</label>
            <input type="text" value="${api.api_base || ''}" placeholder="例如: https://api.openai.com/v1 (末尾加#强制使用原始地址)" onchange="window.configManager.updateAiforgeCustomProvider(${index}, 'api_base', this.value)">
            <small style="color:#888;font-size:11px;">💡 提示：系统会自动补全/v1路径，如需强制使用原始地址请在末尾添加#</small>
        `;

        // API Key
        const keyGroup = document.createElement('div');
        keyGroup.className = 'form-group form-group-full';
        keyGroup.innerHTML = `
            <label>API KEY</label>
            <input type="password" value="${api.api_key || ''}" placeholder="输入API Key" onchange="window.configManager.updateAiforgeCustomProvider(${index}, 'api_key', this.value)">
        `;

        // 模型选择
        const modelGroup = document.createElement('div');
        modelGroup.className = 'form-group form-group-full';
        const modelOptions = (api.models || []).map(m => `<option value="${m}" ${api.model === m ? 'selected' : ''}>${m}</option>`).join('');
        modelGroup.innerHTML = `
            <label>模型</label>
            <div class="model-select-wrapper">
                <select onchange="window.configManager.updateAiforgeCustomProvider(${index}, 'model', this.value)">
                    <option value="">请先测试API获取模型</option>
                    ${modelOptions}
                </select>
            </div>
        `;

        // 提供商选择
        const providerGroup = document.createElement('div');
        providerGroup.className = 'form-group form-group-full';
        providerGroup.innerHTML = `
            <label>提供商 (Provider) <span style="color:#999;font-weight:normal;">(可选)</span></label>
            <input type="text" value="${api.provider || ''}" placeholder="例如: openai, anthropic, zhipu 等" onchange="window.configManager.updateAiforgeCustomProvider(${index}, 'provider', this.value)">
            <small class="form-help" style="color:#999;">填写litellm支持的提供商名称，留空则自动识别</small>
        `;

        // 测试结果
        const resultDiv = document.createElement('div');
        resultDiv.id = `aiforge-test-result-${index}`;
        resultDiv.className = 'test-result';
        resultDiv.style.display = 'none';

        form.appendChild(nameGroup);
        form.appendChild(baseGroup);
        form.appendChild(keyGroup);
        form.appendChild(modelGroup);
        form.appendChild(providerGroup);
        form.appendChild(resultDiv);

        card.appendChild(header);
        card.appendChild(form);

        return card;
    }

    // 添加AIForge自定义提供商
    addAiforgeCustomProvider() {
        this.aiforgeCustomProviders.push({
            name: '',
            api_base: '',
            api_key: '',
            model: '',
            models: [],
            provider: '',
            isCurrent: false,
            tested: false
        });
        this.saveAiforgeCustomProviders();
        this.renderAiforgeCustomProviders();
    }

    // 删除AIForge自定义提供商
    deleteAiforgeCustomProvider(index) {
        if (confirm('确定要删除这个自定义LLM提供商吗?')) {
            if (this.aiforgeCustomProviders[index]?.isCurrent) {
                this.aiforgeCustomProviders.forEach((api, i) => {
                    if (api) api.isCurrent = false;
                });
            }
            this.aiforgeCustomProviders.splice(index, 1);
            this.saveAiforgeCustomProviders();
            this.renderAiforgeCustomProviders();
        }
    }

    // 设置当前使用的AIForge自定义LLM
    async setCurrentAiforgeCustomProvider(index) {
        const api = this.aiforgeCustomProviders[index];
        if (!api || !api.tested) {
            window.app?.showNotification('请先测试API后再设为当前使用', 'warning');
            return;
        }

        // 更新当前使用状态
        this.aiforgeCustomProviders.forEach((a, i) => {
            if (a) a.isCurrent = (i === index);
        });

        this.saveAiforgeCustomProviders();

        // 更新后端配置
        await this.updateConfig({
            aiforge_config: {
                ...this.config.aiforge_config,
                default_llm_provider: `custom_${index}`,
                llm: {
                    ...this.config.aiforge_config.llm,
                    [`custom_${index}`]: {
                        type: 'custom',
                        model: api.model,
                        api_key: api.api_key,
                        base_url: api.api_base,
                        provider: api.provider || ''
                    }
                }
            }
        });

        this.renderAiforgeCustomProviders();
        window.app?.showNotification('已切换到自定义LLM', 'success');
    }

    // 更新AIForge自定义提供商字段
    updateAiforgeCustomProvider(index, field, value) {
        if (this.aiforgeCustomProviders[index]) {
            this.aiforgeCustomProviders[index][field] = value;
            this.aiforgeCustomProviders[index].tested = false;
            this.saveAiforgeCustomProviders();
        }
    }

    // 测试AIForge自定义LLM
    async testAiforgeCustomProvider(index) {
        const api = this.aiforgeCustomProviders[index];
        if (!api.api_base || !api.api_key) {
            alert('请填写API BASE和API KEY');
            return;
        }

        const testBtn = document.querySelector(`.custom-api-card[data-index="${index}"] .btn-test`);
        const resultDiv = document.getElementById(`aiforge-test-result-${index}`);

        testBtn.disabled = true;
        testBtn.textContent = '测试中...';

        try {
            const response = await fetch('/api/config/test-custom-api', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: api.name,
                    api_base: api.api_base,
                    api_key: api.api_key,
                    model: api.model || 'gpt-3.5-turbo',
                    provider: api.provider || ''
                })
            });

            const result = await response.json();

            resultDiv.style.display = 'block';
            if (result.status === 'success') {
                resultDiv.className = 'test-result success';
                resultDiv.textContent = '✅ ' + result.message;
                this.aiforgeCustomProviders[index].tested = true;
                this.saveAiforgeCustomProviders();

                // 自动获取模型列表
                await this.fetchAiforgeModels(index);
            } else {
                resultDiv.className = 'test-result error';
                resultDiv.textContent = '❌ ' + result.message;
                this.aiforgeCustomProviders[index].tested = false;
            }
        } catch (error) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'test-result error';
            resultDiv.textContent = '❌ 测试失败: ' + error.message;
        }

        testBtn.disabled = false;
        testBtn.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 测试`;
    }

    // 获取AIForge自定义LLM模型列表
    async fetchAiforgeModels(index) {
        const api = this.aiforgeCustomProviders[index];
        if (!api.api_base || !api.api_key) {
            alert('请先填写API BASE和API KEY');
            return;
        }

        try {
            const response = await fetch('/api/config/list-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_base: api.api_base,
                    api_key: api.api_key
                })
            });

            const result = await response.json();

            if (result.status === 'success' && result.models) {
                this.aiforgeCustomProviders[index].models = result.models;
                this.saveAiforgeCustomProviders();
                this.renderAiforgeCustomProviders();
                window.app?.showNotification(`获取到${result.models.length}个模型`, 'success');
            }
        } catch (error) {
            console.error('获取模型列表失败:', error);
        }
    }

    // 填充AIForge配置UI  
    populateAIForgeUI() {
        if (!this.config.aiforge_config) return;

        const aiforgeConfig = this.config.aiforge_config;

        // 填充通用配置  
        const maxRoundsInput = document.getElementById('aiforge-max-rounds');
        if (maxRoundsInput && aiforgeConfig.max_rounds !== undefined) {
            maxRoundsInput.value = aiforgeConfig.max_rounds;
        }

        const defaultMaxTokensInput = document.getElementById('aiforge-default-max-tokens');
        if (defaultMaxTokensInput && aiforgeConfig.max_tokens !== undefined) {
            defaultMaxTokensInput.value = aiforgeConfig.max_tokens;
        }

        // 填充缓存配置  
        if (aiforgeConfig.cache && aiforgeConfig.cache.code) {
            const cacheConfig = aiforgeConfig.cache.code;

            const cacheEnabledCheckbox = document.getElementById('cache-enabled');
            if (cacheEnabledCheckbox && cacheConfig.enabled !== undefined) {
                cacheEnabledCheckbox.checked = cacheConfig.enabled;
            }

            const maxModulesInput = document.getElementById('cache-max-modules');
            if (maxModulesInput && cacheConfig.max_modules !== undefined) {
                maxModulesInput.value = cacheConfig.max_modules;
            }

            const failureThresholdInput = document.getElementById('cache-failure-threshold');
            if (failureThresholdInput && cacheConfig.failure_threshold !== undefined) {
                failureThresholdInput.value = cacheConfig.failure_threshold;
            }

            const maxAgeDaysInput = document.getElementById('cache-max-save-days');
            if (maxAgeDaysInput && cacheConfig.max_age_days !== undefined) {
                maxAgeDaysInput.value = cacheConfig.max_age_days;
            }

            const cleanupIntervalInput = document.getElementById('cache-cleanup-interval');
            if (cleanupIntervalInput && cacheConfig.cleanup_interval !== undefined) {
                cleanupIntervalInput.value = cacheConfig.cleanup_interval;
            }
        }

        // 填充LLM提供商卡片  
        this.populateAIForgeLLMUI();
    }

    // 填充AIForge LLM提供商UI  
    populateAIForgeLLMUI() {
        const container = document.getElementById('aiforge-llm-providers-container');
        if (!container || !this.config.aiforge_config) return;

        const aiforgeConfig = this.config.aiforge_config;
        const currentProvider = aiforgeConfig.default_llm_provider;

        // 清空现有内容  
        container.innerHTML = '';

        // 获取所有LLM提供商  
        const providers = Object.keys(aiforgeConfig.llm).map(key => ({
            key: key,
            display: key.charAt(0).toUpperCase() + key.slice(1)
        }));

        // 为每个提供商生成卡片  
        providers.forEach(provider => {
            const providerData = aiforgeConfig.llm[provider.key];
            if (providerData) {
                const card = this.createAIForgeLLMProviderCard(
                    provider.key,
                    provider.display,
                    providerData,
                    currentProvider
                );
                container.appendChild(card);
            }
        });
    }

    // 创建AIForge LLM提供商卡片  
    createAIForgeLLMProviderCard(providerKey, providerDisplay, providerData, currentProvider) {
        const card = document.createElement('div');
        card.className = 'api-provider-card';
        if (providerKey === currentProvider) {
            card.classList.add('active');
        }

        // ========== 卡片头部 ==========  
        const header = document.createElement('div');
        header.className = 'provider-header';

        const titleGroup = document.createElement('div');
        titleGroup.className = 'provider-title-group';

        const name = document.createElement('div');
        name.className = 'provider-name';
        name.textContent = providerDisplay;

        const badge = document.createElement('span');
        badge.className = `provider-badge ${providerKey === currentProvider ? 'active' : 'inactive'}`;
        badge.textContent = providerKey === currentProvider ? '使用中' : '未使用';

        titleGroup.appendChild(name);
        titleGroup.appendChild(badge);

        const toggleBtn = document.createElement('button');
        toggleBtn.className = `provider-toggle-btn ${providerKey === currentProvider ? 'active' : ''}`;
        toggleBtn.textContent = providerKey === currentProvider ? '当前使用' : '设为当前';
        toggleBtn.disabled = providerKey === currentProvider;
        toggleBtn.addEventListener('click', async () => {
            await this.setCurrentAIForgeLLMProvider(providerKey);
        });

        header.appendChild(titleGroup);
        header.appendChild(toggleBtn);

        // ========== 表单内容 ==========  
        const form = document.createElement('div');
        form.className = 'provider-form';

        // ✅ 第一行:类型、模型、API KEY(三个字段)  
        const row1 = document.createElement('div');
        row1.className = 'form-row';

        // 类型(只读)  
        const typeGroup = this.createFormGroup(
            '类型',
            'text',
            `aiforge-${providerKey}-type`,
            providerData.type || '',
            '',
            false,
            false
        );
        typeGroup.classList.add('form-group-third');
        const typeInput = typeGroup.querySelector('input');
        if (typeInput) {
            typeInput.disabled = true;
            typeInput.style.userSelect = 'none';
            typeInput.style.cursor = 'not-allowed';
        }

        // 模型  
        const modelGroup = this.createFormGroup(
            '模型',
            'text',
            `aiforge-${providerKey}-model`,
            providerData.model || '',
            '使用的具体模型名称',
            true
        );
        modelGroup.classList.add('form-group-third');

        // API KEY  
        const apiKeyGroup = this.createFormGroup(
            'API KEY',
            'text',
            `aiforge-${providerKey}-api-key`,
            providerData.api_key || '',
            '模型提供商的API KEY',
            true
        );
        apiKeyGroup.classList.add('form-group-third');

        row1.appendChild(typeGroup);
        row1.appendChild(modelGroup);
        row1.appendChild(apiKeyGroup);

        // ✅ 第二行:Base URL、超时时间、最大Tokens(三个字段)  
        const row2 = document.createElement('div');
        row2.className = 'form-row';

        // Base URL  
        const baseUrlGroup = this.createFormGroup(
            'Base URL',
            'text',
            `aiforge-${providerKey}-base-url`,
            providerData.base_url || '',
            'API的基础地址',
            true,
            true
        );
        baseUrlGroup.classList.add('form-group-third');

        // 超时时间  
        const timeoutGroup = this.createFormGroup(
            '超时时间(秒)',
            'number',
            `aiforge-${providerKey}-timeout`,
            providerData.timeout || 30,
            'API请求的超时时间'
        );
        timeoutGroup.classList.add('form-group-third');

        // 最大Tokens  
        const maxTokensGroup = this.createFormGroup(
            '最大Tokens',
            'number',
            `aiforge-${providerKey}-max-tokens`,
            providerData.max_tokens || 8192,
            '控制生成内容的长度'
        );
        maxTokensGroup.classList.add('form-group-third');

        row2.appendChild(baseUrlGroup);
        row2.appendChild(timeoutGroup);
        row2.appendChild(maxTokensGroup);

        // ========== 组装表单 ==========  
        form.appendChild(row1);
        form.appendChild(row2);

        // ========== 组装卡片 ==========  
        card.appendChild(header);
        card.appendChild(form);

        return card;
    }

    // 切换当前AIForge LLM提供商  
    async setCurrentAIForgeLLMProvider(providerKey) {
        await this.updateConfig({
            aiforge_config: {
                ...this.config.aiforge_config,
                default_llm_provider: providerKey
            }
        });

        // 刷新UI  
        this.populateAIForgeLLMUI();

        window.app?.showNotification(
            `已切换到${providerKey}`,
            'success'
        );
    }

    // 更新AIForge LLM提供商字段  
    async updateAIForgeLLMProviderField(providerKey, field, value) {
        // 字段名映射  
        const fieldMap = {
            'api-key': 'api_key',
            'base-url': 'base_url',
            'max-tokens': 'max_tokens'
        };
        const actualField = fieldMap[field] || field;

        // 类型字段是只读的,不更新  
        if (actualField === 'type') {
            return;
        }

        await this.updateConfig({
            aiforge_config: {
                ...this.config.aiforge_config,
                llm: {
                    ...this.config.aiforge_config.llm,
                    [providerKey]: {
                        ...this.config.aiforge_config.llm[providerKey],
                        [actualField]: value
                    }
                }
            }
        });
    }

    bindCreativeConfigListeners() {
        if (this._creativeBindingsReady) return;
        this._creativeBindingsReady = true;

        const markDirty = () => {
            const btn = document.getElementById('save-creative-config');
            if (btn && !btn.classList.contains('has-changes')) {
                btn.classList.add('has-changes');
                btn.innerHTML = '保存设置 <span style="color: var(--warning-color);">(有未保存更改)</span>';
            }
        };

        const patchCreative = async (patch) => {
            await this.updateConfig({
                dimensional_creative: {
                    ...this.config.dimensional_creative,
                    ...patch
                }
            });
            markDirty();
        };

        document.getElementById('creative-enabled')?.addEventListener('change', async (e) => {
            await patchCreative({ enabled: e.target.checked });
            this.updateCreativeControlsState();
        });

        document.getElementById('auto-dimension-selection')?.addEventListener('change', async (e) => {
            await patchCreative({ auto_dimension_selection: e.target.checked });
            this.updateCreativeControlsState();
        });

        document.getElementById('preserve-core-info')?.addEventListener('change', async (e) => {
            await patchCreative({ preserve_core_info: e.target.checked });
        });

        document.getElementById('allow-experimental')?.addEventListener('change', async (e) => {
            await patchCreative({ allow_experimental: e.target.checked });
        });

        document.getElementById('creative-intensity')?.addEventListener('input', async (e) => {
            this.updateCreativeSliderLabels();
            await patchCreative({ creative_intensity: parseFloat(e.target.value) });
        });

        document.getElementById('compatibility-threshold')?.addEventListener('input', async (e) => {
            this.updateCreativeSliderLabels();
            await patchCreative({ compatibility_threshold: parseFloat(e.target.value) });
        });

        document.getElementById('max-dimensions')?.addEventListener('change', async (e) => {
            await patchCreative({ max_dimensions: parseInt(e.target.value, 10) || 3 });
        });

        document.getElementById('save-creative-config')?.addEventListener('click', async () => {
            await this.syncDimensionalCreativeFromUI();
            const success = await this.saveConfig();
            const btn = document.getElementById('save-creative-config');
            if (success && btn) {
                btn.classList.remove('has-changes');
                btn.innerHTML = '保存设置';
            }
            window.app?.showNotification(
                success ? '创意配置已保存' : '保存创意配置失败',
                success ? 'success' : 'error'
            );
        });

        document.getElementById('reset-creative-config')?.addEventListener('click', async () => {
            const response = await fetch(`${this.apiEndpoint}/default`);
            if (!response.ok) {
                window.app?.showNotification('恢复默认配置失败', 'error');
                return;
            }
            const result = await response.json();
            await this.updateConfig({ dimensional_creative: result.data.dimensional_creative });
            this.populateCreativeUI();
            window.app?.showNotification('已恢复默认创意配置', 'info');
        });

        document.getElementById('creative-expand-all')?.addEventListener('click', () => {
            document.querySelectorAll('.creative-dimension-card .creative-dimension-body').forEach((el) => {
                el.classList.remove('collapsed');
            });
            document.querySelectorAll('.creative-dimension-chevron').forEach((el) => el.classList.add('rotated'));
        });

        document.getElementById('creative-collapse-all')?.addEventListener('click', () => {
            document.querySelectorAll('.creative-dimension-card .creative-dimension-body').forEach((el) => {
                el.classList.add('collapsed');
            });
            document.querySelectorAll('.creative-dimension-chevron').forEach((el) => el.classList.remove('rotated'));
        });

        document.getElementById('creative-enable-recommended')?.addEventListener('click', async () => {
            const enabled = { ...(this.config.dimensional_creative?.enabled_dimensions || {}) };
            this._creativeRecommendedDimensions.forEach((key) => {
                enabled[key] = true;
            });
            await patchCreative({ enabled_dimensions: enabled, auto_dimension_selection: false });
            this.populateCreativeUI();
        });
    }

    updateCreativeSliderLabels() {
        const intensity = document.getElementById('creative-intensity');
        const intensityVal = document.getElementById('creative-intensity-val');
        if (intensity && intensityVal) intensityVal.textContent = intensity.value;

        const threshold = document.getElementById('compatibility-threshold');
        const thresholdVal = document.getElementById('compatibility-threshold-val');
        if (threshold && thresholdVal) thresholdVal.textContent = threshold.value;
    }

    async syncDimensionalCreativeFromUI() {
        if (!this.config.dimensional_creative) return;

        const selected_dimensions = [];
        Object.entries(this.DIMENSION_GROUPS).forEach(([, groupData]) => {
            groupData.dimensions.forEach((dimensionKey) => {
                const checkbox = document.getElementById(`dimension-${dimensionKey}-enabled`);
                const select = document.getElementById(`dimension-${dimensionKey}-select`);
                if (!checkbox?.checked) return;
                const option = select?.value || '';
                selected_dimensions.push({ category: dimensionKey, option });
            });
        });

        await this.updateConfig({
            dimensional_creative: {
                ...this.collectDimensionalCreativeFromForm(),
                selected_dimensions
            }
        });
    }

    collectDimensionalCreativeFromForm() {
        return {
            enabled: document.getElementById('creative-enabled')?.checked || false,
            creative_intensity: parseFloat(document.getElementById('creative-intensity')?.value || '1'),
            preserve_core_info: document.getElementById('preserve-core-info')?.checked !== false,
            allow_experimental: document.getElementById('allow-experimental')?.checked || false,
            auto_dimension_selection: document.getElementById('auto-dimension-selection')?.checked !== false,
            max_dimensions: parseInt(document.getElementById('max-dimensions')?.value || '3', 10),
            compatibility_threshold: parseFloat(document.getElementById('compatibility-threshold')?.value || '0.6')
        };
    }

    // 填充创意配置UI  
    populateCreativeUI() {
        if (!this.config.dimensional_creative) return;

        const creativeConfig = this.config.dimensional_creative;

        const enabledCheckbox = document.getElementById('creative-enabled');
        if (enabledCheckbox) enabledCheckbox.checked = !!creativeConfig.enabled;

        const intensitySlider = document.getElementById('creative-intensity');
        if (intensitySlider) intensitySlider.value = creativeConfig.creative_intensity ?? 1.0;

        const preserveCheckbox = document.getElementById('preserve-core-info');
        if (preserveCheckbox) preserveCheckbox.checked = creativeConfig.preserve_core_info !== false;

        const autoSelectionCheckbox = document.getElementById('auto-dimension-selection');
        if (autoSelectionCheckbox) {
            autoSelectionCheckbox.checked = creativeConfig.auto_dimension_selection !== false;
        }

        const maxDimensionsInput = document.getElementById('max-dimensions');
        if (maxDimensionsInput) maxDimensionsInput.value = creativeConfig.max_dimensions ?? 3;

        const thresholdSlider = document.getElementById('compatibility-threshold');
        if (thresholdSlider) thresholdSlider.value = creativeConfig.compatibility_threshold ?? 0.6;

        const experimentalCheckbox = document.getElementById('allow-experimental');
        if (experimentalCheckbox) experimentalCheckbox.checked = !!creativeConfig.allow_experimental;

        this.updateCreativeSliderLabels();
        this.populateDimensionGroups();
        this.updateCreativeControlsState();
    }

    // 生成维度分组卡片  
    populateDimensionGroups() {
        const container = document.getElementById('dimension-groups-container');
        if (!container || !this.config.dimensional_creative) return;

        const creativeConfig = this.config.dimensional_creative;
        const dimensionOptions = creativeConfig.dimension_options || {};
        const enabledDimensions = creativeConfig.enabled_dimensions || {};
        const autoSelection = creativeConfig.auto_dimension_selection || false;
        const globalEnabled = creativeConfig.enabled || false;

        container.innerHTML = '';

        // 为每个维度分组创建卡片  
        Object.entries(this.DIMENSION_GROUPS).forEach(([groupKey, groupData]) => {
            const card = this.createDimensionGroupCard(
                groupKey,
                groupData,
                dimensionOptions,
                enabledDimensions,
                autoSelection,
                globalEnabled
            );
            container.appendChild(card);
        });
    }

    updateCreativeControlsState() {
        const globalEnabled = document.getElementById('creative-enabled')?.checked || false;
        const autoSelection = document.getElementById('auto-dimension-selection')?.checked !== false;

        const intensitySlider = document.getElementById('creative-intensity');
        const preserveCheckbox = document.getElementById('preserve-core-info');
        const experimentalCheckbox = document.getElementById('allow-experimental');
        const autoSelectionCheckbox = document.getElementById('auto-dimension-selection');
        const maxDimensionsInput = document.getElementById('max-dimensions');
        const thresholdSlider = document.getElementById('compatibility-threshold');
        const autoParams = document.getElementById('creative-auto-params');
        const manualHint = document.getElementById('creative-manual-hint');
        const modeTitle = document.getElementById('creative-mode-title');
        const modeDesc = document.getElementById('creative-mode-desc');
        const enabledPill = document.getElementById('creative-enabled-pill');
        const dimToolbar = document.querySelector('.creative-dim-toolbar');

        if (intensitySlider) intensitySlider.disabled = !globalEnabled;
        if (preserveCheckbox) preserveCheckbox.disabled = !globalEnabled;
        if (experimentalCheckbox) experimentalCheckbox.disabled = !globalEnabled;
        if (autoSelectionCheckbox) autoSelectionCheckbox.disabled = !globalEnabled;
        if (maxDimensionsInput) maxDimensionsInput.disabled = !globalEnabled || !autoSelection;
        if (thresholdSlider) thresholdSlider.disabled = !globalEnabled || !autoSelection;
        if (autoParams) autoParams.classList.toggle('is-disabled', !globalEnabled || !autoSelection);
        if (manualHint) manualHint.hidden = autoSelection || !globalEnabled;
        if (dimToolbar) dimToolbar.classList.toggle('is-manual-only', autoSelection);

        if (enabledPill) {
            enabledPill.textContent = globalEnabled ? '已启用' : '未启用';
            enabledPill.classList.toggle('is-on', globalEnabled);
        }
        if (modeTitle) modeTitle.textContent = autoSelection ? '自动选维' : '手动选维';
        if (modeDesc) {
            modeDesc.textContent = autoSelection
                ? 'AI 按内容类型挑选维度组合，无需逐项勾选'
                : '请勾选下方维度并选择预设；未勾选任何维度时创意步骤将跳过';
        }

        let manualEnabledCount = 0;
        Object.entries(this.DIMENSION_GROUPS).forEach(([groupKey, groupData]) => {
            let enabledCount = 0;
            groupData.dimensions.forEach((dimensionKey) => {
                const checkbox = document.getElementById(`dimension-${dimensionKey}-enabled`);
                const select = document.getElementById(`dimension-${dimensionKey}-select`);
                const customInput = document.getElementById(`dimension-${dimensionKey}-custom`);
                const isRowOn = checkbox?.checked || false;
                if (isRowOn) {
                    enabledCount++;
                    manualEnabledCount++;
                }

                if (checkbox) checkbox.disabled = !globalEnabled || autoSelection;
                if (select) select.disabled = !globalEnabled || autoSelection || !isRowOn;
                if (customInput) {
                    customInput.disabled = !globalEnabled || !isRowOn || select?.value !== 'custom';
                }
            });

            const badge = document.querySelector(`[data-group-badge="${groupKey}"]`);
            if (badge) badge.textContent = `${enabledCount}/${groupData.dimensions.length}`;
        });

        const modeBar = document.getElementById('creative-mode-bar');
        if (modeBar && !autoSelection && globalEnabled && manualEnabledCount === 0) {
            modeBar.classList.add('is-warning');
        } else if (modeBar) {
            modeBar.classList.remove('is-warning');
        }
    }

    createDimensionGroupCard(groupKey, groupData, dimensionOptions, enabledDimensions, autoSelection, globalEnabled) {
        const card = document.createElement('div');
        card.className = 'creative-dimension-card dimension-group-card';
        card.dataset.groupKey = groupKey;

        const header = document.createElement('button');
        header.type = 'button';
        header.className = 'creative-dimension-header dimension-group-header';

        const titleGroup = document.createElement('div');
        titleGroup.className = 'dimension-group-title-group';

        const emoji = document.createElement('span');
        emoji.className = 'creative-dimension-emoji';
        emoji.textContent = groupData.emoji || '◆';

        const name = document.createElement('span');
        name.className = 'dimension-group-name';
        name.textContent = groupData.name;

        const enabledCount = groupData.dimensions.filter((dim) => enabledDimensions[dim] === true).length;
        const badge = document.createElement('span');
        badge.className = 'dimension-count-badge';
        badge.dataset.groupBadge = groupKey;
        badge.textContent = `${enabledCount}/${groupData.dimensions.length}`;

        titleGroup.appendChild(emoji);
        titleGroup.appendChild(name);
        titleGroup.appendChild(badge);

        const chevron = document.createElement('span');
        chevron.className = 'creative-dimension-chevron dimension-toggle-icon';
        chevron.textContent = '▾';

        header.appendChild(titleGroup);
        header.appendChild(chevron);

        const content = document.createElement('div');
        content.className = 'creative-dimension-body dimension-group-content';

        groupData.dimensions.forEach((dimensionKey) => {
            const dimensionData = dimensionOptions[dimensionKey];
            if (!dimensionData) return;
            content.appendChild(
                this.createDimensionRow(
                    dimensionKey,
                    dimensionData,
                    !!enabledDimensions[dimensionKey],
                    globalEnabled,
                    autoSelection
                )
            );
        });

        header.addEventListener('click', () => {
            content.classList.toggle('collapsed');
            chevron.classList.toggle('rotated');
        });

        card.appendChild(header);
        card.appendChild(content);
        return card;
    }

    createDimensionRow(dimensionKey, dimensionData, isEnabled, globalEnabled, autoSelection) {
        const row = document.createElement('div');
        row.className = 'creative-dimension-row dimension-row';

        const top = document.createElement('div');
        top.className = 'creative-dimension-row-top';

        const checkboxLabel = document.createElement('label');
        checkboxLabel.className = 'checkbox-label creative-dimension-check';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `dimension-${dimensionKey}-enabled`;
        checkbox.className = 'dimension-checkbox';
        checkbox.checked = isEnabled;
        checkbox.disabled = !globalEnabled || autoSelection;

        const checkboxCustom = document.createElement('span');
        checkboxCustom.className = 'checkbox-custom';
        checkboxLabel.appendChild(checkbox);
        checkboxLabel.appendChild(checkboxCustom);

        const label = document.createElement('span');
        label.className = 'dimension-name-label';
        label.textContent = dimensionData.name || dimensionKey;

        top.appendChild(checkboxLabel);
        top.appendChild(label);

        const fields = document.createElement('div');
        fields.className = 'creative-dimension-fields';

        const select = document.createElement('select');
        select.id = `dimension-${dimensionKey}-select`;
        select.className = 'dimension-select form-control';
        select.disabled = !globalEnabled || autoSelection || !isEnabled;

        const autoOption = document.createElement('option');
        autoOption.value = '';
        autoOption.textContent = '自动选择预设';
        select.appendChild(autoOption);

        (dimensionData.preset_options || []).forEach((option) => {
            const opt = document.createElement('option');
            opt.value = option.name;
            opt.textContent = option.value || option.name;
            opt.title = option.description || '';
            select.appendChild(opt);
        });

        const customOption = document.createElement('option');
        customOption.value = 'custom';
        customOption.textContent = '自定义…';
        select.appendChild(customOption);
        select.value = dimensionData.selected_option || '';

        const customInput = document.createElement('input');
        customInput.type = 'text';
        customInput.id = `dimension-${dimensionKey}-custom`;
        customInput.className = 'dimension-custom-input form-control';
        customInput.placeholder = '自定义描述';
        customInput.value = dimensionData.custom_input || '';
        customInput.disabled = !globalEnabled || !isEnabled || select.value !== 'custom';

        const patchDim = async (dimPatch) => {
            await this.updateConfig({
                dimensional_creative: {
                    ...this.config.dimensional_creative,
                    ...dimPatch
                }
            });
            const btn = document.getElementById('save-creative-config');
            if (btn && !btn.classList.contains('has-changes')) {
                btn.classList.add('has-changes');
                btn.innerHTML = '保存设置 <span style="color: var(--warning-color);">(有未保存更改)</span>';
            }
        };

        checkbox.addEventListener('change', async (e) => {
            await patchDim({
                enabled_dimensions: {
                    ...this.config.dimensional_creative.enabled_dimensions,
                    [dimensionKey]: e.target.checked
                }
            });
            this.updateCreativeControlsState();
        });

        select.addEventListener('change', async (e) => {
            const selectedValue = e.target.value;
            if (selectedValue !== 'custom') customInput.value = '';
            customInput.disabled = !globalEnabled || !checkbox.checked || selectedValue !== 'custom';
            await patchDim({
                dimension_options: {
                    ...this.config.dimensional_creative.dimension_options,
                    [dimensionKey]: {
                        ...this.config.dimensional_creative.dimension_options[dimensionKey],
                        selected_option: selectedValue,
                        custom_input: selectedValue === 'custom' ? customInput.value : ''
                    }
                }
            });
        });

        let originalValue = customInput.value;
        customInput.addEventListener('blur', async (e) => {
            if (e.target.value === originalValue) return;
            originalValue = e.target.value;
            await patchDim({
                dimension_options: {
                    ...this.config.dimensional_creative.dimension_options,
                    [dimensionKey]: {
                        ...this.config.dimensional_creative.dimension_options[dimensionKey],
                        custom_input: e.target.value,
                        selected_option: 'custom'
                    }
                }
            });
        });

        fields.appendChild(select);
        fields.appendChild(customInput);
        row.appendChild(top);
        row.appendChild(fields);
        return row;
    }

    // 更新维度选项  
    async updateDimensionOption(dimensionKey, selectedOption, customInput) {
        await this.updateConfig({
            dimensional_creative: {
                ...this.config.dimensional_creative,
                dimension_options: {
                    ...this.config.dimensional_creative.dimension_options,
                    [dimensionKey]: {
                        ...this.config.dimensional_creative.dimension_options[dimensionKey],
                        selected_option: selectedOption,
                        custom_input: customInput
                    }
                }
            }
        });
    }

    populateImageDesignUI() {
        if (!this.config.image_design) return;

        const imageMargin = document.getElementById('image-margin');
        if (imageMargin) imageMargin.value = this.config.image_design.margin || 20;

        const borderRadius = document.getElementById('image-border-radius');
        if (borderRadius) borderRadius.value = this.config.image_design.border_radius || 8;

        const maxWidth = document.getElementById('image-max-width');
        if (maxWidth) maxWidth.value = this.config.image_design.max_width || 100;

        const autoTheme = document.getElementById('auto-theme-adapt');
        if (autoTheme) autoTheme.checked = this.config.image_design.auto_theme_adapt !== false;
    }

    // 保存配置  
    async saveImageDesignConfig() {
        const imageDesignConfig = {
            margin: parseInt(document.getElementById('image-margin')?.value || 20),
            border_radius: parseInt(document.getElementById('image-border-radius')?.value || 8),
            max_width: parseInt(document.getElementById('image-max-width')?.value || 100),
            auto_theme_adapt: document.getElementById('auto-theme-adapt')?.checked || false,
            light_bg_color: document.getElementById('light-bg-color')?.value || '#ffffff',
            dark_bg_color: document.getElementById('dark-bg-color')?.value || '#1a1a1a'
        };

        await this.updateConfig({ image_design: imageDesignConfig });
        const success = await this.saveConfig();

        if (success) {
            const saveBtn = document.getElementById('save-image-design-config');
            if (saveBtn) {
                saveBtn.classList.remove('has-changes');
                saveBtn.innerHTML = '保存设置';
            }
        }

        window.app?.showNotification(
            success ? '页面设计已保存' : '保存配置失败',
            success ? 'success' : 'error'
        );
    }

    updateSliderValue(slider) {
        const value = slider.value;
        const valueDisplay = slider.parentElement.querySelector('.slider-value');
        if (valueDisplay) {
            valueDisplay.textContent = value;
        }
    }

    // 更新配置(仅内存,不保存文件)  
    async updateConfig(updates) {
        try {
            const response = await fetch(this.apiEndpoint, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config_data: updates })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // 同步更新前端内存        
            this.deepMerge(this.config, updates);

            const panelButtonMap = {
                'general': 'save-general-config',
                'ui': 'save-general-config',
                'base': 'save-general-config',
                'platforms': 'save-platforms-config',
                'wechat': 'save-wechat-config',
                'api': 'save-api-config',
                'img-api': 'save-img-api-config',
                'aiforge': 'save-aiforge-config',
                'creative': 'save-creative-config',
                'image-design': 'save-image-design-config'
            };

            const saveBtnId = panelButtonMap[this.currentPanel];
            if (saveBtnId) {
                const saveBtn = document.getElementById(saveBtnId);
                if (saveBtn && !saveBtn.classList.contains('has-changes')) {
                    saveBtn.classList.add('has-changes');
                    saveBtn.innerHTML = `保存设置 <span style="color: var(--warning-color);">(有未保存更改)</span>`;
                }
            }

            return true;
        } catch (error) {
            return false;
        }
    }

    // 保存配置到文件  
    async saveConfig() {
        try {
            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const result = await response.json();
            return result.status === 'success';
        } catch (error) {
            return false;
        }
    }

    // 恢复默认配置(仅更新内存,不保存)  
    async resetToDefault() {
        try {
            const response = await fetch(`${this.apiEndpoint}/default`);
            if (!response.ok) {
                throw new Error('获取默认配置失败');
            }

            const result = await response.json();

            // 更新后端内存  
            await this.updateConfig(result.data);

            // 更新前端内存  
            this.config = result.data;

            // 刷新UI  
            this.populateUI();

            return true;
        } catch (error) {
            return false;
        }
    }

    // 深度合并辅助方法  
    deepMerge(target, source) {
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                if (!target[key]) target[key] = {};
                this.deepMerge(target[key], source[key]);
            } else {
                target[key] = source[key];
            }
        }
    }

    // 获取当前配置    
    getConfig() {
        return this.config;
    }

    // 更新特定配置项(仅内存)  
    async updateConfigItem(key, value) {
        const updateData = {};
        updateData[key] = value;

        try {
            await this.updateConfig(updateData);
            return true;
        } catch (error) {
            return false;
        }
    }
}

// 全局配置管理器实例    
let configManager;

// 添加test-result样式
const testResultStyle = document.createElement('style');
testResultStyle.textContent = `
    .test-result {
        padding: 10px 14px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
    }
    .test-result.success {
        background: #f6ffed;
        border: 1px solid #b7eb8f;
        color: #52c41a;
    }
    .test-result.error {
        background: #fff2f0;
        border: 1px solid #ffccc7;
        color: #ff4d4f;
    }
    .test-status {
        padding: 10px;
        border-radius: 6px;
        font-size: 13px;
        display: flex;
        align-items: center;
    }
    .test-status.info {
        background: #e6f7ff;
        border: 1px solid #91d5ff;
        color: #1890ff;
    }
    .test-status.success {
        background: #f6ffed;
        border: 1px solid #b7eb8f;
        color: #52c41a;
    }
    .test-status.error {
        background: #fff2f0;
        border: 1px solid #ffccc7;
        color: #ff4d4f;
    }
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    .spinner, .spinning svg {
        animation: spin 1s linear infinite;
    }
    .spinner {
        display: inline-block;
        width: 14px;
        height: 14px;
        border: 2px solid currentColor;
        border-right-color: transparent;
        border-radius: 50%;
        margin-right: 8px;
    }
    .model-label-with-refresh {
        display: flex;
        justify-content: space-between;
        align-items: center;
        width: 100%;
    }
    .model-refresh-btn-inline {
        background: none;
        border: none;
        padding: 2px 4px;
        color: var(--primary-color);
        cursor: pointer;
        display: flex;
        align-items: center;
        opacity: 0.7;
        transition: all 0.2s;
        border-radius: 4px;
    }
    .model-refresh-btn-inline:hover {
        opacity: 1;
        background: rgba(var(--primary-rgb), 0.1);
    }
    .model-refresh-btn-inline.spinning {
        pointer-events: none;
        color: var(--text-secondary);
    }
`;
document.head.appendChild(testResultStyle);

// 初始化配置管理器    
document.addEventListener('DOMContentLoaded', async () => {
    configManager = new AIWriteXConfigManager();
    window.configManager = configManager;
});
