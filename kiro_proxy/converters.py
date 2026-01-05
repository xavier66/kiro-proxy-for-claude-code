"""协议转换模块 - Anthropic/OpenAI/Gemini <-> Kiro"""
import json
import hashlib
import base64
import re
from typing import List, Dict, Any, Tuple, Optional


def generate_session_id(messages: list) -> str:
    """基于消息内容生成会话ID"""
    content = json.dumps(messages[:3], sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def extract_images_from_content(content) -> Tuple[str, List[dict]]:
    """从消息内容中提取文本和图片
    
    Returns:
        (text_content, images_list)
    """
    if isinstance(content, str):
        return content, []
    
    if not isinstance(content, list):
        return str(content) if content else "", []
    
    text_parts = []
    images = []
    
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict):
            block_type = block.get("type", "")
            
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            
            elif block_type == "image":
                # Anthropic 格式
                source = block.get("source", {})
                media_type = source.get("media_type", "image/jpeg")
                data = source.get("data", "")
                
                # 提取格式
                fmt = "jpeg"
                if "png" in media_type:
                    fmt = "png"
                elif "gif" in media_type:
                    fmt = "gif"
                elif "webp" in media_type:
                    fmt = "webp"
                
                if data:
                    images.append({
                        "format": fmt,
                        "source": {"bytes": data}
                    })
            
            elif block_type == "image_url":
                # OpenAI 格式
                image_url = block.get("image_url", {})
                url = image_url.get("url", "")
                
                if url.startswith("data:"):
                    # data:image/jpeg;base64,/9j/4AAQ...
                    match = re.match(r'data:image/(\w+);base64,(.+)', url)
                    if match:
                        fmt = match.group(1)
                        data = match.group(2)
                        images.append({
                            "format": fmt,
                            "source": {"bytes": data}
                        })
    
    return "\n".join(text_parts), images


# ==================== Anthropic 转换 ====================

def convert_anthropic_tools_to_kiro(tools: List[dict]) -> List[dict]:
    """将 Anthropic 工具格式转换为 Kiro 格式"""
    kiro_tools = []
    for tool in tools:
        kiro_tool = {
            "toolSpecification": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "inputSchema": {
                    "json": tool.get("input_schema", {})
                }
            }
        }
        kiro_tools.append(kiro_tool)
    return kiro_tools


def convert_anthropic_messages_to_kiro(messages: List[dict], system = "") -> Tuple[str, List[dict], List[dict]]:
    """将 Anthropic 消息格式转换为 Kiro 格式
    
    Returns:
        (user_content, history, tool_results)
        - user_content: 当前用户消息内容
        - history: 历史消息列表
        - tool_results: 当前消息的工具结果（放入 userInputMessageContext.toolResults）
    """
    history = []
    user_content = ""
    current_tool_results = []  # 当前消息的工具结果
    
    # 处理 system 可能是列表的情况
    system_text = ""
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                system_text += block.get("text", "") + "\n"
            elif isinstance(block, str):
                system_text += block + "\n"
        system_text = system_text.strip()
    elif isinstance(system, str):
        system_text = system
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        is_last = (i == len(messages) - 1)
        
        # 处理 content 可能是列表的情况
        tool_results = []
        text_parts = []
        
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        # 工具结果 - Kiro 格式
                        tr_content = block.get("content", "")
                        if isinstance(tr_content, list):
                            tr_text_parts = []
                            for tc in tr_content:
                                if isinstance(tc, dict) and tc.get("type") == "text":
                                    tr_text_parts.append(tc.get("text", ""))
                                elif isinstance(tc, str):
                                    tr_text_parts.append(tc)
                            tr_content = "\n".join(tr_text_parts)
                        
                        tool_results.append({
                            "content": [{"text": tr_content}],
                            "status": "success",
                            "toolUseId": block.get("tool_use_id", "")
                        })
                elif isinstance(block, str):
                    text_parts.append(block)
            
            content = "\n".join(text_parts) if text_parts else ""
        
        # 如果有工具结果
        if tool_results:
            if is_last:
                # 最后一条消息的工具结果
                current_tool_results = tool_results
                user_content = content if content else "继续"
            else:
                # 非最后一条，加入历史（带 toolResults）
                history.append({
                    "userInputMessage": {
                        "content": content if content else "继续",
                        "modelId": "claude-sonnet-4",
                        "origin": "AI_EDITOR",
                        "userInputMessageContext": {
                            "toolResults": tool_results
                        }
                    }
                })
            continue
        
        if role == "user":
            if system_text and not history:
                content = f"{system_text}\n\n{content}"
            
            if is_last:
                user_content = content
            else:
                history.append({
                    "userInputMessage": {
                        "content": content,
                        "modelId": "claude-sonnet-4",
                        "origin": "AI_EDITOR"
                    }
                })
        elif role == "assistant":
            # 检查是否有工具调用
            tool_uses = []
            assistant_text = ""
            if isinstance(msg.get("content"), list):
                text_parts = []
                for block in msg["content"]:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            tool_uses.append({
                                "toolUseId": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input": block.get("input", {})
                            })
                        elif block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                assistant_text = "\n".join(text_parts)
            else:
                assistant_text = content if isinstance(content, str) else ""
            
            history.append({
                "assistantResponseMessage": {
                    "content": assistant_text,
                    "toolUses": tool_uses
                }
            })
    
    return user_content, history, current_tool_results


