"""
VWorld 국토부 공간정보 오픈플랫폼 — 대지·맥락 분석

흐름: 주소 → 지오코딩 → WMS 위성+지적도 합성 이미지 → Claude vision 판독
"""
import asyncio
import base64
import io
import logging
import math
from pathlib import Path

import httpx
from PIL import Image

from services.llm_client import call_messages
from services.utils import parse_json_response

logger = logging.getLogger(__name__)

_VWORLD_BASE = "https://api.vworld.kr/req"
# 위성+지적도 합성 시 1도 ≈ 111km 기준 반경
_DEFAULT_RADIUS_M = 500


# ── 지오코딩 ──────────────────────────────────────────────────────────────────

async def geocode(address: str, api_key: str) -> dict:
    """주소(도로명 또는 지번) → WGS84 좌표.

    Returns: {"lat": float, "lng": float, "matched": str}
    """
    url = f"{_VWORLD_BASE}/address"
    for addr_type in ("ROAD", "PARCEL"):
        params = {
            "service": "address",
            "request": "getcoord",
            "crs": "EPSG:4326",
            "address": address,
            "type": addr_type,
            "format": "json",
            "errorformat": "json",
            "key": api_key,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        resp = r.json().get("response") or {}
        if resp.get("status") == "OK":
            result = resp.get("result") or {}
            point = result.get("point") or {}
            return {
                "lat": float(point["y"]),
                "lng": float(point["x"]),
                "matched": result.get("text", address),
            }
    raise RuntimeError(f"VWorld 지오코딩 실패: '{address}' — 주소를 찾을 수 없습니다. 더 자세한 주소로 재시도해주세요.")


# ── WMS 이미지 취득 ───────────────────────────────────────────────────────────

def _bbox(lat: float, lng: float, radius_m: int) -> str:
    """WMS 1.3.0 EPSG:4326 bbox 문자열 (minLat,minLng,maxLat,maxLng)."""
    lat_d = radius_m / 111_000
    lng_d = radius_m / (111_000 * abs(math.cos(math.radians(lat))))
    return f"{lat - lat_d},{lng - lng_d},{lat + lat_d},{lng + lng_d}"


async def _fetch_wms(
    lat: float, lng: float, api_key: str, domain: str,
    layers: str, radius_m: int = _DEFAULT_RADIUS_M,
    width: int = 800, height: int = 800,
) -> bytes:
    """VWorld WMS GetMap → PNG bytes."""
    params = {
        "service": "WMS",
        "request": "GetMap",
        "version": "1.3.0",
        "layers": layers,
        "styles": "",
        "CRS": "EPSG:4326",
        "bbox": _bbox(lat, lng, radius_m),
        "width": str(width),
        "height": str(height),
        "format": "image/png",
        "transparent": "true",
        "key": api_key,
    }
    if domain:
        params["domain"] = domain

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{_VWORLD_BASE}/wms", params=params)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    if "image" not in ct:
        import re as _re
        xml = r.text
        m = _re.search(r'<ServiceException[^>]*>(.*?)</ServiceException>', xml, _re.DOTALL)
        detail = m.group(1).strip() if m else xml[:800]
        raise RuntimeError(f"WMS 오류 (layer={layers}): {detail}")
    return r.content


def _compose(satellite_bytes: bytes, overlay_bytes: bytes, overlay_alpha: float = 0.55) -> bytes:
    """위성 이미지 위에 지적도 오버레이 합성 → PNG bytes."""
    sat = Image.open(io.BytesIO(satellite_bytes)).convert("RGBA")
    ov  = Image.open(io.BytesIO(overlay_bytes)).convert("RGBA")
    if sat.size != ov.size:
        ov = ov.resize(sat.size, Image.LANCZOS)
    r, g, b, a = ov.split()
    a = a.point(lambda x: int(x * overlay_alpha))
    ov = Image.merge("RGBA", (r, g, b, a))
    sat.alpha_composite(ov)
    out = io.BytesIO()
    # 배경 흰색으로 플래튼해 JPEG 호환
    sat_rgb = Image.new("RGB", sat.size, (255, 255, 255))
    sat_rgb.paste(sat, mask=sat.split()[3])
    sat_rgb.save(out, format="JPEG", quality=90)
    return out.getvalue()


def _satellite_only_jpeg(satellite_bytes: bytes) -> bytes:
    """위성 이미지 단독 → JPEG bytes (지적도 오버레이 없음)."""
    sat = Image.open(io.BytesIO(satellite_bytes)).convert("RGB")
    out = io.BytesIO()
    sat.save(out, format="JPEG", quality=90)
    return out.getvalue()


# ── Claude vision 대지 분석 ───────────────────────────────────────────────────

_SITE_ANALYSIS_PROMPT = """이 이미지는 '{address}' 일대의 위성사진 + 연속지적도 합성 이미지입니다.
좌표: 위도 {lat:.5f}, 경도 {lng:.5f} | 반경 약 {radius_m}m.

건축 공모 수주 전략 수립을 위해 아래를 분석해주세요.
위성사진에서 **직접 확인되는 것만** 서술. 확인 불가시 해당 항목에 "위성 확인 불가" 표기.

1. orientation: 대지 장변 방향, 남향 가능성, 형상 특이사항
2. road_access: 주요 접면 도로(방향·폭 추정), 코너 필지 여부, 주 보행 진입
3. surrounding_uses: 인접 건물 용도·밀도 (주거/상업/공공/녹지 등)
4. natural_assets: 산·하천·공원 등 조망·완충 자원, 대략적 거리
5. special_context: 랜드마크, 경관 민감지역, 일조/소음 리스크, 기타 특이사항
6. overall_summary: 수주 제안서에 바로 쓸 수 있는 대지 맥락 1~2문장 요약

JSON으로만 응답 (한국어):
{{
  "orientation": "...",
  "road_access": "...",
  "surrounding_uses": "...",
  "natural_assets": "...",
  "special_context": "...",
  "overall_summary": "...",
  "confidence": "high|medium|low",
  "caveats": ["..."]
}}"""


async def _vision_analyze(
    image_bytes: bytes, address: str, lat: float, lng: float,
    radius_m: int, model: str = "claude-sonnet-4-6",
) -> dict:
    """합성 이미지 → Claude vision → 대지 분석 dict."""
    img_b64 = base64.standard_b64encode(image_bytes).decode()
    # JPEG 출력이므로 media_type은 image/jpeg
    media_type = "image/jpeg"

    prompt_text = _SITE_ANALYSIS_PROMPT.format(
        address=address, lat=lat, lng=lng, radius_m=radius_m,
    )
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": img_b64},
            },
            {"type": "text", "text": prompt_text},
        ],
    }]

    text = await asyncio.to_thread(
        call_messages,
        model=model,
        messages=messages,
        max_tokens=1500,
        temperature=0,
        system="당신은 건축 설계·공모 전문가입니다. 위성사진과 지적도로 대지 맥락을 분석합니다.",
    )
    result = parse_json_response(text)
    if not isinstance(result, dict):
        raise RuntimeError(f"대지 분석 응답 파싱 실패: {text[:300]}")
    return result


