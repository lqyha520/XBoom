# Debug Session: custom-api-blocked

Status: OPEN

## Symptom
自定义 API 测试连接可用，但创作时调用 `https://api.wenwenai.org/v1/chat/completions` 返回 `Your request was blocked.`。

## Hypotheses
1. 服务商因请求头缺失或 User-Agent/Referer 等策略拦截正式创作请求。
2. 服务商因提示词内容或长度触发安全风控。
3. 服务商不兼容 OpenAI SDK 发送的某些参数，虽然已切到非流式，但仍有参数触发拦截。
4. 配置里模型名与该服务商实际支持模型不匹配，测试请求未覆盖正式模型行为。
5. base_url 处理后实际请求地址或 OpenAI SDK 生成请求体与预期不同。

## Instrumentation Plan
在 LLM 调用失败处采集不含 API Key 的请求摘要、错误类型、HTTP 状态、响应体片段、模型、URL、消息长度和参数键。

## Instrumentation Applied
已在 `src/ai_write_x/core/direct_llm.py` 的非流式请求路径添加观测点：
- `llm_request`: URL、模型、兼容模式、参数键、消息数量和长度。
- `llm_error`: 异常类型、错误消息、HTTP 状态、响应体片段、部分安全响应头。

## Evidence
待复现采集。

## Fix
待证据确认后实施。
