"""
VWorld 국토부 공간정보 오픈플랫폼 — 대지·맥락 분석

흐름: 주소 → 지오코딩 → WMTS 위성 타일(3×3) + WMS 연속지적도 오버레이 합성
      → Claude vision 판독.

위성은 WMTS 타일(`/req/wmts/.../Satellite/...`)로만 서빙(WMS GetMap 미지원).
지적도는 WMS GetMap(`lp_pa_cbnd_bonbun,bubun`, EPSG:3857)으로 위성 bbox 에 정렬해
합성 — 단, 연속지적도는 스케일 임계(≈1km span)가 있어 줌17 이하에서만 렌더된다.
"""
import asyncio
import base64
import io
import logging
import math
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from services.llm_client import call_messages
from services.utils import parse_json_response

logger = logging.getLogger(__name__)

_VWORLD_BASE = "https://api.vworld.kr/req"
# 위성+지적도 합성 시 1도 ≈ 111km 기준 반경
_DEFAULT_RADIUS_M = 500

# WMTS 기본 줌 16 = 3×3 약 1.8km 광역 맥락(하천·산·간선·도시조직).
_DEFAULT_ZOOM = 16
_TILE_GRID = 3
_WORLD_3857 = 20037508.342789244  # Web Mercator 반세계 (m)

# 하이브리드 단일 이미지: 광역 위성 위 **중앙**에만 연속지적도(필지경계+지번)를 합성.
# VWorld 연속지적도 WMS 레이어 (본번·부번). 구 코드 lp_pa_cn_A 는 오타라 LayerNotDefined.
_CADASTRAL_LAYERS = "lp_pa_cbnd_bonbun,lp_pa_cbnd_bubun"
# 지적도 sub-bbox span(m). 연속지적도는 스케일 임계가 **m/px**(절대 span 아님) →
# 작은 영역을 고해상으로 요청(_CADASTRAL_REQ_PX)해야 렌더, 그 뒤 비례 축소해 광역에 붙임.
_CADASTRAL_SPAN_M = 900
_CADASTRAL_REQ_PX = 768


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


def _lat_lng_to_3857(lat: float, lng: float) -> tuple:
    """WGS84 → EPSG:3857 (Web Mercator) 미터 좌표 (점 위치, 지적도 정렬용)."""
    x = lng * _WORLD_3857 / 180
    y = math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) * _WORLD_3857 / math.pi
    return x, y


def _tile_grid_bbox_3857(cx: int, cy: int, zoom: int, grid: int) -> tuple:
    """grid×grid WMTS 타일 묶음의 EPSG:3857 extent (minx, miny, maxx, maxy).

    WMS 오버레이를 위성 타일과 픽셀 단위로 정렬하기 위한 정확한 경계.
    """
    half = grid // 2
    ts = 2 * _WORLD_3857 / (2 ** zoom)
    minx = -_WORLD_3857 + (cx - half) * ts
    maxx = -_WORLD_3857 + (cx + half + 1) * ts
    maxy = _WORLD_3857 - (cy - half) * ts
    miny = _WORLD_3857 - (cy + half + 1) * ts
    return minx, miny, maxx, maxy


# ── 필지 경계 폴리곤 (2D데이터 API GetFeature) → 이미지 정규화 좌표 ──────────────────
# 연속지적도 필지 레이어. 위성 이미지가 bbox_3857 을 정확히 커버하므로, 필지 폴리곤(WGS84)
# 을 3857 로 변환 후 이미지 0~1 정규화 좌표로 투영해 저장 → 렌더러가 위성 위에 실제 대지경계
# 를 그린다. (지적도 래스터선과 달리 '이 대지'만 벡터로 강조 가능.)
_PARCEL_LAYER = "LP_PA_CBND_BUBUN"


def _geom_outer_rings(geom: dict) -> list:
    """GeoJSON geometry → 외곽 링 리스트 (각 링 = [[lng,lat],...]). Polygon/MultiPolygon 처리."""
    t = geom.get("type")
    c = geom.get("coordinates") or []
    if t == "Polygon":
        return [c[0]] if c else []
    if t == "MultiPolygon":
        return [poly[0] for poly in c if poly]
    return []