# ── 전체 파이프라인 ────────────────────────────────────────────────────────────

async def run_site_analysis(
    address: str,
    vworld_key: str,
    vworld_domain: str = "",
    radius_m: int = _DEFAULT_RADIUS_M,
    save_image_path: Path | None = None,
) -> dict:
    """주소 → 분석 결과 dict.

    Returns:
        address_input, matched_address, lat, lng, radius_m,
        analysis (dict), image_jpeg_b64 (str, 프리뷰용)
    """
    # 1. 지오코딩
    geo = await geocode(address, vworld_key)
    lat, lng = geo["lat"], geo["lng"]
    logger.info("geocode OK: %s → (%.5f, %.5f)", geo["matched"], lat, lng)

    # 2. 위성 이미지 취득 (필수)
    sat_bytes = await _fetch_wms(lat, lng, vworld_key, vworld_domain, "Satellite", radius_m)

    # 3. 지적도 오버레이 (실패 시 위성 단독 사용)
    cad_bytes = None
    for cad_layer in ("lp_pa_cn_A", "LP_PA_CN_A", "lp_pa_cn_a"):
        try:
            cad_bytes = await _fetch_wms(lat, lng, vworld_key, vworld_domain, cad_layer, radius_m)
            logger.info("cadastral layer OK: %s", cad_layer)
            break
        except Exception as e:
            logger.warning("cadastral layer '%s' failed: %s", cad_layer, e)

    # 4. 합성 (Pillow) — 지적도 없으면 위성 단독 JPEG 변환
    if cad_bytes:
        composed = await asyncio.to_thread(_compose, sat_bytes, cad_bytes)
    else:
        logger.warning("지적도 오버레이 실패 — 위성 단독으로 분석 진행")
        composed = await asyncio.to_thread(_satellite_only_jpeg, sat_bytes)

    # 5. 이미지 저장 (옵션)
    if save_image_path:
        save_image_path.write_bytes(composed)
        logger.info("site image saved: %s", save_image_path)

    # 6. Vision 분석
    analysis = await _vision_analyze(composed, geo["matched"], lat, lng, radius_m)

    return {
        "address_input": address,
        "matched_address": geo["matched"],
        "lat": lat,
        "lng": lng,
        "radius_m": radius_m,
        "analysis": analysis,
        "image_jpeg_b64": base64.standard_b64encode(composed).decode(),
    }
