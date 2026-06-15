"""
run_pipeline.py — 백엔드 추출 파이프라인 래퍼

⚠️  LLM 비용 발생 지점
  1. classify_all_pages()  → claude-haiku-4-5  (72 DPI, 5페이지 배치)
  2. extract_pdf()         → claude-sonnet-4-6 (120 DPI, 타입별 프롬프트)

  추정 비용 (페이지 40장 PDF 기준):
    분류  ~$0.02  (Haiku 배치 × 8회)
    추출  ~$0.25  (Sonnet, 이미지 토큰 포함)
    합계  ~$0.27 / PDF

  25 PDFs 기준 총 예상 비용: ~$6.75
  --skip-extraction 옵션으로 캐시만 사용 시 LLM 비용 없음.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# backend 모듈 import 경로 삽입
_BACKEND = Path(__file__).parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _ensure_api_key():
    """ANTHROPIC_API_KEY 환경변수 확인. 없으면 app_settings.json에서 읽기 시도."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    settings_path = _BACKEND / "app_settings.json"
    if settings_path.exists():
        try:
            s = json.loads(settings_path.read_text(encoding="utf-8"))
            key = s.get("anthropic_api_key", "")
            if key:
                os.environ["ANTHROPIC_API_KEY"] = key
                return
        except Exception:
            pass
    raise RuntimeError(
        "ANTHROPIC_API_KEY가 설정되지 않았습니다.\n"
        "환경변수로 설정하거나 app_settings.json에 추가하세요.\n"
        "LLM 없이 실행하려면 --skip-extraction 옵션을 사용하세요."
    )


def run_extraction(pdf_path: Path, facility_type: str) -> dict:
    """
    PDF 한 건 전체 파이프라인 실행 후 결과 dict 반환.
    ⚠️ LLM 호출: classify_all_pages (Haiku) + extract_pdf (Sonnet)
    """
    _ensure_api_key()

    from services.page_classifier import classify_all_pages
    from services.data_extractor import extract_pdf, merge_extracted_data

    async def _run() -> dict:
        page_map = await classify_all_pages(pdf_path)
        extractions = await extract_pdf(pdf_path, page_map=page_map)
        merged = merge_extracted_data(page_map, extractions)
        merged["page_map"] = page_map
        merged["facility_type"] = facility_type
        return merged

    return asyncio.run(_run())


def get_or_extract(
    pdf_path: Path,
    facility_type: str,
    cache_path: Path,
    force: bool = False,
) -> dict:
    """
    캐시 있으면 로드, 없으면 추출 후 저장.

    force=True  → 캐시 무시하고 재추출  ⚠️ LLM 비용 발생
    force=False → 캐시 있으면 LLM 비용 없음
    """
    if not force and cache_path.exists():
        print(f"    [cache] {cache_path.name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    print(f"    [LLM ⚠️] {pdf_path.name} ({facility_type})")
    result = run_extraction(pdf_path, facility_type)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    [saved] {cache_path.name}")
    return result
