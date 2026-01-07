# 功能特性

## 核心功能

### 多协议支持
支持三种主流 AI API 协议：
- **OpenAI** - `/v1/chat/completions`, `/v1/models`
- **Anthropic** - `/v1/messages`, `/v1/messages/count_tokens`
- **Gemini** - `/v1/models/{model}:generateContent`

### 多账号轮询
- 支持添加多个 Kiro 账号
- 自动负载均衡，轮询使用
- 会话粘性：同一会话 60 秒内使用同一账号

### Token 自动刷新
- 后台每 5 分钟检查 Token 状态
- 提前 15 分钟自动刷新即将过期的 Token
- 支持 Social 认证（Google/GitHub）的 Token 刷新

### 配额管理
- 自动检测 429 错误
- 超限账号自动冷却 5 分钟
- 自动切换到其他可用账号
- 冷却结束自动恢复

### 流量监控
- 记录所有 LLM 请求
- 支持搜索、过滤、导出
- 显示 Token 使用量
- 支持书签和备注

## 登录方式

### Google 登录
使用 Google 账号登录，通过 OAuth 授权。

### GitHub 登录
使用 GitHub 账号登录，通过 OAuth 授权。

### AWS Builder ID
使用 AWS Builder ID 登录，通过 Device Code Flow 授权。

## 配置持久化
- 账号配置保存到 `~/.kiro-proxy/config.json`
- 重启代理不丢失配置
- 支持导入/导出配置

## 健康检查
- 每 10 分钟自动检测账号可用性
- 自动标记不健康的账号
- 可手动触发健康检查
