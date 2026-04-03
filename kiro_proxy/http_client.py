"""统一的 HTTP 客户端工具"""
import httpx
from .config import PROXY_URL, PROXY_ENABLED


def create_http_client(timeout: float = 30, verify: bool = False, **kwargs) -> httpx.AsyncClient:
    """创建配置了代理的 HTTP 客户端

    Args:
        timeout: 超时时间（秒）
        verify: 是否验证 SSL 证书
        **kwargs: 其他 httpx.AsyncClient 参数

    Returns:
        配置好的 httpx.AsyncClient 实例
    """
    client_kwargs = {
        "timeout": timeout,
        "verify": verify,
        **kwargs
    }

    # 如果启用代理，添加代理配置
    if PROXY_ENABLED and PROXY_URL:
        # httpx 0.28.1 使用 proxy 参数而不是 proxies
        client_kwargs["proxy"] = PROXY_URL
        print(f"[HTTP Client] Using proxy: {PROXY_URL}")

    return httpx.AsyncClient(**client_kwargs)


def get_proxy_info() -> dict:
    """获取代理配置信息"""
    return {
        "enabled": PROXY_ENABLED,
        "url": PROXY_URL if PROXY_ENABLED else None,
    }