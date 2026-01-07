# API 文档

## AI 协议端点

### OpenAI 协议

#### Chat Completions
```
POST /v1/chat/completions
```
兼容 OpenAI Chat API，支持流式和非流式输出。

**请求示例：**
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

#### 模型列表
```
GET /v1/models
```
返回可用模型列表。

### Anthropic 协议

#### Messages
```
POST /v1/messages
```
兼容 Anthropic Messages API。

**请求示例：**
```json
{
  "model": "claude-sonnet-4",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 1024
}
```

#### Token 计数
```
POST /v1/messages/count_tokens
```

### Gemini 协议
```
POST /v1/models/{model}:generateContent
```

## 管理 API

### 状态
```
GET /api/status
```
返回服务状态和统计信息。

### 账号管理
```
GET /api/accounts          # 获取所有账号
GET /api/accounts/{id}     # 获取账号详情
POST /api/accounts         # 添加账号
DELETE /api/accounts/{id}  # 删除账号
POST /api/accounts/{id}/toggle   # 启用/禁用
POST /api/accounts/{id}/refresh  # 刷新 Token
POST /api/accounts/{id}/restore  # 恢复冷却
GET /api/accounts/{id}/usage     # 查询用量
```

### 流量监控
```
GET /api/flows             # 查询流量记录
GET /api/flows/stats       # 流量统计
GET /api/flows/{id}        # 流量详情
POST /api/flows/{id}/bookmark  # 书签
POST /api/flows/{id}/note      # 添加备注
POST /api/flows/export         # 导出
```

### 其他
```
GET /api/quota             # 配额状态
GET /api/logs              # 请求日志
POST /api/speedtest        # 速度测试
POST /api/health-check     # 健康检查
GET /api/browsers          # 可用浏览器
```

## 模型映射

| 请求模型 | 实际模型 |
|----------|----------|
| gpt-4o, gpt-4 | claude-sonnet-4 |
| gpt-4o-mini, gpt-3.5-turbo | claude-haiku-4.5 |
| o1, o1-preview | claude-opus-4.5 |
| claude-sonnet-4 | claude-sonnet-4 |
| claude-sonnet-4.5 | claude-sonnet-4.5 |
| gemini-pro | claude-sonnet-4 |