def _project_ring_norm(ring: list, bbox: tuple) -> list:
    """WGS84 링([[lng,lat],...]) → 이미지 정규화 좌표([[nx,ny],...], 0~1). y 는 상단이 maxy."""
    minx, miny, maxx, maxy = bbox
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    out = []
    for pt in ring:
        try:
            x, y = _lat_lng_to_3857(float(pt[1]), float(pt[0]))
        except (TypeError, ValueError, IndexError):
            continue
        out.append([round((x - minx) / w, 4), round((maxy - y) / h, 4)])
    return out


async def _fetch_parcel_polygon(lat: float, lng: float, api_key: str, bbox: tuple,
                                domain: str = "") -> list | None:
    """지오코딩 좌표의 연속지적도 필지 폴리곤 → 이미지 정규화 링 리스트. 실패·미지원 시 None(graceful).

    2D데이터 API GetFeature (VWorld 인증키에 '2D데이터 API' 활성 필요 — 미활성 시 status!=OK → None).
    """
    url = f"{_VWORLD_BASE}/data"
    params = {
        "service": "data", "request": "GetFeature", "data": _PARCEL_LAYER,
        "key": api_key, "geomFilter": f"POINT({lng} {lat})", "geometry": "true",
        "crs": "EPSG:4326", "format": "json", "size": "1",
    }
    if domain:
        params["domain"] = domain
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url, params=params)
        data = r.json()
        resp = data.get("response") or {}
        if resp.get("status") != "OK":
            logger.info("필지 폴리곤 status=%s (2D데이터 API 미활성일 수 있음)", resp.get("status"))
            return None
        feats = (((resp.get("result") or {}).get("featureCollection") or {}).get("features") or [])
        if not feats:
            return None
        rings = _geom_outer_rings(feats[0].get("geometry") or {})
        norm = [_project_ring_norm(rg, bbox) for rg in rings if rg]
        norm = [n for n in norm if len(n) >= 3]
        return norm or None
    except Exception as e:
        logger.warning("VWorld 필지 폴리곤 취득 실패 (비치명): %s", e)
        return None


