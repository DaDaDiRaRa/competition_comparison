"""
vworld_analyzer 결정론 헬퍼 테스트 — 네트워크/LLM 의존 없음.

핵심 보호: 지적도 WMS 오버레이를 위성 WMTS 타일에 픽셀 정렬하는 bbox 기하.
틀어지면 필지 경계가 위성과 어긋나 합성이 무의미해진다.
"""
import math

from services.vworld_analyzer import (
    _lat_lng_to_tile,
    _lat_lng_to_3857,
    _tile_grid_bbox_3857,
    _geom_outer_rings,
    _project_ring_norm,
    _WORLD_3857,
    _DEFAULT_ZOOM,
    _CADASTRAL_SPAN_M,
    _CADASTRAL_REQ_PX,
)


def _tile_left_top_3857(x, y, z):
    """단일 타일 (x,y) 의 좌상단 3857 좌표 (독립 재계산, 헬퍼 검증용)."""
    ts = 2 * _WORLD_3857 / (2 ** z)
    return (-_WORLD_3857 + x * ts, _WORLD_3857 - y * ts)


class TestTileGridBbox:

    def test_single_tile_matches_web_mercator(self):
        # grid=1 이면 타일 (cx,cy) 한 장의 정확한 경계여야 한다
        z = 17
        cx, cy = 55869, 25389
        minx, miny, maxx, maxy = _tile_grid_bbox_3857(cx, cy, z, 1)
        lt = _tile_left_top_3857(cx, cy, z)
        rb = _tile_left_top_3857(cx + 1, cy + 1, z)
        assert math.isclose(minx, lt[0], rel_tol=1e-9)
        assert math.isclose(maxy, lt[1], rel_tol=1e-9)
        assert math.isclose(maxx, rb[0], rel_tol=1e-9)
        assert math.isclose(miny, rb[1], rel_tol=1e-9)

    def test_3x3_spans_three_tiles(self):
        z = 17
        ts = 2 * _WORLD_3857 / (2 ** z)
        minx, miny, maxx, maxy = _tile_grid_bbox_3857(100, 100, z, 3)
        assert math.isclose(maxx - minx, 3 * ts, rel_tol=1e-9)
        assert math.isclose(maxy - miny, 3 * ts, rel_tol=1e-9)

    def test_bbox_ordering(self):
        minx, miny, maxx, maxy = _tile_grid_bbox_3857(12345, 6789, 17, 3)
        assert minx < maxx and miny < maxy

    def test_center_tile_contains_point(self):
        # 점이 속한 타일을 중심으로 한 3×3 bbox 는 그 점을 반드시 포함한다
        lat, lng = 37.5219, 126.9018
        z = _DEFAULT_ZOOM
        cx, cy = _lat_lng_to_tile(lat, lng, z)
        minx, miny, maxx, maxy = _tile_grid_bbox_3857(cx, cy, z, 3)
        px = lng * _WORLD_3857 / 180
        py = math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) * _WORLD_3857 / math.pi
        assert minx < px < maxx
        assert miny < py < maxy


