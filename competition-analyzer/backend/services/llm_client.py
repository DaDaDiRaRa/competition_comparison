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
    """Claude API 호출. 응답의 첫 번째 text block 반환."""
    client = anthropic.Anthropic(api_key=settings.api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages,
    )
    return response.content[0].text
