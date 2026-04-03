# 代理配置说明

## 启用代理

KiroProxy 现在支持通过环境变量配置代理，可以提高访问 AWS 服务的速度。

### 方法一：环境变量配置

```bash
# 启用代理
export KIRO_PROXY_ENABLED=true
export KIRO_PROXY_URL=http://127.0.0.1:7897

# 启动服务
python run.py
```

### 方法二：启动时设置

```bash
# 一次性启用代理
KIRO_PROXY_ENABLED=true KIRO_PROXY_URL=http://127.0.0.1:7897 python run.py
```

### 方法三：Windows 批处理

```batch
set KIRO_PROXY_ENABLED=true
set KIRO_PROXY_URL=http://127.0.0.1:7897
python run.py
```

## 代理配置说明

- `KIRO_PROXY_ENABLED`: 是否启用代理 (true/false)
- `KIRO_PROXY_URL`: 代理服务器地址，默认 `http://127.0.0.1:7897`

## 支持的代理类型

- HTTP 代理
- HTTPS 代理
- SOCKS 代理 (需要 `httpx[socks]`)

## 注意事项

1. 确保代理服务器正常运行
2. 代理会应用到所有对外的 HTTP 请求
3. 启用代理后会在日志中显示代理信息
4. 如果代理不可用，请求会失败，建议先测试代理连通性