class TestHybridCadastralGeometry:
    """광역 위성(줌16) 중앙에 지적도 sub-bbox 를 비례 합성하는 기하."""

    def test_point_3857_roundtrip_with_tile_bounds(self):
        # _lat_lng_to_3857 점이 그 점이 속한 줌16 타일의 3857 경계 안에 있어야 한다
        lat, lng = 37.5219, 126.9018
        px, py = _lat_lng_to_3857(lat, lng)
        minx, miny, maxx, maxy = _tile_grid_bbox_3857(*_lat_lng_to_tile(lat, lng, 16), 16, 1)
        assert minx <= px <= maxx
        assert miny <= py <= maxy

    def test_cadastral_subbbox_within_wide(self):
        # 중앙 sub-bbox(_CADASTRAL_SPAN_M) 는 줌16 광역 3×3 bbox 안에 완전히 들어가야
        # 합성 시 프레임이 이미지 밖으로 안 나간다 (점이 중앙 타일에 있다는 전제)
        lat, lng = 37.5219, 126.9018
        cx, cy = _lat_lng_to_tile(lat, lng, _DEFAULT_ZOOM)
        wminx, wminy, wmaxx, wmaxy = _tile_grid_bbox_3857(cx, cy, _DEFAULT_ZOOM, 3)
        px, py = _lat_lng_to_3857(lat, lng)
        s = _CADASTRAL_SPAN_M
        assert wminx <= px - s / 2 and px + s / 2 <= wmaxx
        assert wminy <= py - s / 2 and py + s / 2 <= wmaxy

    def test_cadastral_request_scale_under_threshold(self):
        # 핵심: 연속지적도 렌더 임계는 m/px. 고해상 요청이 ≲1.3 m/px 여야 그려진다.
        m_per_px = _CADASTRAL_SPAN_M / _CADASTRAL_REQ_PX
        assert m_per_px < 1.5, f"{m_per_px:.2f} m/px 는 지적도 렌더 임계 초과"

    def test_default_zoom_is_wide(self):
        # 광역 맥락 확보용으로 줌16(3×3 ≈ 1.8km)을 유지 (지적도는 중앙 합성으로 별도 처리)
        minx, _, maxx, _ = _tile_grid_bbox_3857(55869, 25389, _DEFAULT_ZOOM, 3)
        assert maxx - minx > 1500


class TestParcelPolygonProjection:
    """연속지적도 필지 폴리곤 → 이미지 정규화 투영 (2D데이터 API GetFeature 소비, 네트워크 0)."""

    def test_geom_outer_rings_polygon(self):
        ring = [[126.9, 37.5], [126.91, 37.5], [126.91, 37.51], [126.9, 37.5]]
        assert _geom_outer_rings({"type": "Polygon", "coordinates": [ring, [[0, 0]]]}) == [ring]

    def test_geom_outer_rings_multipolygon(self):
        r1 = [[126.9, 37.5], [126.91, 37.5], [126.91, 37.51]]
        r2 = [[126.8, 37.4], [126.81, 37.4], [126.81, 37.41]]
        got = _geom_outer_rings({"type": "MultiPolygon", "coordinates": [[r1], [r2]]})
        assert got == [r1, r2]

    def test_geom_outer_rings_unknown_empty(self):
        assert _geom_outer_rings({"type": "Point", "coordinates": [1, 2]}) == []

    def test_projection_center_point_near_half(self):
        # 지오코딩 좌표 부근 필지 → 이미지 정규화 좌표는 0~1 안, 중앙 근처
        lat, lng = 37.5665, 126.9780
        cx, cy = _lat_lng_to_tile(lat, lng, _DEFAULT_ZOOM)
        bbox = _tile_grid_bbox_3857(cx, cy, _DEFAULT_ZOOM, 3)
        ring = [[lng - 0.0006, lat - 0.0004], [lng + 0.0006, lat - 0.0004],
                [lng + 0.0006, lat + 0.0004], [lng - 0.0006, lat + 0.0004]]
        norm = _project_ring_norm(ring, bbox)
        assert len(norm) == 4
        for nx, ny in norm:
            assert 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0     # 이미지 안
            assert 0.3 < nx < 0.7 and 0.3 < ny < 0.75         # 중앙 부근(타일 오프셋 허용)

    def test_projection_y_inverted(self):
        # 위도가 클수록(북쪽) 이미지 y 는 작아야(위쪽) 한다
        lat, lng = 37.5, 127.0
        cx, cy = _lat_lng_to_tile(lat, lng, _DEFAULT_ZOOM)
        bbox = _tile_grid_bbox_3857(cx, cy, _DEFAULT_ZOOM, 3)
        south = _project_ring_norm([[lng, lat - 0.001]], bbox)[0]
        north = _project_ring_norm([[lng, lat + 0.001]], bbox)[0]
        assert north[1] < south[1]                            # 북쪽이 위(작은 y)
