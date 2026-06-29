"""
proposal_number_check.check_proposal_numbers 단위 테스트 — LLM/네트워크 없음.

대상: 제안서 prose 의 수치를 지침서 추출 데이터와 대조, 근거 없는 숫자만 flag.
검증: 발명 수치 flag · 지침서 실재 수치 통과 · 한 자리 구조 숫자 제외 · basis 제외 ·
      숫자 무수정(플래그만).
"""
from services.proposal_number_check import check_proposal_numbers


_BRIEF = {
    "_brief_meta": {"facility_type": "public"},
    "feasibility_export": {"sites": [{"site_area_sqm": 43000, "max_height_m": 95}]},
    "raw_text": "가격평가 30점, 디자인 30점, 용적률 250% 이하, 규모 B2F~35F, 공사기간 32개월",
}


class TestCheckProposalNumbers:

    def test_fabricated_number_flagged(self):
        p = {"executive_summary": "분양가 1,100만원/평에 ROI 15.3% 예상"}
        flags = check_proposal_numbers(p, _BRIEF)
        vals = {f["value"] for f in flags}
        assert "1,100" in vals          # 지침서에 없는 발명 수치
        assert "15.3" in vals
        assert all("field" in f and "context" in f for f in flags)

    def test_grounded_numbers_pass(self):
        # 지침서에 실재하는 30/250/35/32 는 flag 되지 않는다
        p = {"executive_summary": "가격평가 30점이 1순위, 용적률 250%, B2F~35F, 32개월"}
        flags = check_proposal_numbers(p, _BRIEF)
        assert flags == []

    def test_scoring_focus_numbers_allowed(self):
        p = {
            "priorities": [{"focus": "x", "why": "y", "scoring_weight": "40%"}],
            "scoring_focus": [{"category": "배치", "points": 40, "weight_pct": 40.0}],
        }
        flags = check_proposal_numbers(p, _BRIEF)
        assert flags == []   # 40 은 결정론 scoring_focus 에 있으므로 통과

    def test_single_digit_structural_ignored(self):
        p = {"design_directions": [{"narrative": "3면 개방 5안 중 1순위"}]}
        flags = check_proposal_numbers(p, _BRIEF)
        assert flags == []   # 한 자리(3·5·1)는 검사 제외

    def test_basis_not_scanned(self):
        # basis 의 'p.999' 페이지 포인터는 사실 주장이 아니라 검사 제외
        p = {"win_themes": [{"theme": "t", "basis": ["p.999", "999억 어쩌고"]}]}
        flags = check_proposal_numbers(p, _BRIEF)
        assert flags == []

    def test_does_not_mutate_proposal(self):
        p = {"executive_summary": "ROI 99.9%"}
        before = dict(p)
        check_proposal_numbers(p, _BRIEF)
        assert p == before   # 숫자 수정 0

    def test_program_detail_scanned(self):
        p = {"program_directions": [{"claim": "c", "detail": "세대수 864세대로 구성"}]}
        flags = check_proposal_numbers(p, _BRIEF)
        assert any(f["value"] == "864" for f in flags)   # 지침서에 없는 864 flag
