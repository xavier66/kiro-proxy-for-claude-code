"""OpenAI Responses API 处理 - /v1/responses

Codex CLI 新版本使用的 API 端点
"""
import json
import uuid
import time
import asyncio
import httpx
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse

from ..config import KIRO_API_URL, map_model_name
from ..core import state, is_retryable_error, stats_manager
from ..core.state import RequestLog
from ..core.history_manager import HistoryManager, get_history_config
from ..core.error_handler import classify_error, ErrorType, format_error_log
from ..core.rate_limiter import get_rate_limiter
from ..kiro_api import build_headers, build_kiro_request, parse_event_stream, parse_event_stream_full, is_quota_exceeded_error


def _convert_responses_input_to_kiro(input_data, instructions: str = None):
    """将 Responses API 的 input 转换为 Kiro 格式
    
    input 可以是:
    - 字符串: 直接作为用户消息
    - 列表: 消息数组，每个消息有 type, role, content
    """
    history = []
    user_content = ""
    tool_results = []
    
    # 添加 instructions 作为系统消息
    if instructions:
        history.append({"role": "system", "content": instructions})
    
    if isinstance(input_data, str):
        user_content = input_data
    elif isinstance(input_data, list):
        for item in input_data:
            if item.get("type") == "message":
                role = item.get("role", "user")
                content = item.get("content", [])
                
                # 提取文本内容
                text_parts = []
                for c in content if isinstance(content, list) else [content]:
                    if isinstance(c, str):
                        text_parts.append(c)
                    elif isinstance(c, dict):
                        if c.get("type") == "input_text":
                            text_parts.append(c.get("text", ""))
                        elif c.get("type") == "output_text":
                            text_parts.append(c.get("text", ""))
                        elif c.get("type") == "text":
                            text_parts.append(c.get("text", ""))
                
                text = "\n".join(text_parts)
                
                if role == "user":
                    user_content = text  # 最后一条用户消息
                    if history:  # 之前的消息加入历史
                        history.append({"role": "user", "content": text})
                elif role == "assistant":
                    history.append({"role": "assistant", "content": text})
                elif role == "system":
                    history.insert(0, {"role": "system", "content": text})
            
            elif item.get("type") == "function_call_output":
                # 工具调用结果
                tool_results.append({
                    "call_id": item.get("call_id", ""),
                    "output": item.get("output", "")
                })
    
    # 如果没有用户消息但有历史，取最后一条用户消息
    if not user_content and history:
        for msg in reversed(history):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                history.remove(msg)
                break
    
    return user_content, history, tool_results


def _convert_kiro_response_to_responses(result: dict, model: str, response_id: str):
    """将 Kiro 响应转换为 Responses API 格式"""
    output = []
    
    # 添加文本消息
    text = result.get("text", "")
    if text:
        output.append({
            "type": "message",
            "id": f"msg_{response_id}",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": []
            }]
        })
    
    # 添加工具调用
    for tool_use in result.get("tool_uses", []):
        output.append({
            "type": "function_call",
            "id": tool_use.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "call_id": tool_use.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "name": tool_use.get("name", ""),
            "arguments": json.dumps(tool_use.get("input", {}))
        })
    
    return {
        "id": f"resp_{response_id}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "total_tokens": result.get("input_tokens", 0) + result.get("output_tokens", 0)
        }
    }


def _convert_tools_to_kiro(tools: list) -> list:
    """将 Responses API 的 tools 转换为 Kiro 格式"""
    if not tools:
        return None
    
    kiro_tools = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool.get("function", tool)
            kiro_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {})
            })
    
    return kiro_tools if kiro_tools else None


