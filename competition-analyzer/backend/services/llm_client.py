import httpx
from config import settings

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


def call_messages(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str,
    messages: list[dict],
) -> str:
    """Anthropic Messages API 직접 호출 (httpx). 응답의 첫 번째 text block 반환."""
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
        return response.json()["content"][0]["text"]
