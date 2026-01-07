"""管理 API 处理"""
import json
import uuid
import time
import httpx
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from fastapi import Request, HTTPException, Query

from ..config import TOKEN_PATH, MODELS_URL
from ..core import state, Account, stats_manager, get_browsers_info, open_url, flow_monitor, get_account_usage
from ..credential import quota_manager, generate_machine_id, get_kiro_version, CredentialStatus
from ..auth import start_device_flow, poll_device_flow, cancel_device_flow, get_login_state, save_credentials_to_file
from ..auth import start_social_auth, exchange_social_auth_token, cancel_social_auth, get_social_auth_state


async def get_status():
    """服务状态"""
    try:
        with open(TOKEN_PATH) as f:
            data = json.load(f)
        return {
            "ok": True,
            "expires": data.get("expiresAt"),
            "stats": state.get_stats()
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "stats": state.get_stats()}


async def get_stats():
    """获取统计信息"""
    return state.get_stats()


async def get_logs(limit: int = Query(100, le=1000)):
    """获取请求日志"""
    logs = list(state.request_logs)[-limit:]
    return {
        "logs": [asdict(log) for log in reversed(logs)],
        "total": len(state.request_logs)
    }


async def get_accounts():
    """获取账号列表（增强版）"""
    return {
        "accounts": state.get_accounts_status()
    }


async def get_account_detail(account_id: str):
    """获取账号详细信息"""
    for acc in state.accounts:
        if acc.id == account_id:
            creds = acc.get_credentials()
            return {
                "id": acc.id,
                "name": acc.name,
                "enabled": acc.enabled,
                "status": acc.status.value,
                "available": acc.is_available(),
                "request_count": acc.request_count,
                "error_count": acc.error_count,
                "last_used": acc.last_used,
                "token_path": acc.token_path,
                "machine_id": acc.get_machine_id()[:16] + "...",
                "credentials": {
                    "has_access_token": bool(creds and creds.access_token),
                    "has_refresh_token": bool(creds and creds.refresh_token),
                    "has_client_id": bool(creds and creds.client_id),
                    "auth_method": creds.auth_method if creds else None,
                    "region": creds.region if creds else None,
                    "expires_at": creds.expires_at if creds else None,
                    "is_expired": acc.is_token_expired(),
                    "is_expiring_soon": acc.is_token_expiring_soon(),
                } if creds else None,
                "cooldown": {
                    "is_cooldown": not quota_manager.is_available(acc.id),
                    "remaining_seconds": quota_manager.get_cooldown_remaining(acc.id),
                }
            }
    raise HTTPException(404, "Account not found")


async def add_account(request: Request):
    """添加账号"""
    body = await request.json()
    name = body.get("name", f"账号{len(state.accounts)+1}")
    token_path = body.get("token_path")
    
    if not token_path or not Path(token_path).exists():
        raise HTTPException(400, "Invalid token path")
    
    account = Account(
        id=uuid.uuid4().hex[:8],
        name=name,
        token_path=token_path
    )
    state.accounts.append(account)
    
    # 预加载凭证
    account.load_credentials()
    
    # 保存配置
    state._save_accounts()
    
    return {"ok": True, "account_id": account.id}


async def delete_account(account_id: str):
    """删除账号"""
    state.accounts = [a for a in state.accounts if a.id != account_id]
    # 清理配额记录
    quota_manager.restore(account_id)
    # 保存配置
    state._save_accounts()
    return {"ok": True}


async def toggle_account(account_id: str):
    """启用/禁用账号"""
    for acc in state.accounts:
        if acc.id == account_id:
            acc.enabled = not acc.enabled
            # 保存配置
            state._save_accounts()
            return {"ok": True, "enabled": acc.enabled}
    raise HTTPException(404, "Account not found")


async def refresh_account_token(account_id: str):
    """刷新指定账号的 token"""
    success, message = await state.refresh_account_token(account_id)
    return {"ok": success, "message": message}


