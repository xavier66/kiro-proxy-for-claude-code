# 快速开始

## 安装运行

### 方式一：下载预编译版本
从 [Releases](../../releases) 下载对应平台的安装包，解压后直接运行。

### 方式二：从源码运行
```bash
git clone https://github.com/yourname/kiro-proxy.git
cd kiro-proxy
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

启动后访问 http://localhost:8080

## 获取 Kiro 账号

### 方式一：在线登录（推荐）
1. 打开 Web UI，点击「账号」标签
2. 点击「在线登录」按钮
3. 选择登录方式：Google / GitHub / AWS Builder ID
4. 在浏览器中完成授权
5. 账号自动添加到代理

### 方式二：扫描 Token
1. 打开 Kiro IDE，使用 Google/GitHub 账号登录
2. 登录成功后 token 自动保存到 `~/.aws/sso/cache/`
3. 在 Web UI 点击「扫描 Token」
4. 选择要添加的账号

## 配置 AI 客户端

### Claude Code (VSCode 插件)
```
名称: Kiro Proxy
API Key: any（随便填）
Base URL: http://localhost:8080
模型: claude-sonnet-4
```

### Codex CLI
```
名称: Kiro Proxy
API Key: any
Endpoint: http://localhost:8080/v1
模型: gpt-4o
```

### Gemini CLI
```
Base URL: http://localhost:8080/v1
模型: gemini-pro
```
