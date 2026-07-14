/**    
 * 悬浮预览面板管理器    
 */
class PreviewPanelManager {
    constructor() {
        this.overlay = null;
        this.panel = null;
        this.isVisible = false;
        this.currentSize = 'tablet';
        this.isSourceView = false;
        this.currentHtml = '';
        this.sizePresets = {
            mobile: { width: 390, label: '390px · 手机' },
            tablet: { width: 768, label: '768px · 平板' },
            desktop: { width: 1024, label: '宽屏 · 桌面' }
        };

        this.currentArticleInfo = null;
        this.showActions = false;

        this.init();
    }

    init() {
        this.overlay = document.getElementById('preview-overlay');
        this.panel = this.overlay?.querySelector('.preview-panel');

        if (!this.overlay || !this.panel) {
            return;
        }

        this.bindEvents();
        this.bindActionEvents();  // 绑定编辑/设计/发布按钮  
        this.initTriggerButton();
    }

    bindEvents() {
        // 关闭按钮    
        const closeBtn = document.getElementById('preview-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }

        // 尺寸切换按钮    
        const toggleSizeBtn = document.getElementById('preview-toggle-size');
        if (toggleSizeBtn) {
            toggleSizeBtn.addEventListener('click', () => this.toggleSize());
        }

        // 点击遮罩关闭    
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.hide();
            }
        });

        // ESC 键关闭    
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isVisible) {
                this.hide();
            }
        });

        // 源码切换按钮
        const toggleSourceBtn = document.getElementById('preview-toggle-source');
        if (toggleSourceBtn) {
            toggleSourceBtn.addEventListener('click', () => this.toggleSourceView());
        }

        // 源码复制按钮
        const copyHtmlBtn = document.getElementById('preview-copy-html');
        if (copyHtmlBtn) {
            copyHtmlBtn.addEventListener('click', () => this.copyHtml());
        }
    }

    bindActionEvents() {
        // 编辑按钮  
        const editBtn = document.getElementById('preview-edit-btn');
        if (editBtn) {
            editBtn.addEventListener('click', async () => {
                if (!this.currentArticleInfo) {
                    window.app?.showNotification('无法获取文章信息', 'error');
                    return;
                }

                try {
                    if (!window.contentEditorDialog) {
                        window.contentEditorDialog = new ContentEditorDialog();
                    }

                    // this.hide();  
                    await window.contentEditorDialog.open(
                        this.currentArticleInfo.path,
                        this.currentArticleInfo.title,
                        'article'
                    );
                } catch (error) {
                    window.app?.showNotification('打开编辑器失败: ' + error.message, 'error');
                }
            });
        }

        // 设计按钮  
        const designBtn = document.getElementById('preview-design-btn');
        if (designBtn) {
            designBtn.addEventListener('click', async () => {
                if (!this.currentArticleInfo) {
                    window.app?.showNotification('无法获取文章信息', 'error');
                    return;
                }

                try {
                    if (!window.imageDesignerDialog) {
                        window.imageDesignerDialog = new ImageDesignerDialog();
                    }

                    // this.hide();  
                    await window.imageDesignerDialog.open(this.currentArticleInfo.path);
                } catch (error) {
                    window.app?.showNotification('打开设计器失败: ' + error.message, 'error');
                }
            });
        }

        const regenerateImageBtn = document.getElementById('preview-regenerate-image-btn');
        if (regenerateImageBtn) {
            regenerateImageBtn.addEventListener('click', () => this.openSingleImageRegenerator());
        }

        // 对比原稿按钮
        const compareBtn = document.getElementById('preview-compare-btn');
        if (compareBtn) {
            compareBtn.addEventListener('click', () => {
                if (!this.currentArticleInfo) {
                    window.app?.showNotification('无法获取文章信息', 'error');
                    return;
                }
                if (typeof window.openArticleComparison === 'function') {
                    window.openArticleComparison(this.currentArticleInfo);
                } else {
                    window.app?.showNotification('对比功能尚未完全加载', 'error');
                }
            });
        }

        // 发布按钮
        const publishBtn = document.getElementById('preview-publish-btn');
        if (publishBtn) {
            publishBtn.addEventListener('click', async () => {
                if (!this.currentArticleInfo) {
                    window.app?.showNotification('无法获取文章信息', 'error');
                    return;
                }

                try {
                    //  如果 ArticleManager 未初始化,先初始化它  
                    if (!window.articleManager) {
                        window.articleManager = new ArticleManager();
                    }

                    // 检查 showPublishDialog 方法是否存在  
                    if (typeof window.articleManager.showPublishDialog !== 'function') {
                        window.app?.showNotification('发布功能不可用', 'error');
                        return;
                    }

                    // 关闭预览面板  
                    // this.hide();  

                    // 打开发布对话框  
                    await window.articleManager.showPublishDialog(this.currentArticleInfo.path);
                } catch (error) {
                    window.app?.showNotification('打开发布对话框失败: ' + error.message, 'error');
                }
            });
        }
    }

    openSingleImageRegenerator() {
        if (!this.currentArticleInfo?.path) {
            window.app?.showNotification('无法获取文章路径', 'error');
            return;
        }

        const parsed = new DOMParser().parseFromString(this.currentHtml || '', 'text/html');
        const images = Array.from(parsed.querySelectorAll('img')).map((img, index) => ({
            index,
            src: img.getAttribute('src') || '',
            prompt: img.getAttribute('data-img-prompt') || img.getAttribute('alt') || '',
            ratio: img.getAttribute('data-aspect-ratio') || (img.getAttribute('data-cover') === '1' ? '2.35:1' : '16:9'),
            cover: img.getAttribute('data-cover') === '1'
        })).filter(item => item.src);

        if (!images.length) {
            window.app?.showNotification('这篇文章里没有可重新生成的图片', 'warning');
            return;
        }

        document.getElementById('single-image-regenerator')?.remove();
        const overlay = document.createElement('div');
        overlay.id = 'single-image-regenerator';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:10050;background:rgba(15,23,42,.62);display:flex;align-items:center;justify-content:center;padding:24px;';
        overlay.innerHTML = `
            <div style="width:min(720px,96vw);max-height:92vh;overflow:auto;background:var(--bg-primary,#fff);color:var(--text-primary,#18212f);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.28);padding:22px;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px;">
                    <div><div style="font-size:18px;font-weight:700;">单张换图</div><div style="font-size:12px;color:var(--text-secondary,#64748b);margin-top:4px;">只替换选中的图片，文章其他内容不会改变</div></div>
                    <button type="button" data-action="close" style="border:0;background:transparent;font-size:24px;cursor:pointer;color:inherit;">×</button>
                </div>
                <label style="display:block;font-size:13px;margin-bottom:6px;">选择图片</label>
                <select data-field="image" style="width:100%;padding:10px 12px;border:1px solid var(--border-color,#d7dee8);border-radius:9px;background:var(--bg-secondary,#fff);color:inherit;"></select>
                <div style="margin:14px 0;background:#0f172a;border-radius:12px;min-height:180px;display:flex;align-items:center;justify-content:center;overflow:hidden;">
                    <img data-field="preview" alt="当前图片" style="max-width:100%;max-height:320px;object-fit:contain;">
                </div>
                <div style="display:grid;grid-template-columns:1fr 140px;gap:12px;">
                    <div>
                        <label style="display:block;font-size:13px;margin-bottom:6px;">图片提示词</label>
                        <textarea data-field="prompt" rows="6" style="box-sizing:border-box;width:100%;padding:10px 12px;border:1px solid var(--border-color,#d7dee8);border-radius:9px;resize:vertical;background:var(--bg-secondary,#fff);color:inherit;" placeholder="可直接修改；清空后将按文章内容和所选风格自动构建"></textarea>
                    </div>
                    <div>
                        <label style="display:block;font-size:13px;margin-bottom:6px;">图片风格</label>
                        <select data-field="style" style="width:100%;padding:10px 8px;border:1px solid var(--border-color,#d7dee8);border-radius:9px;background:var(--bg-secondary,#fff);color:inherit;">
                            <option value="auto">智能匹配</option><option value="premium_editorial">高级杂志摄影</option>
                            <option value="documentary">真实纪实摄影</option><option value="cinematic">电影叙事</option>
                            <option value="soft_illustration">温暖质感插画</option><option value="minimal_3d">极简高级 3D</option>
                            <option value="oriental">东方美学</option>
                        </select>
                        <button type="button" data-action="auto-prompt" style="width:100%;margin-top:10px;padding:9px;border:1px solid var(--border-color,#d7dee8);border-radius:9px;background:transparent;color:inherit;cursor:pointer;">按风格重构提示词</button>
                    </div>
                </div>
                <div data-field="status" style="min-height:20px;margin-top:12px;font-size:13px;color:var(--text-secondary,#64748b);"></div>
                <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:14px;">
                    <button type="button" data-action="cancel" style="padding:10px 18px;border:1px solid var(--border-color,#d7dee8);border-radius:9px;background:transparent;color:inherit;cursor:pointer;">取消</button>
                    <button type="button" data-action="generate" style="padding:10px 18px;border:0;border-radius:9px;background:#2563eb;color:#fff;cursor:pointer;font-weight:600;">重新生成并替换</button>
                </div>
            </div>`;

        const imageSelect = overlay.querySelector('[data-field="image"]');
        const preview = overlay.querySelector('[data-field="preview"]');
        const promptInput = overlay.querySelector('[data-field="prompt"]');
        const styleSelect = overlay.querySelector('[data-field="style"]');
        const status = overlay.querySelector('[data-field="status"]');
        const generateBtn = overlay.querySelector('[data-action="generate"]');
        images.forEach((item, position) => {
            const option = document.createElement('option');
            option.value = String(position);
            option.textContent = item.cover ? `封面图 · ${item.ratio}` : `正文图 ${position + 1} · ${item.ratio}`;
            imageSelect.appendChild(option);
        });
        const updateSelection = () => {
            const item = images[Number(imageSelect.value) || 0];
            preview.src = item.src;
            promptInput.value = item.prompt;
            status.textContent = '修改提示词可精确控制画面；点击“按风格重构提示词”则由系统重新构建。';
        };
        imageSelect.addEventListener('change', updateSelection);
        overlay.querySelector('[data-action="auto-prompt"]').addEventListener('click', () => {
            promptInput.value = '';
            promptInput.placeholder = `将根据文章内容自动构建“${styleSelect.options[styleSelect.selectedIndex].text}”提示词`;
            status.textContent = '已切换为自动构建提示词。';
        });
        const close = () => overlay.remove();
        overlay.querySelector('[data-action="close"]').addEventListener('click', close);
        overlay.querySelector('[data-action="cancel"]').addEventListener('click', close);
        overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
        generateBtn.addEventListener('click', async () => {
            const item = images[Number(imageSelect.value) || 0];
            generateBtn.disabled = true;
            generateBtn.textContent = '正在生成…';
            const started = Date.now();
            const timer = setInterval(() => {
                status.textContent = `正在重新生成，已耗时 ${Math.floor((Date.now() - started) / 1000)} 秒…`;
            }, 1000);
            try {
                const response = await fetch('/api/articles/regenerate-image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: this.currentArticleInfo.path,
                        image_src: item.src,
                        image_index: item.index,
                        prompt: promptInput.value.trim(),
                        image_style: styleSelect.value
                    })
                });
                const result = await response.json();
                if (!response.ok || result.status !== 'success') {
                    throw new Error(result.detail || result.message || `HTTP ${response.status}`);
                }
                const contentResponse = await fetch(`/api/articles/content?path=${encodeURIComponent(this.currentArticleInfo.path)}`);
                if (!contentResponse.ok) throw new Error('图片已替换，但刷新预览失败');
                const refreshedHtml = await contentResponse.text();
                this.setContent(refreshedHtml);
                status.textContent = `替换完成，耗时 ${result.data.elapsed_seconds} 秒。`;
                window.app?.showNotification('图片已重新生成并原位替换', 'success');
                setTimeout(close, 900);
            } catch (error) {
                status.textContent = `生成失败：${error.message}`;
                window.app?.showNotification('单张换图失败: ' + error.message, 'error');
                generateBtn.disabled = false;
                generateBtn.textContent = '重新生成并替换';
            } finally {
                clearInterval(timer);
            }
        });
        updateSelection();
        document.body.appendChild(overlay);
    }

    show(content = null) {
        if (!this.overlay) return;

        if (content) {
            this.setContent(content);
        }

        this.setSize('tablet');

        this.overlay.classList.remove('active');
        this.overlay.style.display = 'flex';

        // 使用双重 requestAnimationFrame 确保浏览器完成布局计算    
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                this.overlay.classList.add('active');
            });
        });

        this.isVisible = true;
        document.body.style.overflow = 'hidden';
        this.updateTriggerState();
    }

    hide() {
        if (!this.overlay) return;

        this.overlay.classList.remove('active');

        setTimeout(() => {
            this.overlay.style.display = 'none';
            document.body.style.overflow = '';
        }, 300);

        this.isVisible = false;

        // 隐藏时重置为预览模式
        if (this.isSourceView) {
            this.toggleSourceView(false);
        }

        this.updateTriggerState();
    }


    toggle(content = null) {
        if (this.isVisible) {
            this.hide();
        } else {
            this.show(content);
        }
    }

    initTriggerButton() {
        const triggerBtn = document.getElementById('preview-trigger');
        if (!triggerBtn) {
            return;
        }

        triggerBtn.addEventListener('click', () => {
            this.toggle();
        });
    }

    updateTriggerState() {
        const triggerBtn = document.getElementById('preview-trigger');
        if (!triggerBtn) return;

        const tooltip = triggerBtn.querySelector('.trigger-tooltip');
        if (this.isVisible) {
            triggerBtn.classList.add('active');
            if (tooltip) tooltip.textContent = '关闭预览';
        } else {
            triggerBtn.classList.remove('active');
            if (tooltip) tooltip.textContent = '预览面板';
        }
    }

    setContent(content) {
        const previewArea = document.getElementById('preview-area');
        const sourceArea = document.getElementById('preview-source-code');
        if (!previewArea) return;

        // 保存原始内容供源码查看
        this.currentHtml = typeof content === 'string' ? content : (content.innerHTML || '');
        if (sourceArea) {
            sourceArea.value = this.currentHtml;
        }

        // 清空现有内容    
        previewArea.innerHTML = '';

        if (typeof content === 'string') {
            // 检测是否是HTML内容    
            const isHtml = content.trim().startsWith('<');

            if (isHtml) {
                // 检测是否已经包含完整的文档结构和样式    
                const hasDoctype = content.trim().toLowerCase().startsWith('<!doctype');
                const hasHtmlTag = content.trim().toLowerCase().startsWith('<html');
                const hasScrollbarStyles = content.includes('::-webkit-scrollbar') ||
                    content.includes('scrollbar-width');

                let finalContent = content;

                // 如果是完整文档但缺少滚动条样式,需要注入样式    
                if ((hasDoctype || hasHtmlTag) && !hasScrollbarStyles) {
                    // 获取CSS变量值    
                    const computedStyle = getComputedStyle(document.documentElement);
                    const bgColor = computedStyle.getPropertyValue('--background-color').trim();
                    const borderColor = computedStyle.getPropertyValue('--border-color').trim();
                    const secondaryColor = computedStyle.getPropertyValue('--secondary-color').trim();

                    // 注入与全局CSS相同的滚动条样式    
                    const styleTag = `    
                        <style>    
                            /* 使用与全局CSS相同的滚动条样式 */    
                            ::-webkit-scrollbar {    
                                width: 6px;    
                                height: 6px;    
                            }    
                              
                            ::-webkit-scrollbar-track {    
                                background: ${bgColor};    
                            }    
                              
                            ::-webkit-scrollbar-thumb {    
                                background: ${borderColor};    
                                border-radius: 3px;    
                            }    
                              
                            ::-webkit-scrollbar-thumb:hover {    
                                background: ${secondaryColor};    
                            }    
                        </style>    
                    `;

                    // 在 </head> 之前插入样式    
                    if (content.includes('</head>')) {
                        finalContent = content.replace('</head>', `${styleTag}</head>`);
                    } else if (content.includes('<head>')) {
                        finalContent = content.replace('<head>', `<head>${styleTag}`);
                    } else {
                        // 如果没有 <head> 标签,在 <html> 后添加    
                        finalContent = content.replace(/<html[^>]*>/i, (match) => `${match}<head>${styleTag}</head>`);
                    }
                } else if (!hasDoctype && !hasHtmlTag) {
                    // HTML片段,包装成完整文档    
                    const computedStyle = getComputedStyle(document.documentElement);
                    const bgColor = computedStyle.getPropertyValue('--background-color').trim();
                    const borderColor = computedStyle.getPropertyValue('--border-color').trim();
                    const secondaryColor = computedStyle.getPropertyValue('--secondary-color').trim();
                    const textColor = computedStyle.getPropertyValue('--text-primary').trim();

                    finalContent = `    
    <!DOCTYPE html>    
    <html>    
    <head>    
        <meta charset="UTF-8">    
        <style>    
            body {    
                margin: 0;    
                padding: 16px;    
                overflow: auto;    
                color: ${textColor};    
                background: ${bgColor};    
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;    
            }    
              
            /* 使用与全局CSS相同的滚动条样式 */    
            ::-webkit-scrollbar {    
                width: 6px;    
                height: 6px;    
            }    
              
            ::-webkit-scrollbar-track {    
                background: ${bgColor};    
            }    
              
            ::-webkit-scrollbar-thumb {    
                background: ${borderColor};    
                border-radius: 3px;    
            }    
              
            ::-webkit-scrollbar-thumb:hover {    
                background: ${secondaryColor};    
            }    
        </style>    
    </head>    
    <body>    
        ${content}    
    </body>    
    </html>    
                    `;
                }

                // 使用 iframe 渲染    
                const iframe = document.createElement('iframe');
                iframe.style.cssText = `    
                    width: 100%;    
                    height: 100%;    
                    min-height: 100%;    
                    border: none;    
                    display: block;    
                    position: absolute;    
                    top: 0;    
                    left: 0;    
                    right: 0;    
                    bottom: 0;    
                `;
                iframe.sandbox = 'allow-same-origin allow-scripts';
                iframe.srcdoc = finalContent;

                // 确保 preview-area 有正确的定位上下文    
                previewArea.style.position = 'relative';
                previewArea.style.height = '100%';

                previewArea.appendChild(iframe);
            } else {
                // 纯文本内容直接插入    
                previewArea.innerHTML = content;
            }
        } else {
            previewArea.appendChild(content);
        }
    }

    /**
     * 切换源码视图
     */
    toggleSourceView(force = null) {
        const previewArea = document.getElementById('preview-area');
        const sourceContainer = document.getElementById('preview-source-area');
        const toggleBtn = document.getElementById('preview-toggle-source');

        this.isSourceView = force !== null ? force : !this.isSourceView;

        if (this.isSourceView) {
            if (previewArea) previewArea.style.display = 'none';
            if (sourceContainer) sourceContainer.style.display = 'block';
            if (toggleBtn) {
                toggleBtn.classList.add('active');
                toggleBtn.title = '切回预览';
            }
        } else {
            if (previewArea) previewArea.style.display = 'block';
            if (sourceContainer) sourceContainer.style.display = 'none';
            if (toggleBtn) {
                toggleBtn.classList.remove('active');
                toggleBtn.title = '显示源码';
            }
        }
    }

    /**
     * 复制 HTML 到剪贴板
     */
    async copyHtml() {
        if (!this.currentHtml) {
            window.app?.showNotification('没有可复制的内容', 'warning');
            return;
        }

        try {
            await navigator.clipboard.writeText(this.currentHtml);
            window.app?.showNotification('HTML 已成功拷贝到剪贴板', 'success');
        } catch (err) {
            console.error('拷贝失败:', err);
            // 降级使用 textarea 选中的方式
            const sourceCode = document.getElementById('preview-source-code');
            if (sourceCode) {
                sourceCode.select();
                document.execCommand('copy');
                window.app?.showNotification('HTML 已成功拷贝到剪贴板', 'success');
            } else {
                window.app?.showNotification('拷贝失败，请手动选择复制', 'error');
            }
        }
    }

    toggleSize() {
        const sizes = Object.keys(this.sizePresets);
        const currentIndex = sizes.indexOf(this.currentSize);
        const nextIndex = (currentIndex + 1) % sizes.length;
        const nextSize = sizes[nextIndex];

        this.setSize(nextSize);
    }

    setSize(size) {
        if (!this.sizePresets[size] || !this.panel) return;

        this.currentSize = size;
        const preset = this.sizePresets[size];

        // 移除所有尺寸类      
        this.panel.classList.remove('tablet-size', 'desktop-size');

        // 添加对应尺寸类      
        if (size === 'tablet') {
            this.panel.classList.add('tablet-size');
        } else if (size === 'desktop') {
            this.panel.classList.add('desktop-size');
        }

        // 更新尺寸信息显示      
        const sizeInfo = this.overlay.querySelector('.preview-size-info');
        if (sizeInfo) {
            sizeInfo.textContent = preset.label;
        }
    }

    async previewArticle(article) {
        try {
            const response = await fetch(`/api/articles/content?path=${encodeURIComponent(article.path)}`);
            if (response.ok) {
                const html = await response.text();
                if (window.previewPanelManager) {
                    window.previewPanelManager.show(html);
                } else {
                    window.app?.showNotification('预览面板未初始化', 'error');
                }
            } else {
                window.app?.showNotification(`加载失败 (HTTP ${response.status})`, 'error');
            }
        } catch (error) {
            window.app?.showNotification('预览失败: ' + error.message, 'error');
        }
    }

    // 预览生成的内容      
    previewGenerated(content) {
        this.show(content);
    }

    // 内容生成专用:显示预览并启用操作按钮  
    showWithActions(content, articleInfo) {
        this.currentArticleInfo = articleInfo;
        this.showActions = true;

        const actionsDiv = document.getElementById('preview-actions');
        if (actionsDiv) {
            actionsDiv.style.display = 'flex';
        }

        this.show(content);
    }

    reset() {
        // 清空预览内容,恢复初始占位符  
        const previewArea = document.getElementById('preview-area');
        if (previewArea) {
            previewArea.innerHTML = '<p class="preview-placeholder">内容预览将在这里显示</p>';
        }

        // 重置尺寸为默认(平板模式)
        this.setSize('tablet');

        // 清空文章信息  
        this.currentArticleInfo = null;
        this.showActions = false;

        // 隐藏操作按钮组(如果存在)  
        const actionsDiv = document.getElementById('preview-actions');
        if (actionsDiv) {
            actionsDiv.style.display = 'none';
        }

        // 关闭面板  
        this.hide();
    }
}

// 全局预览面板管理器实例      
let previewPanelManager;

// 初始化预览面板管理器      
document.addEventListener('DOMContentLoaded', () => {
    previewPanelManager = new PreviewPanelManager();
    window.previewPanelManager = previewPanelManager;
});

// 导出给其他模块使用      
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PreviewPanelManager;
}