async def handle_responses(request: Request):
    """处理 /v1/responses 请求"""
    start_time = time.time()
    log_id = uuid.uuid4().hex[:8]
    
    body = await request.json()
    model = map_model_name(body.get("model", "gpt-4o"))
    input_data = body.get("input", "")
    instructions = body.get("instructions", "")
    stream = body.get("stream", False)
    tools = body.get("tools", [])
    
    if not input_data:
        raise HTTPException(400, "input required")
    
    # 生成 session_id
    import hashlib
    session_id = hashlib.sha256(json.dumps(input_data[:3] if isinstance(input_data, list) else input_data[:100], sort_keys=True, default=str).encode()).hexdigest()[:16]
    account = state.get_available_account(session_id)
    
    if not account:
        raise HTTPException(503, "All accounts are rate limited or unavailable")
    
    # 检查 token 是否即将过期
    if account.is_token_expiring_soon(5):
        print(f"[Responses] Token 即将过期，尝试刷新: {account.id}")
        success, msg = await account.refresh_token()
        if not success:
            print(f"[Responses] Token 刷新失败: {msg}")
    
    token = account.get_token()
    if not token:
        raise HTTPException(500, f"Failed to get token for account {account.name}")
    
    creds = account.get_credentials()
    headers = build_headers(
        token,
        machine_id=account.get_machine_id(),
        profile_arn=creds.profile_arn if creds else None,
        client_id=creds.client_id if creds else None
    )
    
    # 限速检查
    rate_limiter = get_rate_limiter()
    can_request, wait_seconds, reason = rate_limiter.can_request(account.id)
    if not can_request:
        print(f"[Responses] 限速: {reason}")
        await asyncio.sleep(wait_seconds)
    
    # 转换输入格式
    user_content, history, tool_results = _convert_responses_input_to_kiro(input_data, instructions)
    
    # 历史消息预处理
    history_manager = HistoryManager(get_history_config())
    history = history_manager.pre_process(history, user_content)
    
    if history_manager.was_truncated:
        print(f"[Responses] {history_manager.truncate_info}")
    
    # 转换工具
    kiro_tools = _convert_tools_to_kiro(tools)
    
    # 构建 Kiro 请求
    kiro_request = build_kiro_request(
        user_content, model, history,
        tools=kiro_tools,
        tool_results=tool_results if tool_results else None
    )
    
    error_msg = None
    status_code = 200
    current_account = account
    max_retries = 2
    
    if stream:
        return await _handle_stream_responses(
            kiro_request, headers, current_account, model, log_id, start_time,
            history, user_content, kiro_tools, tool_results, history_manager, max_retries
        )
    
    for retry in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(verify=False, timeout=120) as client:
                resp = await client.post(KIRO_API_URL, json=kiro_request, headers=headers)
                status_code = resp.status_code
                
                # 处理配额超限
                if resp.status_code == 429 or is_quota_exceeded_error(resp.status_code, resp.text):
                    current_account.mark_quota_exceeded("Rate limited")
                    next_account = state.get_next_available_account(current_account.id)
                    if next_account and retry < max_retries:
                        print(f"[Responses] 配额超限，切换账号: {current_account.id} -> {next_account.id}")
                        current_account = next_account
                        headers["Authorization"] = f"Bearer {current_account.get_token()}"
                        continue
                    raise HTTPException(429, "All accounts rate limited")
                
                # 处理可重试的服务端错误
                if is_retryable_error(resp.status_code):
                    if retry < max_retries:
                        print(f"[Responses] 服务端错误 {resp.status_code}，重试 {retry + 1}/{max_retries}")
                        await asyncio.sleep(0.5 * (2 ** retry))
                        continue
                    raise HTTPException(resp.status_code, f"Server error after {max_retries} retries")
                
                if resp.status_code != 200:
                    error_msg = resp.text
                    error = classify_error(resp.status_code, error_msg)
                    print(format_error_log(error, current_account.id))
                    
                    if error.should_disable_account:
                        current_account.enabled = False
                        from ..credential import CredentialStatus
                        current_account.status = CredentialStatus.SUSPENDED
                    
                    if error.should_switch_account:
                        next_account = state.get_next_available_account(current_account.id)
                        if next_account and retry < max_retries:
                            current_account = next_account
                            headers["Authorization"] = f"Bearer {current_account.get_token()}"
                            continue
                    
                    if error.type == ErrorType.CONTENT_TOO_LONG:
                        truncated_history, should_retry = history_manager.handle_length_error(history, retry)
                        if should_retry:
                            history = truncated_history
                            kiro_request = build_kiro_request(user_content, model, history, kiro_tools, tool_results)
                            continue
                    
                    raise HTTPException(resp.status_code, error.user_message)
                
                result = parse_event_stream_full(resp.content)
                current_account.request_count += 1
                current_account.last_used = time.time()
                get_rate_limiter().record_request(current_account.id)
                break
                
        except HTTPException:
            raise
        except httpx.TimeoutException:
            error_msg = "Request timeout"
            status_code = 408
            if retry < max_retries:
                await asyncio.sleep(0.5 * (2 ** retry))
                continue
            raise HTTPException(408, "Request timeout after retries")
        except Exception as e:
            error_msg = str(e)
            status_code = 500
            if is_retryable_error(None, e) and retry < max_retries:
                await asyncio.sleep(0.5 * (2 ** retry))
                continue
            raise HTTPException(500, str(e))
    
    # 记录日志
    duration = (time.time() - start_time) * 1000
    state.add_log(RequestLog(
        id=log_id,
        timestamp=time.time(),
        method="POST",
        path="/v1/responses",
        model=model,
        account_id=current_account.id if current_account else None,
        status=status_code,
        duration_ms=duration,
        error=error_msg
    ))
    
    stats_manager.record_request(
        account_id=current_account.id if current_account else "unknown",
        model=model,
        success=status_code == 200,
        latency_ms=duration
    )
    
    return _convert_kiro_response_to_responses(result, model, log_id)