async def refresh_all_tokens():
    """刷新所有即将过期的 token"""
    results = await state.refresh_expiring_tokens()
    return {
        "ok": True,
        "results": results,
        "refreshed": len([r for r in results if r["success"]])
    }


async def restore_account(account_id: str):
    """恢复账号（从冷却状态）"""
    restored = quota_manager.restore(account_id)
    if restored:
        for acc in state.accounts:
            if acc.id == account_id:
                from ..credential import CredentialStatus
                acc.status = CredentialStatus.ACTIVE
                break
    return {"ok": restored}


async def speedtest():
    """测试 API 延迟"""
    account = state.get_available_account()
    if not account:
        return {"ok": False, "error": "No available account"}
    
    start = time.time()
    try:
        token = account.get_token()
        machine_id = account.get_machine_id()
        kiro_version = get_kiro_version()
        
        headers = {
            "content-type": "application/json",
            "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{kiro_version}-{machine_id}",
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(MODELS_URL, headers=headers, params={"origin": "AI_EDITOR"})
            latency = (time.time() - start) * 1000
            return {
                "ok": resp.status_code == 200,
                "latency_ms": round(latency, 2),
                "status": resp.status_code,
                "account_id": account.id
            }
    except Exception as e:
        return {"ok": False, "error": str(e), "latency_ms": (time.time() - start) * 1000}


async def scan_tokens():
    """扫描系统中的 Kiro token 文件"""
    found = []
    sso_cache = Path.home() / ".aws/sso/cache"
    if sso_cache.exists():
        for f in sso_cache.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if "accessToken" in data:
                        # 检查是否已添加
                        already_added = any(a.token_path == str(f) for a in state.accounts)
                        
                        auth_method = data.get("authMethod", "social")
                        client_id_hash = data.get("clientIdHash")
                        
                        # 检查 IdC 配置完整性
                        idc_complete = None
                        if auth_method == "idc" and client_id_hash:
                            hash_file = sso_cache / f"{client_id_hash}.json"
                            if hash_file.exists():
                                try:
                                    with open(hash_file) as hf:
                                        hash_data = json.load(hf)
                                        idc_complete = bool(hash_data.get("clientId") and hash_data.get("clientSecret"))
                                except:
                                    idc_complete = False
                            else:
                                idc_complete = False
                        
                        found.append({
                            "path": str(f),
                            "name": f.stem,
                            "expires": data.get("expiresAt"),
                            "auth_method": auth_method,
                            "region": data.get("region", "us-east-1"),
                            "has_refresh_token": "refreshToken" in data,
                            "already_added": already_added,
                            "idc_config_complete": idc_complete,
                        })
            except:
                pass
    return {"tokens": found}


async def add_from_scan(request: Request):
    """从扫描结果添加账号"""
    body = await request.json()
    token_path = body.get("path")
    name = body.get("name", "扫描账号")
    
    if not token_path or not Path(token_path).exists():
        raise HTTPException(400, "Token 文件不存在")
    
    if any(a.token_path == token_path for a in state.accounts):
        raise HTTPException(400, "该账号已添加")
    
    try:
        with open(token_path) as f:
            data = json.load(f)
            if "accessToken" not in data:
                raise HTTPException(400, "无效的 token 文件")
    except json.JSONDecodeError:
        raise HTTPException(400, "无效的 JSON 文件")
    
    account = Account(
        id=uuid.uuid4().hex[:8],
        name=name,
        token_path=token_path
    )
    state.accounts.append(account)
    
    # 预加载凭证
    account.load_credentials()
    
    # 保存配置
    state._save_accounts()
    
    return {"ok": True, "account_id": account.id}


async def export_config():
    """导出配置"""
    return {
        "accounts": [
            {"name": a.name, "token_path": a.token_path, "enabled": a.enabled}
            for a in state.accounts
        ],
        "exported_at": datetime.now().isoformat()
    }


async def import_config(request: Request):
    """导入配置"""
    body = await request.json()
    accounts = body.get("accounts", [])
    imported = 0
    
    for acc_data in accounts:
        token_path = acc_data.get("token_path", "")
        if Path(token_path).exists():
            if not any(a.token_path == token_path for a in state.accounts):
                account = Account(
                    id=uuid.uuid4().hex[:8],
                    name=acc_data.get("name", "导入账号"),
                    token_path=token_path,
                    enabled=acc_data.get("enabled", True)
                )
                state.accounts.append(account)
                account.load_credentials()
                imported += 1
    
    # 保存配置
    state._save_accounts()
    
    return {"ok": True, "imported": imported}


async def refresh_token_check():
    """检查所有账号的 token 状态"""
    results = []
    for acc in state.accounts:
        creds = acc.get_credentials()
        if creds:
            results.append({
                "id": acc.id,
                "name": acc.name,
                "valid": not acc.is_token_expired(),
                "expiring_soon": acc.is_token_expiring_soon(),
                "expires": creds.expires_at,
                "auth_method": creds.auth_method,
                "has_refresh_token": bool(creds.refresh_token),
            })
        else:
            results.append({
                "id": acc.id,
                "name": acc.name,
                "valid": False,
                "error": "无法加载凭证"
            })
    
    return {"accounts": results}


async def get_quota_status():
    """获取配额状态"""
    return {
        "cooldown_seconds": quota_manager.cooldown_seconds,
        "exceeded_count": len(quota_manager.exceeded_records),
        "exceeded_credentials": [
            {
                "credential_id": r.credential_id,
                "exceeded_at": r.exceeded_at,
                "cooldown_until": r.cooldown_until,
                "remaining_seconds": max(0, int(r.cooldown_until - time.time())),
                "reason": r.reason
            }
            for r in quota_manager.exceeded_records.values()
        ]
    }


async def get_kiro_login_url():
    """获取 Kiro 登录说明"""
    return {
        "message": "Kiro 使用 AWS Identity Center 认证，无法直接 OAuth",
        "instructions": [
            "1. 打开 Kiro IDE",
            "2. 点击登录按钮，使用 Google/GitHub 账号登录",
            "3. 登录成功后，token 会自动保存到 ~/.aws/sso/cache/",
            "4. 本代理会自动读取该 token"
        ],
        "token_path": str(TOKEN_PATH),
        "token_exists": TOKEN_PATH.exists()
    }


async def get_detailed_stats():
    """获取详细统计信息"""
    basic_stats = state.get_stats()
    detailed = stats_manager.get_all_stats()
    
    return {
        **basic_stats,
        "detailed": detailed
    }


async def run_health_check():
    """手动触发健康检查"""
    results = []
    
    for acc in state.accounts:
        if not acc.enabled:
            results.append({
                "id": acc.id,
                "name": acc.name,
                "status": "disabled",
                "healthy": False
            })
            continue
        
        try:
            token = acc.get_token()
            if not token:
                acc.status = CredentialStatus.UNHEALTHY
                results.append({
                    "id": acc.id,
                    "name": acc.name,
                    "status": "no_token",
                    "healthy": False
                })
                continue
            
            headers = {
                "Authorization": f"Bearer {token}",
                "content-type": "application/json"
            }
            
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    MODELS_URL,
                    headers=headers,
                    params={"origin": "AI_EDITOR"}
                )
                
                if resp.status_code == 200:
                    if acc.status == CredentialStatus.UNHEALTHY:
                        acc.status = CredentialStatus.ACTIVE
                    results.append({
                        "id": acc.id,
                        "name": acc.name,
                        "status": "healthy",
                        "healthy": True,
                        "latency_ms": resp.elapsed.total_seconds() * 1000
                    })
                elif resp.status_code == 401:
                    acc.status = CredentialStatus.UNHEALTHY
                    results.append({
                        "id": acc.id,
                        "name": acc.name,
                        "status": "auth_failed",
                        "healthy": False
                    })
                elif resp.status_code == 429:
                    results.append({
                        "id": acc.id,
                        "name": acc.name,
                        "status": "rate_limited",
                        "healthy": True  # 限流不代表不健康
                    })
                else:
                    results.append({
                        "id": acc.id,
                        "name": acc.name,
                        "status": f"error_{resp.status_code}",
                        "healthy": False
                    })
                    
        except Exception as e:
            results.append({
                "id": acc.id,
                "name": acc.name,
                "status": "error",
                "healthy": False,
                "error": str(e)
            })
    
    healthy_count = len([r for r in results if r["healthy"]])
    return {
        "ok": True,
        "total": len(results),
        "healthy": healthy_count,
        "unhealthy": len(results) - healthy_count,
        "results": results
    }


