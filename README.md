<p align="center">
  <img src="assets/icon.svg" width="80" height="96" alt="Kiro Proxy">
</p>

<h1 align="center">Kiro Proxy for Claude Code</h1>

<p align="center">
  将 Kiro IDE 的免费 Claude API 接入 Claude Code 的反向代理
</p>

---

> **✅ 验证状态（2026-04-03）**
>
> 已验证：**Claude Code** 接入正常，工具调用、流式响应、Context Window HUD 均正常工作。
>
> 未验证：Codex CLI、Gemini CLI（代码层面有支持，但未实际测试）

## 改动说明

本项目基于 [petehsu/KiroProxy](https://github.com/petehsu/KiroProxy) 二次开发，针对 Claude Code 接入做了以下改动：

### Bug 修复
- **修复流式 SSE 事件格式错误** — 原版只发 `data:` 行，缺少 `event:` 行。Claude Code 依赖 `event:` 字段识别事件类型，缺失后触发 non-streaming fallback，同一请求发两次，token 消耗翻倍
- **修复非流式响应内容丢失** — non-stream 路径用了错误的 key 取响应内容（`result["text"]` 应为 `result["content"]`）
- **修复 Flow 状态不持久化** — `complete_flow`/`fail_flow` 修改内存状态后未写入 SQLite，WebUI 刷新后状态回到 pending

### 新增特性
- **Context Window HUD 支持** — 估算 system + messages + tools 的 token 数，填入 SSE usage 字段，Claude Code 的 context 进度条可正常显示
- **SQLite 流量持久化** — 所有请求记录保存到 `flows.db`，重启后不丢失
- **HTTP 代理支持** — 通过环境变量配置出口代理加速请求
- **WebUI 请求详情** — 弹框展示 system_prompt、messages、tools、响应内容、token 用量，JSON 树形折叠/展开，方便研究 Claude Code 的请求细节
- **禁用重试和预摘要** — 去掉所有自动重试和智能摘要，代理只负责透传，不做任何智能处理

---

## 快速开始

### 1. 克隆并安装依赖

```bash
git clone https://github.com/xavier66/kiro-proxy-for-claude-code.git
cd kiro-proxy-for-claude-code

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 获取 Kiro Token

**方式一：扫描本地 Token（推荐，已有 Kiro IDE）**

1. 打开 Kiro IDE，确保已用 Google/GitHub 账号登录
2. 启动代理后打开 WebUI，点击「账号」→「扫描 Token」

**方式二：在线登录**

1. 启动代理后打开 WebUI，点击「账号」→「在线登录」
2. 选择 Google / GitHub / AWS Builder ID 完成授权

### 3. 启动代理

```bash
# 默认端口 8080
python run.py

# 指定端口
python run.py 8081

# 启用出口代理（可选，用于加速访问 AWS）
KIRO_PROXY_ENABLED=true KIRO_PROXY_URL=http://127.0.0.1:7897 python run.py 8081
```

启动后访问 http://localhost:8081 打开 WebUI。

### 4. 配置 Claude Code

在 Claude Code 中添加自定义 API Provider：

```
API Provider: Anthropic
API Key:      any（随便填）
Base URL:     http://localhost:8081
Model:        claude-sonnet-4-6
```

或通过环境变量：

```bash
export ANTHROPIC_BASE_URL=http://localhost:8081
export ANTHROPIC_API_KEY=any
claude
```

### 5. 验证

发一条消息，WebUI「流量」页面应出现请求记录，状态为「完成」，Claude Code 的 Context Window HUD 应显示非零进度。

---

## 模型映射

Claude Code 发送的模型名会自动映射到 Kiro API 支持的名称：

| Claude Code 模型名 | Kiro API 模型 |
|-------------------|--------------|
| `claude-sonnet-4-6` | `claude-sonnet-4.6` |
| `claude-opus-4-6` | `claude-opus-4.6` |
| `claude-haiku-4-5-20251001` | `claude-haiku-4.5` |
| 其他未知模型 | `claude-sonnet-4.6`（默认） |

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KIRO_PROXY_ENABLED` | `false` | 是否启用出口代理 |
| `KIRO_PROXY_URL` | `http://127.0.0.1:7897` | 出口代理地址 |

---

## WebUI 功能

访问 http://localhost:8081 可以：

- **流量** — 查看所有请求记录，点击任意记录展开详情（system prompt、messages、tools、响应内容、token 用量）
- **账号** — 添加/管理 Kiro 账号，查看 Token 状态
- **监控** — 请求统计、延迟、错误率
- **设置** — 限速配置等

---

## 其他客户端（未验证）

以下客户端在代码层面有支持，但未实际测试：

**Codex CLI**
```bash
export OPENAI_API_KEY=any
export OPENAI_BASE_URL=http://localhost:8081/v1
codex
```

**Gemini CLI**
```bash
export GEMINI_API_BASE=http://localhost:8081/v1
```

---

## 账号管理 CLI

```bash
python run.py accounts list              # 列出账号
python run.py accounts scan --auto       # 扫描并自动添加本地 Token
python run.py accounts add               # 手动添加 Token
python run.py accounts export -o acc.json
python run.py accounts import acc.json
python run.py login google               # 在线登录
python run.py login github
```

---

## 免责声明

本项目仅供学习研究，禁止商用。使用本项目产生的任何后果由使用者自行承担，与作者无关。

本项目与 Kiro / AWS / Anthropic 官方无关。
