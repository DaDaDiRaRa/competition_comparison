"""교차비교 지침서 통합 회귀 테스트 (MATURITY 로드맵 #1).

교차비교가 서로 다른 공모의 제출물을 비교할 때, 첫 공모 지침서를 전체
공통 기준으로 오적용하지 않고 제출물별 자기 지침서(_brief_context)로
판정하도록 두 메커니즘을 잠근다:
  1) _brief_digest 가 요구사항·정량만 컴팩트하게 뽑는다.
  2) comparator._trim_extracted 가 _brief_context 를 트리밍에서 보존한다.
"""
from routers.accumulate import _brief_digest
from services.comparator import _trim_extracted


class TestBriefDigest:
    def test_extracts_requirements_and_quantitative(self):
        brief = {"_requirements": {"a": 1}, "_quantitative": {"b": 2}, "junk": 3}
        assert _brief_digest(brief) == {"_requirements": {"a": 1}, "_quantitative": {"b": 2}}

    def test_empty_brief_returns_empty(self):
        assert _brief_digest({}) == {}
        assert _brief_digest(None) == {}

    def test_partial_brief(self):
        assert _brief_digest({"_requirements": {"a": 1}}) == {"_requirements": {"a": 1}}
        # 빈 요구사항/정량은 담지 않음 (falsy)
        assert _brief_digest({"_requirements": {}, "_quantitative": {}}) == {}


class TestTrimExtractedPreservesBriefContext:
    def test_brief_context_survives_trimming(self):
        # 다공모 교차비교에서 제출물에 실린 자기 지침서가 트리밍 후에도 남아야
        # comparator 프롬프트가 제출물별 판정을 할 수 있다.
        data = {"_brief_context": {"_requirements": {"x": 1}}, "concept": {}, "junk": 9}
        trimmed = _trim_extracted(data)
        assert trimmed["_brief_context"] == {"_requirements": {"x": 1}}
        assert "junk" not in trimmed

    def test_normal_submission_has_no_brief_context(self):
        # 단일 공모 flow 제출물엔 _brief_context 가 없어 기존 동작 불변.
        trimmed = _trim_extracted({"concept": {"a": 1}})
        assert "_brief_context" not in trimmed