# ==================== Kiro 登录 API ====================

async def get_browsers():
    """获取可用浏览器列表"""
    return {"browsers": get_browsers_info()}


async def start_kiro_login(request: Request):
    """启动 Kiro 设备授权登录"""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    region = body.get("region", "us-east-1")
    browser = body.get("browser", "default")
    incognito = body.get("incognito", False)
    
    success, result = await start_device_flow(region)
    
    if success:
        # 用指定浏览器打开授权页面
        open_url(result["verification_uri"], browser, incognito)
        
        return {
            "ok": True,
            "user_code": result["user_code"],
            "verification_uri": result["verification_uri"],
            "expires_in": result["expires_in"],
            "interval": result["interval"],
        }
    else:
        return {"ok": False, "error": result.get("error", "未知错误")}


async def poll_kiro_login():
    """轮询 Kiro 登录状态"""
    success, result = await poll_device_flow()
    
    if not success:
        return {"ok": False, "error": result.get("error", "未知错误")}
    
    if result.get("completed"):
        # 授权完成，保存凭证并添加账号
        credentials = result["credentials"]
        
        # 保存到文件
        from ..auth.device_flow import save_credentials_to_file
        file_path = await save_credentials_to_file(credentials)
        
        # 添加账号
        account = Account(
            id=uuid.uuid4().hex[:8],
            name="在线登录账号",
            token_path=file_path
        )
        state.accounts.append(account)
        account.load_credentials()
        state._save_accounts()
        
        return {
            "ok": True,
            "completed": True,
            "account_id": account.id,
            "message": "登录成功，账号已添加"
        }
    else:
        return {
            "ok": True,
            "completed": False,
            "status": result.get("status", "pending")
        }


