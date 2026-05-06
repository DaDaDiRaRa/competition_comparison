import base64
import json
from pathlib import Path


def encode_image(image_path: Path) -> tuple[str, str]:
    ext = image_path.suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def parse_json_response(text: str) -> dict:
    text = text.strip()
    for delim in ("```json", "```"):
        if delim in text:
            text = text.split(delim)[1].split("```")[0].strip()
            break
    return json.loads(text)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
