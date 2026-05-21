import logging
import time
import httpx
from config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

# 재시도 대상 상태코드: Anthropic 서버 일시 장애(502/529) + 과부하(529)
_RETRYABLE_STATUS = {502, 503, 529}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # 초 (지수 백오프: 2s → 4s → 8s)


def call_messages(
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str | list,
    messages: list[dict],
) -> str:
    """Anthropic Messages API 직접 호출 (httpx). 응답의 첫 번째 text block 반환.

    재시도: 502/503/529 상태코드 또는 네트워크 타임아웃 시 지수 백오프로 최대 3회 재시도.
    Prompt caching: content block에 cache_control 마킹 시 자동 적용 (5분 TTL, 90% 할인).
    """
    api_key = settings.api_key
    if not api_key:
        raise ValueError("Anthropic API 키가 설정되지 않았습니다. 설정 탭에서 API 키를 입력해주세요.")

    headers = {
        "x-api-key": api_key,
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

    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=900) as client:
                response = client.post(_API_URL, headers=headers, json=body)

            if response.status_code in _RETRYABLE_STATUS:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "[retry] attempt=%d/%d status=%d — %.0fs 후 재시도",
                    attempt + 1, _MAX_RETRIES, response.status_code, delay,
                )
                time.sleep(delay)
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                continue

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

        except httpx.TimeoutException as e:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "[retry] attempt=%d/%d timeout — %.0fs 후 재시도",
                attempt + 1, _MAX_RETRIES, delay,
            )
            time.sleep(delay)
            last_exc = e
            continue

        except httpx.HTTPStatusError:
            # 4xx 등 재시도 불필요한 오류는 즉시 raise
            raise

    raise last_exc
