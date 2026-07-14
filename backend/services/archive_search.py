"""아카이브 검색 서비스.

/data 하위 모든 경쟁공모의 _comparison.json + _meta.json을 재귀 탐색해
SQLite in-memory + FTS5로 인덱싱한다. 디스크 저장 없음, 읽기 전용 접근.

검색 두 가지:
- search_keyword(): FTS5 직접 매칭
- search_natural(): Claude로 자연어 → 키워드 추출 후 FTS5 매칭

인덱싱 필드: competition_id, facility_type, ranking, key_differentiators,
            winner_patterns, concept_keywords, gap_analysis_alignment

winner_patterns / concept_keywords는 _comparison.json의 winner_strengths에서 수집한다
(_patterns/{ft}.json은 시설유형 전체 평균이라 공모별 검색에 부적합).
"""

import json
import logging
import sqlite3
from pathlib import Path

from config import settings, facility_label
from services.llm_client import call_messages
from services.utils import parse_json_response

logger = logging.getLogger(__name__)

# BM25 컬럼 가중치 — archive_fts 8컬럼 순서와 정확히 일치해야 한다.
# 순서: competition_id, facility_type, ranking, key_differentiators,
#       winner_patterns, concept_keywords, gap_analysis_alignment, extra_meta
# 매칭이 더 의미있는 컬럼(시설유형·컨셉/차별화 키워드)을 우대, 식별자/정렬라벨은 낮게.
# 고정 상수(사용자 입력 아님) — SQL 문자열 보간 안전.
_BM25_WEIGHTS = "0.5, 2.0, 1.0, 1.5, 1.2, 1.5, 0.3, 1.0"

# 시설유형 동의어 — 사용자가 자연어로 쓰는 표현(시청·병원·아파트 등)이
# facility_type FTS 컬럼과 매칭되도록 영어 키 + 한국어 레이블 + 일반 호칭을 함께 저장한다.
# 수주 형태 동의어 — MyProjectMode의 procurement_type FTS 매칭용.
# 사용자가 "수의계약 했던 거", "턴키" 같은 구어체로 검색해도 정식 키와 매칭되도록.
PROCUREMENT_SYNONYMS = {
    "competition":  ["경쟁공모", "설계공모", "공모"],
    "negotiated":   ["수의계약", "수의"],
    "invited":      ["지명공모", "지명", "초청"],
    "turnkey":      ["턴키", "일괄입찰", "기술제안"],
    "private":      ["민간발주", "민간"],
    "other":        ["기타"],
}

# 사업 단계 동의어.
PHASE_SYNONYMS = {
    "planning":         ["기획", "기획설계"],
    "concept":          ["계획", "계획설계", "컨셉"],
    "basic_design":     ["기본설계", "기본"],
    "detailed_design":  ["실시설계", "실시"],
    "cm":               ["CM", "사업관리", "감리"],
}


FACILITY_SYNONYMS = {
    "public":         ["공공시설", "시청", "구청", "관공서", "청사", "도서관", "문화시설", "체육관"],
    "residential":    ["주거시설", "공동주택", "아파트", "단지", "주거"],
    "office":         ["업무시설", "오피스", "사옥", "복합업무"],
    "transport":      ["교통시설", "역사", "터미널", "환승센터", "철도역", "버스터미널"],
    "commercial":     ["상업시설", "쇼핑몰", "백화점", "마트", "상가"],
    "cultural":       ["문화시설", "공연장", "박물관", "미술관", "집회시설"],
    "hospitality":    ["숙박시설", "호텔", "리조트", "레저시설", "위락시설"],
    "education":      ["교육시설", "학교", "대학", "캠퍼스", "연구시설"],
    "masterplan":     ["마스터플랜", "도시계획", "단지계획", "종합계획"],
    "industrial":     ["산업시설", "공장", "물류센터", "산업단지"],
    "medical":        ["의료시설", "병원", "요양원", "재활센터", "보건소"],
    "mixed_use":      ["복합시설", "복합개발", "복합단지"],
    "reconstruction": ["재건축", "재개발", "정비사업"],
    "alternative":    ["대안설계", "리모델링"],
}


def _facility_index_text(facility_type: str) -> str:
    """facility_type FTS 컬럼 값 — 영어 키 + 한국어 레이블 + 동의어 공백 조인."""
    parts = [facility_type, facility_label(facility_type)]
    parts.extend(FACILITY_SYNONYMS.get(facility_type, []))
    return " ".join(p for p in parts if p)