async def cancel_kiro_login():
    """取消 Kiro 登录"""
    cancelled = cancel_device_flow()
    return {"ok": cancelled}


async def get_kiro_login_status():
    """获取当前登录状态"""
    login_state = get_login_state()
    if login_state:
        return {
            "ok": True,
            "in_progress": True,
            **login_state
        }
    else:
        return {"ok": True, "in_progress": False}


# ==================== Social Auth API (Google/GitHub) ====================

async def start_social_login(request: Request):
    """启动 Social Auth 登录 (Google/GitHub)"""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    provider = body.get("provider", "google")
    browser = body.get("browser", "default")
    incognito = body.get("incognito", False)
    
    success, result = await start_social_auth(provider)
    
    if success:
        # 用指定浏览器打开登录页面
        open_url(result["login_url"], browser, incognito)
        
        return {
            "ok": True,
            "provider": result["provider"],
            "login_url": result["login_url"],
            "state": result["state"],
        }
    else:
        return {"ok": False, "error": result.get("error", "未知错误")}


async def exchange_social_token(request: Request):
    """交换 Social Auth Token"""
    body = await request.json()
    code = body.get("code")
    oauth_state = body.get("state")
    
    if not code or not oauth_state:
        return {"ok": False, "error": "缺少 code 或 state"}
    
    success, result = await exchange_social_auth_token(code, oauth_state)
    
    if not success:
        return {"ok": False, "error": result.get("error", "未知错误")}
    
    if result.get("completed"):
        # 保存凭证并添加账号
        credentials = result["credentials"]
        provider = result.get("provider", "Social")
        
        # 保存到文件
        from ..auth.device_flow import save_credentials_to_file
        file_path = await save_credentials_to_file(credentials, f"kiro-{provider.lower()}-auth")
        
        # 添加账号
        account = Account(
            id=uuid.uuid4().hex[:8],
            name=f"{provider} 登录账号",
            token_path=file_path
        )
        state.accounts.append(account)
        account.load_credentials()
        state._save_accounts()
        
        return {
            "ok": True,
            "completed": True,
            "account_id": account.id,
            "provider": provider,
            "message": f"{provider} 登录成功，账号已添加"
        }
    
    return {"ok": False, "error": "Token 交换失败"}