def convert_kiro_response_to_anthropic(result: dict, model: str, msg_id: str) -> dict:
    """将 Kiro 响应转换为 Anthropic 格式"""
    content = []
    text = "".join(result["content"])
    if text:
        content.append({"type": "text", "text": text})
    
    for tool_use in result["tool_uses"]:
        content.append(tool_use)
    
    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": result["stop_reason"],
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 100}
    }


# ==================== OpenAI 转换 ====================

def convert_openai_messages_to_kiro(messages: List[dict], model: str) -> Tuple[str, List[dict]]:
    """将 OpenAI 消息格式转换为 Kiro 格式"""
    system_content = ""
    history = []
    user_content = ""
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if c.get("type") == "text"])
        
        if not content:
            content = ""
        
        if role == "system":
            system_content = content
        elif role == "user":
            if system_content and not history:
                content = f"{system_content}\n\n{content}"
            history.append({
                "userInputMessage": {
                    "content": content,
                    "modelId": model,
                    "origin": "AI_EDITOR"
                }
            })
            user_content = content
        elif role == "assistant":
            history.append({
                "assistantResponseMessage": {
                    "content": content
                }
            })
    
    # 如果没有用户消息，返回空
    if not user_content:
        user_content = messages[-1].get("content", "") if messages else ""
        if isinstance(user_content, list):
            user_content = " ".join([c.get("text", "") for c in user_content if c.get("type") == "text"])
    
    # 历史不包含最后一条用户消息（它会作为当前输入）
    return user_content, history[:-1] if len(history) > 1 else []


# ==================== Gemini 转换 ====================

def convert_gemini_contents_to_kiro(contents: List[dict], system_instruction: dict, model: str) -> Tuple[str, List[dict]]:
    """将 Gemini 消息格式转换为 Kiro 格式"""
    history = []
    user_content = ""
    
    # 处理 system instruction
    system_text = ""
    if system_instruction:
        parts = system_instruction.get("parts", [])
        system_text = " ".join(p.get("text", "") for p in parts if "text" in p)
    
    for content in contents:
        role = content.get("role", "user")
        parts = content.get("parts", [])
        text = " ".join(p.get("text", "") for p in parts if "text" in p)
        
        if role == "user":
            if system_text and not history:
                text = f"{system_text}\n\n{text}"
            history.append({
                "userInputMessage": {
                    "content": text,
                    "modelId": model,
                    "origin": "AI_EDITOR"
                }
            })
            user_content = text
        elif role == "model":
            history.append({
                "assistantResponseMessage": {
                    "content": text
                }
            })
    
    return user_content, history[:-1] if history else []
