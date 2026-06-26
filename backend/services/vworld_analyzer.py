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


# ── WMTS 타일 취득 (위성 영상) ────────────────────────────────────────────────

def _lat_lng_to_tile(lat: float, lng: float, zoom: int) -> tuple:
    """WGS84 → Slippy Map 타일 좌표 (Web Mercator)."""
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


async def _fetch_wmts_satellite(
    lat: float, lng: float, api_key: str, domain: str = "",
    zoom: int = 16, grid: int = 3,
) -> bytes:
    """VWorld WMTS 위성 타일 grid×grid 합성 → JPEG bytes.

    URL: https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{z}/{y}/{x}.jpeg
    zoom 16 기준 타일 1장 ≈ 488m (위도 37°), 3×3 그리드 ≈ 1.4km 시야.
    """
    cx, cy = _lat_lng_to_tile(lat, lng, zoom)
    half = grid // 2
    tile_size = 256

    async def _get_tile(tx: int, ty: int) -> bytes | None:
        url = f"https://api.vworld.kr/req/wmts/1.0.0/{api_key}/Satellite/{zoom}/{ty}/{tx}.jpeg"
        params = {"domain": domain} if domain else {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params)
            if r.is_success and "image" in r.headers.get("content-type", ""):
                return r.content
            logger.warning("WMTS tile (%d/%d/%d) 실패: %s", zoom, ty, tx, r.status_code)
        except Exception as e:
            logger.warning("WMTS tile (%d/%d/%d) 오류: %s", zoom, ty, tx, e)
        return None

    coords = [(cx + dx, cy + dy) for dy in range(-half, half + 1) for dx in range(-half, half + 1)]
    tiles = await asyncio.gather(*[_get_tile(tx, ty) for tx, ty in coords])

    img = Image.new("RGB", (grid * tile_size, grid * tile_size), (180, 180, 180))
    for idx, tile_bytes in enumerate(tiles):
        if tile_bytes:
            gx, gy = idx % grid, idx // grid
            img.paste(Image.open(io.BytesIO(tile_bytes)).convert("RGB"), (gx * tile_size, gy * tile_size))

    if all(t is None for t in tiles):
        raise RuntimeError("VWorld WMTS 위성 타일을 하나도 가져오지 못했습니다. API 키·도메인을 확인하세요.")

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


# ── Claude vision 대지 분석 ───────────────────────────────────────────────────

_SITE_ANALYSIS_PROMPT = """이 이미지는 '{address}' 일대의 VWorld 위성사진입니다 (3×3 타일 합성).
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

    # 2. 위성 이미지 취득 (WMTS 타일, 3×3 그리드)
    composed = await _fetch_wmts_satellite(lat, lng, vworld_key, vworld_domain)
    logger.info("WMTS satellite OK: %d bytes", len(composed))

    # 3. 이미지 저장 (옵션)
    if save_image_path:
        save_image_path.write_bytes(composed)
        logger.info("site image saved: %s", save_image_path)

    # 4. Vision 분석
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
