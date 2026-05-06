import base64
import json
from pathlib import Path


def encode_pdf(pdf_path: Path) -> str:
    """PDF 파일을 base64로 인코딩"""
    with open(pdf_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data


def parse_json_response(text: str) -> dict:
    text = text.strip()
    for delim in ("```json", "```"):
        if delim in text:
            text = text.split(delim)[1].split("```")[0].strip()
            break
    return json.loads(text)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
