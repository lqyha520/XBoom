# Agnes AI 注册到创建 API Key 教程

> 这份教程写给第一次使用 Agnes AI 的新手。目标很简单：注册账号，进入 API 平台，创建并复制自己的 API Key。

---

## 1. Agnes AI 是什么

Agnes AI 是 Sapiens AI 推出的 AI 平台，提供文本、图片、视频等多模态模型能力。

如果你只是聊天、使用网页应用，可以去普通 Agnes 应用入口；如果你要把 Agnes AI 接入软件、工具或代码里，就需要进入 **API 平台** 创建 API Key。

本文讲的是：

```text
注册 Agnes AI API 平台账号 -> 创建 API Key -> 保存 Key -> 后续接入软件使用
```

---

## 2. 准备工作

开始前准备好：

- 一个常用邮箱。
- 可以接收验证码或验证邮件。
- 一个安全的地方保存 Key，比如本地记事本、密码管理器，或软件自己的密钥配置页。

注意：API Key 相当于你的接口密码，不要发给别人，也不要截图公开。

---

## 3. 打开 Agnes AI API 平台

浏览器打开：

```text
https://platform.agnes-ai.com/
```

如果打不开，可以先访问 Agnes AI 官网或文档页，再从页面里的 API / Platform / Console 入口进入。

---

## 4. 注册账号

1. 打开 `https://platform.agnes-ai.com/`。
2. 点击 **Sign up**、**Register**、**注册** 或类似按钮。
3. 输入邮箱。
4. 设置密码。
5. 如果页面要求验证码，就输入邮箱收到的验证码。
6. 如果收到验证邮件，打开邮箱，点击邮件里的验证链接。
7. 验证完成后回到平台登录。

不同时间页面按钮名称可能略有变化，但流程通常是：

```text
邮箱注册 -> 邮箱验证 -> 登录平台
```

---

## 5. 登录 Agnes AI API 平台

1. 回到 `https://platform.agnes-ai.com/`。
2. 点击 **Log in**、**Sign in**、**登录**。
3. 输入刚才注册的邮箱和密码。
4. 登录成功后，会进入控制台或 API 管理页面。

如果登录后进入的是普通应用界面，不是 API 控制台，注意寻找：

- API
- API Hub
- API Management
- API Keys
- Settings
- Developer

创建 Key 的入口一般在这些区域里。

---

## 6. 找到 API Key 页面

登录后，在左侧菜单或设置页面中找到类似入口：

```text
API 密钥
API Keys
Settings -> API Keys
Access Token
Token
```

常见路径可能是：

```text
左侧菜单 -> API 密钥 -> 创建新的密钥
```

也可能是：

```text
Settings -> API Keys -> Create API Key
```

以你当前页面显示为准。

---

## 7. 创建新的 API Key

进入 API Key 页面后：

1. 点击 **创建新的密钥**、**Create API Key** 或类似按钮。
2. 如果要求填写名称，可以随便起一个容易识别的名字。

   例如：

   ```text
   xboom
   xboom-test
   my-first-key
   ```

3. 点击确认创建。
4. 页面会生成一串 Key。
5. 立即复制并保存。

重要提醒：很多平台的 Key 只完整显示一次。关闭弹窗后，可能就看不到完整 Key 了。

---

## 8. 保存 API Key

建议保存到安全位置：

- 密码管理器。
- 本机私密记事本。
- 软件自己的密钥配置页面。

不要这样保存：

- 发到微信群。
- 放进公开文档。
- 截图发给别人。
- 写进会上传到 GitHub/Gitee 的代码文件。

如果怀疑 Key 泄露，请回 Agnes AI 平台删除旧 Key，再重新创建一个。

---

## 9. 创建成功后要记住的信息

Agnes AI API 常用信息如下：

```text
API Base URL:
https://apihub.agnes-ai.com/v1

认证方式:
Authorization: Bearer 你的_API_KEY
```

也就是说，后续接入软件时通常需要填：

| 配置项 | 填什么 |
|---|---|
| API Base / Base URL | `https://apihub.agnes-ai.com/v1` |
| API Key | 你刚刚复制的 Agnes API Key |
| 认证方式 | Bearer Token |
| 模型名称 | 以 Agnes 控制台或官方文档显示为准 |

---

## 10. 接入小爆来咯时怎么填

如果你要把 Agnes AI 接入 **小爆来咯**：

1. 打开小爆来咯。
2. 左侧进入 **设置**。
3. 点击 **大模型API**。
4. 点击 **+ 自定义**。
5. 填写一个名称，例如：

   ```text
   Agnes AI
   ```

6. API Base 填：

   ```text
   https://apihub.agnes-ai.com/v1
   ```

7. API Key 填你在 Agnes 平台复制的 Key。
8. 模型名称按 Agnes 平台当前可用模型填写。
9. 点击 **测试连接**。
10. 测试成功后点击 **设为当前使用**。
11. 点击 **保存设置**。

如果模型名不知道填什么，先去 Agnes AI 文档或控制台查看当前支持的模型名称。

---

## 11. 常见问题

### 找不到 API Key 页面

先确认你进入的是 API 平台：

```text
https://platform.agnes-ai.com/
```

如果你进入的是普通聊天或应用页面，可能找不到 API Key。请从平台里找 **API / Developer / Settings / API Keys** 相关入口。

### 没收到验证码或验证邮件

可以尝试：

- 检查垃圾邮件。
- 等 1 到 3 分钟。
- 点击重新发送验证码。
- 换一个常用邮箱。

### Key 创建后忘记复制

如果页面已经不显示完整 Key，通常无法找回。

处理方式：

```text
删除旧 Key -> 重新创建一个新 Key -> 立刻复制保存
```

### 接入软件测试失败

优先检查：

- API Base 是否填成 `https://apihub.agnes-ai.com/v1`。
- Key 前后是否多复制了空格。
- 认证方式是否是 Bearer Token。
- 模型名称是否填对。
- Agnes 平台账号是否还有可用额度或权限。

---

## 12. 安全提醒

API Key 很重要，请记住：

- 不要公开。
- 不要发给陌生人。
- 不要放进公开文档。
- 不要截图露出完整 Key。
- 不用了就删除。
- 泄露了就立刻重新生成。

---

## 13. 一句话总结

你只需要记住这条路线：

```text
打开 https://platform.agnes-ai.com/
注册并登录
进入 API 密钥 / API Keys
创建新的密钥
复制并保存 Key
```

后续接入软件时，API Base 通常填：

```text
https://apihub.agnes-ai.com/v1
```