async def _fetch_wmts_satellite(
    lat: float, lng: float, api_key: str, domain: str = "",
    zoom: int = _DEFAULT_ZOOM, grid: int = _TILE_GRID,
) -> tuple:
    """VWorld WMTS 위성 타일 grid×grid 합성 → (RGB Image, bbox_3857).

    URL: https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{z}/{y}/{x}.jpeg
    기본 zoom 16 (_DEFAULT_ZOOM): 타일 1장 ≈ 610m (위도 37°), 3×3 그리드 ≈ 1.8km 시야.
    bbox_3857 은 지적도 WMS 오버레이 정렬용 (지적도는 중앙에만 합성).
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

    return img, _tile_grid_bbox_3857(cx, cy, zoom, grid)


# ── WMS 지적도 오버레이 (연속지적도) ──────────────────────────────────────────

async def _fetch_cadastral_overlay(
    bbox_3857: tuple, size: int, api_key: str, domain: str = "",
) -> "Image.Image | None":
    """주어진 bbox 의 VWorld 연속지적도(필지경계+지번) → 반투명 RGBA.

    스케일 임계는 **m/px**(절대 span 아님): 좁은 영역(_CADASTRAL_SPAN_M)을 고해상
    (_CADASTRAL_REQ_PX)으로 요청해야 렌더된다. 빈 타일(alpha 전부 0)·실패는 None
    반환 — 비치명, 위성 단독으로 진행.
    """
    minx, miny, maxx, maxy = bbox_3857
    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0",
        "LAYERS": _CADASTRAL_LAYERS, "STYLES": "",
        "CRS": "EPSG:3857", "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(size), "HEIGHT": str(size),
        "FORMAT": "image/png", "TRANSPARENT": "true", "KEY": api_key,
    }
    if domain:
        params["DOMAIN"] = domain
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{_VWORLD_BASE}/wms", params=params)
        ctype = r.headers.get("content-type", "")
        if not (r.is_success and "image" in ctype):
            logger.warning("지적도 WMS 실패: %s %s %s", r.status_code, ctype, r.text[:160])
            return None
        overlay = Image.open(io.BytesIO(r.content)).convert("RGBA")
        # 스케일 임계 미달 시 alpha 전부 0(전 투명) → 합성 무의미하니 None
        if overlay.getchannel("A").getextrema()[1] == 0:
            logger.info("지적도 WMS 빈 타일(스케일 임계). 위성 단독.")
            return None
        return overlay
    except Exception as e:
        logger.warning("지적도 WMS 오류: %s", e)
        return None


def _cadastral_sub_bbox(lat: float, lng: float) -> tuple:
    """점(lat,lng) 중심의 지적도 sub-bbox(EPSG:3857). 위성과 **병렬** 요청 가능하도록
    이미지 없이 좌표만으로 계산 (Fix 4)."""
    px, py = _lat_lng_to_3857(lat, lng)
    s = _CADASTRAL_SPAN_M
    return (px - s / 2, py - s / 2, px + s / 2, py + s / 2)


def _paste_cadastral(sat_img: "Image.Image", overlay, sub: tuple, wide_bbox: tuple) -> tuple:
    """이미 받아온 지적도 overlay 를 광역 위성(sat_img) **중앙**에 합성 → (RGB Image, bool).

    좁은 sub-bbox 를 광역 비율로 축소해 정렬. overlay None·정렬 불가·PIL 에러면 위성 단독
    (has_cadastral=False) — 네트워크 없는 순수 픽셀 연산 (페치는 호출측이 병렬 수행).
    """
    if overlay is None:
        return sat_img, False
    wminx, wminy, wmaxx, wmaxy = wide_bbox
    s = sub[2] - sub[0]
    wide_px = sat_img.size[0]
    ov_px = max(1, round(wide_px * s / (wmaxx - wminx)))
    # sub-bbox 좌상단(작은 x, 큰 y)을 광역 픽셀 좌표로 매핑
    ox = round((sub[0] - wminx) / (wmaxx - wminx) * wide_px)
    oy = round((wmaxy - sub[3]) / (wmaxy - wminy) * wide_px)

    # 현재 상수(sub 900m < wide 1.8km, 점은 중앙 타일 내)면 항상 in-bounds 지만,
    # 상수가 바뀌면 offset 이 범위를 벗어나 alpha_composite 가 ValueError 로 죽는다.
    # docstring 의 '비치명' 약속을 지키도록 경계 가드 + try/except (실패 시 위성 단독).
    if ox < 0 or oy < 0 or ox + ov_px > wide_px or oy + ov_px > wide_px:
        logger.warning("지적도 sub-bbox 가 광역 범위 이탈 (off=%d,%d ov=%d). 위성 단독.", ox, oy, ov_px)
        return sat_img, False
    try:
        overlay = overlay.resize((ov_px, ov_px), Image.LANCZOS)
        base = sat_img.convert("RGBA")
        base.alpha_composite(overlay, (ox, oy))
        # 지적 데이터 구간임을 명시하는 흰 프레임
        ImageDraw.Draw(base).rectangle(
            [ox, oy, ox + ov_px - 1, oy + ov_px - 1], outline=(255, 255, 255, 200), width=2,
        )
        return base.convert("RGB"), True
    except Exception as e:
        logger.warning("지적도 합성 실패 (비치명): %s", e)
        return sat_img, False


# ── Claude vision 대지 분석 ───────────────────────────────────────────────────

_SITE_ANALYSIS_PROMPT = """이 이미지는 '{address}' 일대의 VWorld 위성사진입니다 (3×3 타일 합성).
좌표: 위도 {lat:.5f}, 경도 {lng:.5f} | 반경 약 {radius_m}m.{cadastral_note}

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


_CADASTRAL_NOTE = (
    "\n이미지 **중앙의 흰 사각 프레임 안**에는 연속지적도가 합성되어 있습니다 "
    "— 주황색 선=필지 경계, 흰색 숫자=지번. 대상 부지는 이 중앙 구간에 있으니, "
    "그 필지 경계로 대상지의 형상·경계·접도와 인접 필지 분할/합필을 판독하세요. "
    "프레임 바깥(가장자리)은 광역 맥락용입니다."
)


