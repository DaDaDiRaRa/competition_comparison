"""
llm_client.py — Claude 호출 추상화 레이어

provider 설정값(api / sdk)에 따라 두 가지 경로로 분기:
  - api: anthropic SDK 직접 호출 (API 토큰 차감)
  - sdk: claude-agent-sdk 경유 호출 (Claude Code 구독 사용, claude login 필요)

기존 services/*.py는 anthropic.Anthropic().messages.create(...)를 직접 호출했으나,
이 모듈의 call_messages()로 래핑되어 provider만 바꾸면 동일 로직이 양쪽 모두에 동작.

응답 포맷은 항상 plain text (JSON 문자열 그대로) 반환 — 호출부의 parse_json_response가
바로 처리할 수 있도록 정규화.
"""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from pathlib import Path
from typing import Any

import anthropic

from config import settings


def call_messages(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str,
    messages: list[dict],
) -> str:
    """단일 진입점. settings.provider 값에 따라 분기.

    인자는 anthropic.messages.create()와 동일한 형태를 받음.
    반환값은 응답의 첫 번째 text block 문자열.
    """
    provider = settings.provider
    if provider == "sdk":
        return _call_via_sdk(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
    return _call_via_api(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages,
    )


def _call_via_api(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str,
    messages: list[dict],
) -> str:
    """기존 동작: anthropic SDK 직접 호출."""
    client = anthropic.Anthropic(api_key=settings.api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def _call_via_sdk(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str,
    messages: list[dict],
) -> str:
    """claude-agent-sdk 경유 호출. claude login으로 인증된 구독 사용.

    이미지 블록은 임시 파일로 저장 후 Claude Code의 Read 툴로 읽도록 경로 참조.
    호출 1회당 max_turns=3 이내에서 완료되도록 프롬프트 설계.
    """
    try:
        from claude_agent_sdk import (
            query,
            ClaudeAgentOptions,
            AssistantMessage,
            TextBlock,
        )
    except ImportError as e:
        raise RuntimeError(
            "claude-agent-sdk 패키지가 설치되어 있지 않습니다. "
            "pip install claude-agent-sdk 후 다시 시도하세요."
        ) from e

    prompt_str, temp_files = _flatten_messages_to_prompt(messages)

    try:
        options = ClaudeAgentOptions(
            model=model,
            system_prompt=system,
            allowed_tools=["Read"] if temp_files else [],
            max_turns=3 if temp_files else 1,
        )

        async def _run() -> str:
            text_parts: list[str] = []
            stop_reason: str | None = None
            async for message in query(prompt=prompt_str, options=options):
                if isinstance(message, AssistantMessage):
                    stop_reason = message.stop_reason
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                # ResultMessage.result는 수집하지 않음 — AssistantMessage와 중복되어
                # {json}{json} 형태가 되어 JSONDecodeError를 일으킬 수 있음
            if stop_reason == "max_tokens":
                raise RuntimeError(
                    "SDK 응답이 max_tokens 한도로 잘렸습니다. "
                    "app_settings.json에서 provider를 'api'로 변경하거나 제출작 수를 줄이세요."
                )
            return "".join(text_parts)

        return asyncio.run(_run())
    finally:
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass


def _flatten_messages_to_prompt(messages: list[dict]) -> tuple[str, list[str]]:
    """anthropic 형태의 messages를 SDK용 단일 문자열로 펼침.

    이미지 블록은 임시 파일에 저장 후 [image: <path>] 마커로 참조.
    Claude Code가 Read 툴로 읽도록 경로를 명시.
    """
    parts: list[str] = []
    temp_files: list[str] = []

    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue

        for block in content:
            btype = block.get("type")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "image":
                src = block.get("source", {})
                if src.get("type") == "base64":
                    data = src.get("data", "")
                    media = src.get("media_type", "image/png")
                    suffix = ".png" if media.endswith("png") else ".jpg"
                    try:
                        img_bytes = base64.b64decode(data)
                    except Exception:
                        continue
                    tf = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                    tf.write(img_bytes)
                    tf.close()
                    temp_files.append(tf.name)
                    parts.append(
                        f"[Image attached at: {tf.name} — read this file to view it]"
                    )

    return "\n\n".join(parts), temp_files