def _collect_deep_search_text(comp_dir: Path) -> str:
    """경쟁공모 폴더 안의 submissions/*_deep.json 전체를 합쳐 FTS 검색 텍스트 생성.

    MyProjectMode 심층 분석에서 LLM이 생성한 concept_narrative + design_intent +
    key_differentiators + search_keywords를 모두 모아 한 문자열로 반환. 자연어
    검색의 핵심 매칭 소스.
    """
    sub_dir = comp_dir / "submissions"
    if not sub_dir.exists():
        return ""

    parts: list[str] = []
    for deep_path in sub_dir.glob("*_deep.json"):
        doc = _safe_read_json(deep_path)
        if not doc:
            continue
        deep = doc.get("deep") or doc
        if not isinstance(deep, dict):
            continue
        narrative = deep.get("concept_narrative")
        if narrative:
            parts.append(str(narrative))
        intent = deep.get("design_intent")
        if intent:
            parts.append(str(intent))
        for k in ("key_differentiators", "search_keywords", "improvement_points"):
            v = deep.get(k)
            if isinstance(v, list):
                parts.extend(str(x) for x in v if x)
    return " ".join(parts)


def _extra_meta_index_text(meta: dict) -> str:
    """_meta.json의 MyProject 상세 필드를 FTS extra_meta 컬럼용으로 직렬화.

    procurement_type/project_phase는 동의어까지 함께 펼쳐서 구어체 검색 매칭.
    tags/memo/partners/role 등 자유 텍스트는 그대로 공백 조인.
    """
    parts: list[str] = []

    proc = (meta.get("procurement_type") or "").strip()
    if proc:
        parts.append(proc)
        parts.extend(PROCUREMENT_SYNONYMS.get(proc, []))

    phase = (meta.get("project_phase") or "").strip()
    if phase:
        parts.append(phase)
        parts.extend(PHASE_SYNONYMS.get(phase, []))

    for k in ("role", "partners", "memo", "gross_floor_area", "floors", "units"):
        v = (meta.get(k) or "").strip() if isinstance(meta.get(k), str) else meta.get(k)
        if v:
            parts.append(str(v))

    tag_list = meta.get("tags") or []
    if isinstance(tag_list, list):
        parts.extend(str(t) for t in tag_list if t)
    elif isinstance(tag_list, str) and tag_list.strip():
        parts.append(tag_list.strip())

    return " ".join(parts)


def _build_facility_hint() -> str:
    """search_natural() 프롬프트용 시설유형 힌트 블록."""
    lines = []
    for key, synonyms in FACILITY_SYNONYMS.items():
        label = facility_label(key)
        sample = ", ".join(synonyms[:6])
        lines.append(f"- {label} ({sample})")
    return "\n".join(lines)


def _build_procurement_hint() -> str:
    """search_natural() 프롬프트용 수주 형태 힌트 블록."""
    lines = []
    for synonyms in PROCUREMENT_SYNONYMS.values():
        if synonyms:
            lines.append(f"- {synonyms[0]} (대표 표현)")
    return "\n".join(lines)


_FACILITY_HINT = _build_facility_hint()
_PROCUREMENT_HINT = _build_procurement_hint()


def _join_list(items, sep: str = " ") -> str:
    """리스트를 공백 구분 문자열로 합침. 문자열/dict 혼재 대응."""
    parts: list[str] = []
    for x in items or []:
        if isinstance(x, str):
            parts.append(x)
        elif isinstance(x, dict):
            parts.append(json.dumps(x, ensure_ascii=False))
        else:
            parts.append(str(x))
    return sep.join(parts)