async def _vision_analyze(
    image_bytes: bytes, address: str, lat: float, lng: float,
    radius_m: int, model: str = "claude-sonnet-4-6", has_cadastral: bool = False,
) -> dict:
    """합성 이미지 → Claude vision → 대지 분석 dict."""
    img_b64 = base64.standard_b64encode(image_bytes).decode()
    # JPEG 출력이므로 media_type은 image/jpeg
    media_type = "image/jpeg"

    prompt_text = _SITE_ANALYSIS_PROMPT.format(
        address=address, lat=lat, lng=lng, radius_m=radius_m,
        cadastral_note=_CADASTRAL_NOTE if has_cadastral else "",
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
    with_cadastral: bool = True,
) -> dict:
    """주소 → 분석 결과 dict.

    Returns:
        address_input, matched_address, lat, lng, radius_m,
        analysis (dict), has_cadastral (bool), image_jpeg_b64 (str, 프리뷰용)
    """
    # 1. 지오코딩
    geo = await geocode(address, vworld_key)
    lat, lng = geo["lat"], geo["lng"]
    logger.info("geocode OK: %s → (%.5f, %.5f)", geo["matched"], lat, lng)

    # 2+3. 광역 위성(WMTS 9타일)과 지적도(WMS) 를 **동시 취득**(Fix 4) 후 중앙 합성.
    #   지적도 sub-bbox 는 점 좌표만으로 계산 → 위성 페치와 병렬 가능(네트워크 왕복 절감).
    sub = _cadastral_sub_bbox(lat, lng) if with_cadastral else None
    fetches = [_fetch_wmts_satellite(lat, lng, vworld_key, vworld_domain)]
    if sub is not None:
        fetches.append(_fetch_cadastral_overlay(sub, _CADASTRAL_REQ_PX, vworld_key, vworld_domain))
    results = await asyncio.gather(*fetches)

    sat_img, bbox = results[0]
    logger.info("WMTS satellite OK: %dx%d", *sat_img.size)
    # 실제 시야 반경 — 줌/그리드로 정해지므로 호출측 radius_m(기본 500)이 아니라 bbox 에서
    # 산출 (Web Mercator 왜곡 보정: ground ≈ 3857거리 × cos(lat)). vision 프롬프트가 거리를
    # 정확히 스케일하도록.
    view_radius_m = round((bbox[2] - bbox[0]) / 2 * math.cos(math.radians(lat)))

    has_cadastral = False
    if sub is not None:
        sat_img, has_cadastral = _paste_cadastral(sat_img, results[1], sub, bbox)
        if has_cadastral:
            logger.info("지적도 중앙 합성 완료 (하이브리드 단일)")

    out = io.BytesIO()
    sat_img.save(out, format="JPEG", quality=90)
    composed = out.getvalue()

    # 4. 이미지 저장 (옵션)
    if save_image_path:
        save_image_path.write_bytes(composed)
        logger.info("site image saved: %s", save_image_path)

    # 5. Vision 분석 + 필지 폴리곤 취득을 **동시** 실행(추가 지연 없음). 폴리곤은 graceful(None 가능).
    parcel_task = asyncio.create_task(
        _fetch_parcel_polygon(lat, lng, vworld_key, bbox, vworld_domain)
    )
    analysis = await _vision_analyze(
        composed, geo["matched"], lat, lng, view_radius_m, has_cadastral=has_cadastral,
    )
    parcel_norm = await parcel_task
    if parcel_norm:
        logger.info("필지 경계 폴리곤 취득: %d개 링", len(parcel_norm))

    return {
        "address_input": address,
        "matched_address": geo["matched"],
        "lat": lat,
        "lng": lng,
        "radius_m": view_radius_m,
        "analysis": analysis,
        "has_cadastral": has_cadastral,
        "parcel_norm": parcel_norm,      # 이미지 정규화 필지 경계(링 리스트) 또는 None
        "image_jpeg_b64": base64.standard_b64encode(composed).decode(),
    }