async def _handle_stream_responses(kiro_request, headers, account, model, log_id, start_time,
                                    history, user_content, kiro_tools, tool_results, history_manager, max_retries):
    """处理流式 Responses API 请求"""
    
    async def generate():
        nonlocal kiro_request, history
        current_account = account
        retry_count = 0
        response_id = f"resp_{log_id}"
        
        while retry_count <= max_retries:
            try:
                async with httpx.AsyncClient(verify=False, timeout=300) as client:
                    async with client.stream("POST", KIRO_API_URL, json=kiro_request, headers=headers) as response:
                        
                        if response.status_code == 429 or is_quota_exceeded_error(response.status_code, ""):
                            current_account.mark_quota_exceeded("Rate limited (stream)")
                            next_account = state.get_next_available_account(current_account.id)
                            if next_account and retry_count < max_retries:
                                current_account = next_account
                                headers["Authorization"] = f"Bearer {current_account.get_token()}"
                                retry_count += 1
                                continue
                            yield f'data: {{"type":"error","error":{{"message":"All accounts rate limited"}}}}\n\n'
                            return
                        
                        if is_retryable_error(response.status_code):
                            if retry_count < max_retries:
                                retry_count += 1
                                await asyncio.sleep(0.5 * (2 ** retry_count))
                                continue
                            yield f'data: {{"type":"error","error":{{"message":"Server error after retries"}}}}\n\n'
                            return
                        
                        if response.status_code != 200:
                            error_text = await response.aread()
                            error = classify_error(response.status_code, error_text.decode())
                            
                            if error.should_switch_account:
                                next_account = state.get_next_available_account(current_account.id)
                                if next_account and retry_count < max_retries:
                                    current_account = next_account
                                    headers["Authorization"] = f"Bearer {current_account.get_token()}"
                                    retry_count += 1
                                    continue
                            
                            yield f'data: {{"type":"error","error":{{"message":"{error.user_message}"}}}}\n\n'
                            return
                        
                        # 发送开始事件
                        yield f'data: {{"type":"response.created","response":{{"id":"{response_id}","object":"response","status":"in_progress","model":"{model}"}}}}\n\n'
                        
                        full_response = b""
                        full_content = ""
                        
                        async for chunk in response.aiter_bytes():
                            full_response += chunk
                            
                            try:
                                pos = 0
                                while pos < len(chunk):
                                    if pos + 12 > len(chunk):
                                        break
                                    total_len = int.from_bytes(chunk[pos:pos+4], 'big')
                                    if total_len == 0 or total_len > len(chunk) - pos:
                                        break
                                    headers_len = int.from_bytes(chunk[pos+4:pos+8], 'big')
                                    payload_start = pos + 12 + headers_len
                                    payload_end = pos + total_len - 4
                                    
                                    if payload_start < payload_end:
                                        try:
                                            payload = json.loads(chunk[payload_start:payload_end].decode('utf-8'))
                                            content = None
                                            if 'assistantResponseEvent' in payload:
                                                content = payload['assistantResponseEvent'].get('content')
                                            elif 'content' in payload:
                                                content = payload['content']
                                            if content:
                                                full_content += content
                                                # 发送文本增量
                                                yield f'data: {{"type":"response.output_text.delta","delta":"{json.dumps(content)[1:-1]}"}}\n\n'
                                        except Exception:
                                            pass
                                    pos += total_len
                            except Exception:
                                pass
                        
                        # 发送完成事件
                        result = parse_event_stream_full(full_response)
                        
                        yield f'data: {{"type":"response.output_text.done","text":"{json.dumps(full_content)[1:-1]}"}}\n\n'
                        yield f'data: {{"type":"response.completed","response":{{"id":"{response_id}","object":"response","status":"completed","model":"{model}"}}}}\n\n'
                        yield 'data: [DONE]\n\n'
                        
                        current_account.request_count += 1
                        current_account.last_used = time.time()
                        get_rate_limiter().record_request(current_account.id)
                        return
                        
            except httpx.TimeoutException:
                if retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(0.5 * (2 ** retry_count))
                    continue
                yield f'data: {{"type":"error","error":{{"message":"Request timeout"}}}}\n\n'
                return
            except Exception as e:
                if is_retryable_error(None, e) and retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(0.5 * (2 ** retry_count))
                    continue
                yield f'data: {{"type":"error","error":{{"message":"{str(e)}"}}}}\n\n'
                return
    
    return StreamingResponse(generate(), media_type="text/event-stream")