async def cancel_social_login():
    """取消 Social Auth 登录"""
    cancelled = cancel_social_auth()
    return {"ok": cancelled}


async def get_social_login_status():
    """获取 Social Auth 状态"""
    auth_state = get_social_auth_state()
    if auth_state:
        return {
            "ok": True,
            "in_progress": True,
            **auth_state
        }
    else:
        return {"ok": True, "in_progress": False}


# ==================== Flow Monitor API ====================

async def get_flows(
    protocol: str = None,
    model: str = None,
    account_id: str = None,
    state_filter: str = None,
    has_error: bool = None,
    bookmarked: bool = None,
    search: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """查询 Flows"""
    from ..core.flow_monitor import FlowState
    
    state_enum = None
    if state_filter:
        try:
            state_enum = FlowState(state_filter)
        except ValueError:
            pass
    
    flows = flow_monitor.query(
        protocol=protocol,
        model=model,
        account_id=account_id,
        state=state_enum,
        has_error=has_error,
        bookmarked=bookmarked,
        search=search,
        limit=limit,
        offset=offset,
    )
    
    return {
        "flows": [f.to_dict() for f in flows],
        "total": len(flows),
    }


async def get_flow_detail(flow_id: str):
    """获取 Flow 详情"""
    flow = flow_monitor.get_flow(flow_id)
    if not flow:
        raise HTTPException(404, "Flow not found")
    return flow.to_full_dict()


async def get_flow_stats():
    """获取 Flow 统计"""
    return flow_monitor.get_stats()


async def bookmark_flow(flow_id: str, request: Request):
    """书签 Flow"""
    body = await request.json()
    bookmarked = body.get("bookmarked", True)
    flow_monitor.bookmark_flow(flow_id, bookmarked)
    return {"ok": True}


async def add_flow_note(flow_id: str, request: Request):
    """添加 Flow 备注"""
    body = await request.json()
    note = body.get("note", "")
    flow_monitor.add_note(flow_id, note)
    return {"ok": True}


async def add_flow_tag(flow_id: str, request: Request):
    """添加 Flow 标签"""
    body = await request.json()
    tag = body.get("tag", "")
    if tag:
        flow_monitor.add_tag(flow_id, tag)
    return {"ok": True}


async def export_flows(request: Request):
    """导出 Flows"""
    body = await request.json()
    flow_ids = body.get("flow_ids", [])
    format = body.get("format", "json")
    
    content = flow_monitor.export(flow_ids if flow_ids else None, format)
    return {"content": content, "format": format}


# ==================== Usage API ====================

async def get_account_usage_info(account_id: str):
    """获取账号用量信息"""
    for acc in state.accounts:
        if acc.id == account_id:
            success, result = await get_account_usage(acc)
            if success:
                return {
                    "ok": True,
                    "account_id": account_id,
                    "account_name": acc.name,
                    "usage": {
                        "subscription_title": result.subscription_title,
                        "usage_limit": result.usage_limit,
                        "current_usage": result.current_usage,
                        "balance": result.balance,
                        "is_low_balance": result.is_low_balance,
                        "free_trial_limit": result.free_trial_limit,
                        "free_trial_usage": result.free_trial_usage,
                        "bonus_limit": result.bonus_limit,
                        "bonus_usage": result.bonus_usage,
                    }
                }
            else:
                return {"ok": False, "error": result.get("error", "查询失败")}
    raise HTTPException(404, "Account not found")
