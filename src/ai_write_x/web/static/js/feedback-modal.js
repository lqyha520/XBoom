/**
 * 问题反馈功能
 */

let screenshotFiles = [];

// 打开反馈 Modal
function openFeedbackModal() {
    document.getElementById('feedbackModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

// 关闭反馈 Modal
function closeFeedbackModal() {
    document.getElementById('feedbackModal').style.display = 'none';
    document.body.style.overflow = '';
    document.getElementById('feedbackForm').reset();
    screenshotFiles = [];
    document.getElementById('screenshotPreview').innerHTML = '';
    document.getElementById('charCount').textContent = '0';
}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    // 字数统计
    const descriptionInput = document.getElementById('feedbackDescription');
    descriptionInput.addEventListener('input', function() {
        document.getElementById('charCount').textContent = this.value.length;
    });

    // 反馈类型切换（Bug时显示复现步骤）
    document.querySelectorAll('input[name="feedbackType"]').forEach(radio => {
        radio.addEventListener('change', function() {
            const reproduceGroup = document.getElementById('reproduceStepsGroup');
            reproduceGroup.style.display = this.value === 'bug' ? 'block' : 'none';
        });
    });

    // 截图上传
    const uploadArea = document.getElementById('screenshotUpload');
    const fileInput = document.getElementById('screenshotInput');
    
    uploadArea.addEventListener('click', (e) => {
        if (!e.target.closest('.screenshot-remove')) {
            fileInput.click();
        }
    });

    // 拖拽上传
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '#3b82f6';
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.style.borderColor = '#d1d5db';
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '#d1d5db';
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    // 表单提交
    document.getElementById('feedbackForm').addEventListener('submit', handleSubmit);

    // 点击遮罩关闭
    document.querySelector('.feedback-overlay').addEventListener('click', closeFeedbackModal);
});

// 处理上传的文件
function handleFiles(files) {
    const maxFiles = 3;
    const remainingSlots = maxFiles - screenshotFiles.length;
    
    if (remainingSlots <= 0) {
        showToast('最多只能上传3张截图', 'warning');
        return;
    }

    const filesToAdd = Array.from(files).slice(0, remainingSlots);
    
    filesToAdd.forEach(file => {
        if (!file.type.startsWith('image/')) {
            showToast('只能上传图片文件', 'error');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showToast('图片大小不能超过5MB', 'error');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            screenshotFiles.push({
                name: file.name,
                data: e.target.result
            });
            renderScreenshots();
        };
        reader.readAsDataURL(file);
    });
}

// 渲染截图预览
function renderScreenshots() {
    const preview = document.getElementById('screenshotPreview');
    preview.innerHTML = screenshotFiles.map((file, index) => `
        <div class="screenshot-item">
            <img src="${file.data}" alt="${file.name}">
            <button type="button" class="screenshot-remove" onclick="removeScreenshot(${index})">×</button>
        </div>
    `).join('');
}

// 移除截图
function removeScreenshot(index) {
    screenshotFiles.splice(index, 1);
    renderScreenshots();
}

// 提交反馈
async function handleSubmit(e) {
    e.preventDefault();

    const submitBtn = document.getElementById('submitFeedbackBtn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');

    // 禁用按钮
    submitBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline-flex';

    try {
        const formData = {
            type: document.querySelector('input[name="feedbackType"]:checked').value,
            description: document.getElementById('feedbackDescription').value.trim(),
            reproduce_steps: document.getElementById('reproduceSteps').value.trim() || null,
            contact: document.getElementById('feedbackContact').value.trim() || null,
            screenshots: screenshotFiles.map(f => f.data.split(',')[1]) // 只发送 base64 部分
        };

        const response = await fetch('/api/feedback/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const result = await response.json();

        if (result.success) {
            showToast(result.message, 'success');
            closeFeedbackModal();
        } else {
            showToast(result.message || '提交失败，请稍后重试', 'error');
        }
    } catch (error) {
        console.error('提交反馈失败:', error);
        showToast('网络错误，请检查连接后重试', 'error');
    } finally {
        // 恢复按钮状态
        submitBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

// Toast 提示（复用现有的或简单实现）
function showToast(message, type = 'info') {
    // 如果系统已有 toast 函数，直接用
    if (typeof window.showNotification === 'function') {
        window.showNotification(message, type);
        return;
    }

    // 简单实现
    const toast = document.createElement('div');
    toast.className = `feedback-toast feedback-toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#f59e0b'};
        color: white;
        border-radius: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideInRight 0.3s ease-out;
    `;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
