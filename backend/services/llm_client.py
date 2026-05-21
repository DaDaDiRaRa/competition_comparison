import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


def call_messages(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str | list,
    messages: list[dict],
) -> str:
    """Anthropic Messages API 직접 호출 (httpx). 응답의 첫 번째 text block 반환.

    Prompt caching: `messages`의 content block 또는 `system` 블록에
    `cache_control: {"type": "ephemeral"}` 마킹 시 자동 적용 (5분 TTL, 90% 할인).
    캐시 통계는 logger.info()로 출력 (cache_creation, cache_read 토큰).
    """
    headers = {
        "x-api-key": settings.api_key,
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    with httpx.Client(timeout=900) as client:
        response = client.post(_API_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        usage = data.get("usage", {})
        cache_create = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        if cache_create or cache_read:
            logger.info(
                "[cache] model=%s input=%d cache_write=%d cache_read=%d output=%d",
                model,
                usage.get("input_tokens", 0),
                cache_create,
                cache_read,
                usage.get("output_tokens", 0),
            )

        return data["content"][0]["text"]
