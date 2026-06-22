"""
brief pipeline unit tests — validator + exporter (no LLM).
Run: python -m pytest tests/test_brief_pipeline.py -v
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from services.brief_validator import validate_brief
from services.brief_checklist_exporter import to_markdown, to_xlsx, to_html

BRIEF_DATA = {
    '_quantitative': {
        'total_floor_area_sqm': 15000,
        'site_area_sqm': 5000,
        'building_coverage_ratio_pct': 60,
        'floor_area_ratio_pct': 300,
        'floors_above': 5,
        'parking_count': 100,
    },
    'brief_evaluation': {
        'evaluation_categories': [
            {'name': '설계 개념', 'points': 30, 'description': '창의성'},
            {'name': '기능성',    'points': 25, 'description': '공간구성'},
            {'name': '경관',     'points': 25, 'description': '도시환경'},
            {'name': '경제성',   'points': None, 'description': '유지관리'},   # null → medium flag
        ],
        'total_points': 100,
    },
    'brief_program': {
        'total_required_floor_area_sqm': 15000,
        'rooms': [
            {'name': '주민센터',   'required_area_sqm': 800, 'required_count': 1},
            {'name': '다목적강당', 'required_area_sqm': 500, 'required_count': 1},
        ],
    },
    'brief_design_guide': {
        'design_requirements': [
            '공공성과 개방성을 최우선으로 한다.',
            '친환경 설계 방식을 적용한다.',
        ],
    },
    'page_map': [
        {'page': 1, 'primary_type': 'BRIEF_OVERVIEW',    'confidence': 0.92},
        {'page': 2, 'primary_type': 'BRIEF_PROGRAM',     'confidence': 0.45},    # low → flag
        {'page': 3, 'primary_type': 'BRIEF_EVALUATION',  'confidence': 0.88},
        {'page': 4, 'primary_type': 'BRIEF_DESIGN_GUIDE','confidence': 0.80},
        {'page': 5, 'primary_type': 'BRIEF_SUBMISSION',  'confidence': 0.75},
    ],
}

REQUIREMENTS = {
    'requirements': [
        {'axis': 'concept_clarity',  'description': '설계 개념의 명확성', 'weight_pct': 30},
        {'axis': 'site_response',    'description': '대지와의 관계성',    'weight_pct': 25},
        {'axis': 'program_planning', 'description': '프로그램 적절성',    'weight_pct': 25},
    ],
    'special_requirements': ['장애인 편의시설 법정 기준 충족'],
}


class TestValidateBrief:
    def test_returns_validation_key(self):
        r = validate_brief(BRIEF_DATA, REQUIREMENTS)
        assert 'validation' in r

    def test_summary_keys(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        assert set(v['summary'].keys()) == {'high', 'medium', 'low'}

    def test_flags_are_list(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        assert isinstance(v['flags'], list)

    def test_flag_fields(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        for f in v['flags']:
            assert 'type' in f, f"missing 'type': {f}"
            assert 'severity' in f, f"missing 'severity': {f}"
            assert 'message' in f, f"missing 'message': {f}"
            assert 'location' in f, f"missing 'location': {f}"
            assert f['severity'] in ('high', 'medium', 'low')

    def test_null_points_detected(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        types = [f['type'] for f in v['flags']]
        assert 'points_mismatch' in types, "배점 null 항목 미감지"

    def test_low_confidence_detected(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        types = [f['type'] for f in v['flags']]
        assert 'low_confidence' in types, "저신뢰 페이지 미감지"

    def test_summary_counts_match_flags(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        flags = v['flags']
        summary = v['summary']
        assert summary['high']   == sum(1 for f in flags if f['severity'] == 'high')
        assert summary['medium'] == sum(1 for f in flags if f['severity'] == 'medium')
        assert summary['low']    == sum(1 for f in flags if f['severity'] == 'low')

    def test_checked_rules_present(self):
        v = validate_brief(BRIEF_DATA, REQUIREMENTS)['validation']
        assert 'checked_rules' in v
        assert len(v['checked_rules']) >= 4


class TestToMarkdown:
    def setup_method(self):
        v_result = validate_brief(BRIEF_DATA, REQUIREMENTS)
        self.bd = {**BRIEF_DATA, **v_result}
        self.validation = v_result['validation']

    def test_returns_string(self):
        md = to_markdown(self.bd, self.validation)
        assert isinstance(md, str)
        assert len(md) > 100

    def test_five_sections(self):
        md = to_markdown(self.bd, self.validation)
        assert '## 1. 사업 개요' in md
        assert '## 2. 면적 프로그램' in md
        assert '## 3. 심사기준' in md
        assert '## 4. 요구사항·설계 지침' in md
        assert '## 5. 검증 경고' in md

    def test_area_values_present(self):
        md = to_markdown(self.bd, self.validation)
        assert '15,000' in md or '15000' in md  # 연면적

    def test_evaluation_table(self):
        md = to_markdown(self.bd, self.validation)
        assert '설계 개념' in md
        assert '30' in md

    def test_flag_summary_line(self):
        md = to_markdown(self.bd, self.validation)
        # 검증 경고 섹션의 건수 요약 줄 (예: "높음: 1건 / 보통: 2건 / 낮음: 0건")
        assert '높음:' in md and '보통:' in md and '낮음:' in md

    def test_room_program(self):
        md = to_markdown(self.bd, self.validation)
        assert '주민센터' in md
        assert '다목적강당' in md


class TestToXlsx:
    def setup_method(self):
        v_result = validate_brief(BRIEF_DATA, REQUIREMENTS)
        self.bd = {**BRIEF_DATA, **v_result}
        self.validation = v_result['validation']

    def test_returns_bytes(self):
        b = to_xlsx(self.bd, self.validation)
        assert isinstance(b, bytes)
        assert len(b) > 1000

    def test_valid_xlsx(self):
        import openpyxl, io
        b = to_xlsx(self.bd, self.validation)
        wb = openpyxl.load_workbook(io.BytesIO(b))
        assert len(wb.sheetnames) == 4

    def test_sheet_names(self):
        import openpyxl, io
        b = to_xlsx(self.bd, self.validation)
        wb = openpyxl.load_workbook(io.BytesIO(b))
        names = wb.sheetnames
        assert '1.면적·프로그램' in names
        assert '2.심사기준'      in names
        assert '3.요구사항'      in names
        assert '4.검증경고'      in names

    def test_sheet1_has_data(self):
        import openpyxl, io
        b = to_xlsx(self.bd, self.validation)
        wb = openpyxl.load_workbook(io.BytesIO(b))
        ws = wb['1.면적·프로그램']
        values = [cell.value for row in ws.iter_rows() for cell in row if cell.value]
        assert any('주민센터' in str(v) for v in values)

    def test_sheet2_score_present(self):
        import openpyxl, io
        b = to_xlsx(self.bd, self.validation)
        wb = openpyxl.load_workbook(io.BytesIO(b))
        ws = wb['2.심사기준']
        values = [cell.value for row in ws.iter_rows() for cell in row if cell.value]
        assert any(v == 30 or v == '30' for v in values), "배점 30 미발견"

    def test_sheet4_severity_colors(self):
        import openpyxl, io
        b = to_xlsx(self.bd, self.validation)
        wb = openpyxl.load_workbook(io.BytesIO(b))
        ws = wb['4.검증경고']
        # 첫 번째 데이터 행에 fill이 있는지 확인
        for row in ws.iter_rows(min_row=4):
            fills = [c.fill.fgColor.rgb for c in row if c.fill and c.fill.fgColor]
            if any(f not in ('00000000', '000000') for f in fills):
                break
        # 경고가 있으면 색 fill이 적용되어야 함
        flag_count = sum(self.validation['summary'].values())
        if flag_count > 0:
            # 경고 행이 존재하면 최소 1개 이상의 비기본 색이 있어야 함
            all_fills = set()
            for row in ws.iter_rows(min_row=5):
                for c in row:
                    if c.fill and c.fill.fgColor:
                        all_fills.add(c.fill.fgColor.rgb)
            non_default = all_fills - {'00000000', '000000', 'FFFFFFFF', None}
            assert len(non_default) > 0, f"severity 색상 미적용: fills={all_fills}"


class TestToHtml:
    def setup_method(self):
        v_result = validate_brief(BRIEF_DATA, REQUIREMENTS)
        self.bd = {**BRIEF_DATA, **v_result}
        self.validation = v_result['validation']

    def test_returns_wellformed_document(self):
        h = to_html(self.bd, self.validation)
        assert isinstance(h, str)
        assert h.startswith('<!DOCTYPE html>')
        assert h.rstrip().endswith('</html>')
        # 태그 균형 (void 제외)
        from html.parser import HTMLParser
        class _B(HTMLParser):
            VOID = {'meta', 'br', 'hr', 'img', 'input', 'link', 'col'}
            def __init__(self): super().__init__(); self.stk = []; self.bad = 0
            def handle_starttag(self, t, a):
                if t not in self.VOID: self.stk.append(t)
            def handle_endtag(self, t):
                if t in self.VOID: return
                if self.stk and self.stk[-1] == t: self.stk.pop()
                else: self.bad += 1
        b = _B(); b.feed(h)
        assert b.stk == [] and b.bad == 0

    def test_five_sections(self):
        h = to_html(self.bd, self.validation)
        for title in ('사업 개요', '면적 프로그램', '심사기준', '요구사항·설계 지침', '검증 경고'):
            assert title in h

    def test_content_present(self):
        h = to_html(self.bd, self.validation)
        assert '주민센터' in h          # 면적 프로그램
        assert '30' in h                # 배점

    def test_escapes_html_in_data(self):
        bd = {**self.bd, '_brief_meta': {'brief_name': '<script>alert(1)</script>'}}
        h = to_html(bd, self.validation)
        assert '<script>alert(1)</script>' not in h
        assert '&lt;script&gt;' in h