def _safe_read_json(path: Path) -> dict | None:
    """JSON 파일을 안전하게 읽는다. 없거나 파싱 실패 시 None 반환."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[archive_search] 파일 읽기 실패: %s — %s", path, e)
        return None


def _fts_escape(token: str) -> str:
    """FTS5 큰따옴표 escape — 토큰 내부 `"` 를 `""`로 치환."""
    return token.replace('"', '""')


class ArchiveSearchIndex:
    """SQLite in-memory FTS5 인덱스. /data 하위 _comparison.json/_meta.json 재귀 탐색."""

    def __init__(self, base_path: Path | None = None):
        self.base_path: Path = Path(base_path) if base_path else settings.db_path
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._cards: dict[str, dict] = {}
        self._init_schema()

    def _init_schema(self):
        # trigram 토크나이저 우선 (한글 부분일치 강함, SQLite 3.34+ 필요)
        # 미지원 환경에서는 unicode61로 폴백.
        # extra_meta 컬럼: MyProjectMode 상세 메타(procurement_type, tags, memo, partners 등)
        # 를 공백 조인하여 자연어 검색에 활용. 경쟁공모는 빈 문자열로 인덱싱.
        try:
            self.conn.executescript("""
                CREATE VIRTUAL TABLE archive_fts USING fts5(
                    competition_id, facility_type, ranking,
                    key_differentiators, winner_patterns,
                    concept_keywords, gap_analysis_alignment,
                    extra_meta,
                    tokenize='trigram'
                );
            """)
        except sqlite3.OperationalError:
            self.conn.executescript("""
                CREATE VIRTUAL TABLE archive_fts USING fts5(
                    competition_id, facility_type, ranking,
                    key_differentiators, winner_patterns,
                    concept_keywords, gap_analysis_alignment,
                    extra_meta,
                    tokenize='unicode61'
                );
            """)
        self.conn.commit()

    def build(self) -> int:
        """모든 경쟁공모를 재귀 탐색해 인덱싱. Returns: 인덱싱된 카드 수."""
        if not self.base_path.exists():
            logger.warning("[archive_search] base_path 없음: %s", self.base_path)
            return 0

        count = 0

        for meta_path in self.base_path.glob("*/*/_meta.json"):
            comp_dir = meta_path.parent
            try:
                meta = _safe_read_json(meta_path)
                if not meta:
                    continue
                comp = _safe_read_json(comp_dir / "_comparison.json") or {}

                facility_type = meta.get("facility_type") or comp_dir.parent.name
                competition_id = meta.get("competition_id") or comp_dir.name

                # 공모별 당선 강점을 winner_patterns 겸 concept_keywords로 사용.
                # (시설유형 평균보다 해당 공모 고유 텍스트가 검색 정확도가 높음)
                winner_strengths = comp.get("winner_strengths", []) or []
                winner_patterns = winner_strengths
                concept_keywords = winner_strengths

                ranking = comp.get("ranking") or comp.get("blind_ranking") or []
                key_diff = comp.get("key_differentiators", []) or []
                gap = comp.get("gap_analysis", {}) or {}
                alignment = gap.get("alignment", "") or ""

                card = {
                    "competition_id": competition_id,
                    "facility_type": facility_type,
                    "ranking": ranking,
                    "gap_analysis": gap,
                    "key_differentiators": key_diff,
                    "winner_patterns": winner_patterns,
                    "meta": meta,
                }
                self._cards[competition_id] = card

                # 사용자 메타 + MyProject 심층 분석(있으면)을 합쳐 extra_meta로.
                extra_text = _extra_meta_index_text(meta)
                deep_text = _collect_deep_search_text(comp_dir)
                combined_extra = (extra_text + " " + deep_text).strip()

                self.conn.execute(
                    "INSERT INTO archive_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        competition_id,
                        _facility_index_text(facility_type),
                        _join_list(ranking),
                        _join_list(key_diff),
                        _join_list(winner_patterns),
                        _join_list(concept_keywords),
                        alignment,
                        combined_extra,
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("[archive_search] 인덱싱 스킵 %s — %s", comp_dir, e)
                continue

        self.conn.commit()
        logger.info("[archive_search] 인덱싱 완료 — %d개 공모 (base=%s)", count, self.base_path)
        return count

    def _ranked_match(self, fts_query: str, limit: int) -> list[dict]:
        """FTS5 MATCH 를 BM25 관련도순으로 실행 (best-first). bm25 미지원 시 무순 폴백.

        BM25 는 음수 점수(작을수록 더 관련)라 ORDER BY 오름차순이 곧 관련도순.
        컬럼 가중치(_BM25_WEIGHTS)로 시설유형·컨셉 키워드 매칭을 우대 — 무순 LIMIT 컷의
        핵심 결함(관련도 정렬 불가)을 해소.
        """
        try:
            rows = self.conn.execute(
                "SELECT competition_id FROM archive_fts WHERE archive_fts MATCH ? "
                f"ORDER BY bm25(archive_fts, {_BM25_WEIGHTS}) LIMIT ?",
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError as e:
            # bm25 미지원(구 SQLite) 등 → 무순 폴백 (기존 동작). 그래도 결과는 준다.
            logger.warning("[archive_search] BM25 정렬 실패 — 무순 폴백: %s — %s", fts_query, e)
            try:
                rows = self.conn.execute(
                    "SELECT competition_id FROM archive_fts WHERE archive_fts MATCH ? LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError as e2:
                logger.warning("[archive_search] FTS 쿼리 실패: %s — %s", fts_query, e2)
                return []
        return [self._cards[r["competition_id"]] for r in rows
                if r["competition_id"] in self._cards]

    def search_keyword(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 키워드 검색 — 따옴표로 감싼 phrase 매칭 (BM25 관련도순)."""
        q = (query or "").strip()
        if not q:
            return []
        return self._ranked_match(f'"{_fts_escape(q)}"', limit)

    def search_natural(self, query: str, limit: int = 10) -> list[dict]:
        """자연어 검색 — Claude로 의도 추출 후 FTS5 OR 매칭."""
        q = (query or "").strip()
        if not q:
            return []

        system = (
            "You convert Korean natural-language search queries about architectural design "
            "competitions into FTS5 keywords. Respond ONLY in the specified JSON format."
        )
        prompt = (
            "TASK: extract_search_keywords\n"
            "OUTPUT_FORMAT: json_only\n"
            "\n"
            f"USER_QUERY: {q}\n"
            "\n"
            "Extract 2-5 Korean keywords most relevant for searching across:\n"
            "- ranking (회사명)\n"
            "- key_differentiators (당선/낙선 분기 요인)\n"
            "- winner_patterns (당선작 반복 패턴)\n"
            "- concept_keywords (설계 컨셉 키워드)\n"
            "- facility_type (시설 카테고리)\n"
            "- gap_analysis_alignment (high/partial/low)\n"
            "- extra_meta (수주 형태/사업 단계/태그/메모 — 내 프로젝트만 보유)\n"
            "\n"
            "AVAILABLE_FACILITY_TYPES (정식 한국어 레이블 — 대표 동의어):\n"
            f"{_FACILITY_HINT}\n"
            "\n"
            "AVAILABLE_PROCUREMENT_TYPES (대표 표현):\n"
            f"{_PROCUREMENT_HINT}\n"
            "\n"
            "RULE: 쿼리에서 시설 카테고리가 언급되면 (예: 시청, 병원, 학교, 아파트),\n"
            "해당 정식 한국어 레이블(예: 공공시설, 의료시설, 교육시설, 주거시설)을\n"
            "키워드에 반드시 포함시켜라. 원래 표현(시청 등)도 함께 포함해도 좋다.\n"
            "수주 형태(수의계약·턴키·지명공모 등)나 태그/메모성 단어가 보이면 그대로 키워드에 넣어라.\n"
            "\n"
            "Use short noun phrases. Avoid stopwords.\n"
            "\n"
            "OUTPUT_ONLY_JSON:\n"
            '{"keywords": ["<kw1>", "<kw2>"]}'
        )
        try:
            raw = call_messages(
                model=settings.model_id_classify,
                max_tokens=300,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = parse_json_response(raw)
            keywords = [k for k in parsed.get("keywords", []) if isinstance(k, str) and k.strip()]
        except Exception as e:
            logger.warning("[archive_search] 자연어→키워드 변환 실패: %s — 직접 키워드 검색으로 폴백", e)
            return self.search_keyword(q, limit=limit)

        if not keywords:
            return []

        fts_query = " OR ".join(f'"{_fts_escape(kw)}"' for kw in keywords)
        return self._ranked_match(fts_query, limit)

    def all_cards(self) -> list[dict]:
        return list(self._cards.values())

    def close(self):
        self.conn.close()


_index: ArchiveSearchIndex | None = None


def get_index(rebuild: bool = False) -> ArchiveSearchIndex:
    """모듈 레벨 싱글톤. 첫 호출 시 자동 빌드, rebuild=True면 강제 재구축."""
    global _index
    if _index is None or rebuild:
        if _index is not None:
            _index.close()
        _index = ArchiveSearchIndex()
        _index.build()
    return _index


def build_index() -> int:
    """앱 startup 시 호출용. 싱글톤 인덱스를 (재)빌드하고 카드 수를 반환."""
    return len(get_index(rebuild=True)._cards)


def rebuild_index() -> int:
    """데이터 변경(비교분석 재실행 등) 후 인덱스를 다시 빌드. build_index alias."""
    return build_index()
