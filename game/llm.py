"""
game/llm.py — MiniMax M3 客户端封装

本项目唯一与 MiniMax API 通信的模块(见 ARCHITECTURE.md 第 3 节"关键约束")。
其它任何模块都不许直接发起 HTTP 请求到 LLM API。

API 规范: https://platform.minimaxi.com/docs/api-reference/text-anthropic-api
    端点: https://api.minimaxi.com/anthropic
    格式: Anthropic SDK 风格 (messages.create)
    认证: ANTHROPIC_API_KEY
    模型: MiniMax-M3
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Final

import httpx
from dotenv import load_dotenv

# override=True：让项目 .env 优先于系统环境变量。
# 否则若系统里全局设了 ANTHROPIC_BASE_URL / ANTHROPIC_MODEL（例如给其它工具用），
# 会盖掉本项目 .env 的 MiniMax 配置，导致拿 MiniMax key 打 Anthropic 端点 → 401。
load_dotenv(override=True)

# === 配置 (来自 .env) ===
ANTHROPIC_API_KEY: Final[str] = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL: Final[str] = os.getenv(
    "ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic"
).rstrip("/")
MODEL: Final[str] = os.getenv("ANTHROPIC_MODEL", "MiniMax-M3")

# 日志路径:项目根 / logs / m3_calls.jsonl
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
LOG_FILE: Final[Path] = _PROJECT_ROOT / "logs" / "m3_calls.jsonl"

# 调用参数
MAX_RETRIES: Final[int] = 2
TIMEOUT_SEC: Final[float] = 60.0


class LLMError(RuntimeError):
    """M3 调用失败(已重试)抛出。上层负责降级。"""


def _log_call(record: dict[str, Any]) -> None:
    """追加一行到 logs/m3_calls.jsonl。日志失败不应影响主流程。"""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def count_tokens(text: str) -> int:
    """
    用官方 count_tokens 接口精确计算 token 数。
    失败时抛 LLMError(调用方应自行决定是否降级到估算)。
    """
    if not ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY 未设置")

    url = f"{ANTHROPIC_BASE_URL}/v1/messages/count_tokens"
    headers = {
        "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
    }

    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        # 响应格式: {"input_tokens": N}
        return data.get("input_tokens", 0)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        raise LLMError(f"count_tokens 调用失败: {e}") from e


def call_m3(
    system: str,
    user: str,
    purpose: str,
    *,
    temperature: float = 0.85,
    max_tokens: int = 800,
    thinking_enabled: bool = False,
) -> str:
    """
    调用 MiniMax M3,返回纯文本响应。

    参数:
        system: system prompt (即 Anthropic 的 system 参数)
        user: user prompt (即 messages 里的一条 user 消息)
        purpose: 用途标签(写入日志),例如 "npc_dialogue:陈伯"
        temperature: 采样温度,对话/叙事偏高(0.8-1.0),决策/裁判偏低(0.3-0.6)
        max_tokens: 最大输出 token
        thinking_enabled: M3 默认开启 thinking;
                         对话/叙事场景必须关闭(省 token + 避免推理过程输出);
                         决策/裁判场景可开启(要质量)。

    失败时抛 LLMError。上层应捕获并降级到规则默认值。
    """
    if not ANTHROPIC_API_KEY:
        raise LLMError(
            "ANTHROPIC_API_KEY 未设置。请复制 .env.example 为 .env 并填入真实 key。"
        )

    url = f"{ANTHROPIC_BASE_URL}/v1/messages"
    headers = {
        "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }

    # 构建消息列表
    messages = []
    if system:
        # system 单独作为 system 参数传入,不在 messages 里
        pass
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": user}]
    })

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        payload["system"] = system

    # 注意：MiniMax-M3 不支持 thinking={"type":"disabled"}——一旦禁用会返回空 content。
    # 因此这里不再发送禁用参数（M3 始终带 thinking）。thinking 块由 _extract_content
    # 自动过滤，只取 text 块。thinking_enabled 参数保留以兼容调用方，但对 M3 不起禁用作用。
    _ = thinking_enabled  # 兼容旧调用签名，当前无操作

    last_err: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=TIMEOUT_SEC) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            elapsed = time.perf_counter() - t0

            # 提取文本内容
            content = _extract_content(data)
            # 从响应中取 token 用量(更精确)
            usage = data.get("usage", {})
            in_tokens = usage.get("input_tokens", 0)
            out_tokens = usage.get("output_tokens", 0)

            _log_call(
                {
                    "ts": time.time(),
                    "purpose": purpose,
                    "model": MODEL,
                    "attempt": attempt,
                    "elapsed_sec": round(elapsed, 3),
                    "in_tokens": in_tokens,
                    "out_tokens": out_tokens,
                    "thinking_disabled": not thinking_enabled,
                    "ok": True,
                }
            )
            return content

        except (httpx.HTTPError, ValueError, KeyError) as e:
            elapsed = time.perf_counter() - t0
            last_err = e
            _log_call(
                {
                    "ts": time.time(),
                    "purpose": purpose,
                    "model": MODEL,
                    "attempt": attempt,
                    "elapsed_sec": round(elapsed, 3),
                    "thinking_disabled": not thinking_enabled,
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)

    raise LLMError(f"M3 调用失败({MAX_RETRIES + 1} 次): {last_err}") from last_err


def _extract_content(data: dict[str, Any]) -> str:
    """
    从 Anthropic 响应中提取文本内容。

    响应格式:
    {
      "content": [
        {"type": "text", "text": "..."},
        {"type": "thinking", "thinking": "..."}  (如果 thinking 未关闭)
      ]
    }
    """
    try:
        content_blocks = data["content"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"响应中无 content 字段: {data}") from e

    if not isinstance(content_blocks, list):
        raise ValueError(f"content 不是列表: {data}")

    # 只取 type="text" 的 block。thinking 块是模型的内部推理，绝不能返回给玩家。
    text_parts = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    result = "".join(text_parts).strip()
    if not result:
        # 没有 text 块通常是 max_tokens 太小，被 thinking 吃光、回复被截断。
        # 抛错触发上层重试/降级，绝不把 thinking 推理泄漏给玩家。
        raise ValueError(
            f"响应无 text 块（疑似 max_tokens 太小，thinking 占满）: usage={data.get('usage')}"
        )
    return result
