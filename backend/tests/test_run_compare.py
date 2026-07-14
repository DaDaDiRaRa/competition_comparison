"""경쟁공모 등록 '비교분석까지 한 번에'(run_compare) 회귀 테스트.

run_pipeline 에서 run_compare 분기를 잠근다: 2개↑면 추출 후 비교분석까지 수행(report_available),
1개면 스킵, off 면 비교 없음. PDF/LLM 파이프라인 함수는 monkeypatch (네트워크 0).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from config import settings
import routers.accumulate as acc

_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ntest\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setitem(settings._data, "db_path", str(tmp_path))
    monkeypatch.setitem(settings._data, "anthropic_api_key", "test-key")

    async def _fake_classify(path):
        return [{"page": 1, "primary_type": "CONCEPT"}]

    async def _fake_extract(path, page_map=None, is_brief=False):
        return [{"page": 1, "data": {}}]

    def _fake_merge(cls, ext):
        return {"_quantitative": {}, "concept": {"_page": 1}}

    async def _fake_compare(brief, subs, ft=""):
        return {"submissions": {s["company"]: {} for s in subs},
                "concept_comparison": {}, "gap_analysis": {}}

    monkeypatch.setattr(acc, "classify_all_pages", _fake_classify)
    monkeypatch.setattr(acc, "extract_pdf", _fake_extract)
    monkeypatch.setattr(acc, "merge_extracted_data", _fake_merge)
    monkeypatch.setattr(acc, "compare_submissions", _fake_compare)
    monkeypatch.setattr(acc, "build_pattern", lambda ft: None)
    monkeypatch.setattr(acc, "_rebuild_archive_index", lambda: 0)
    monkeypatch.setattr(acc, "generate_comparison_report", lambda *a, **k: "<html>cmp</html>")
    monkeypatch.setattr(acc, "generate_submission_report", lambda *a, **k: "<html>sub</html>")

    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _post(client, n_subs, run_compare):
    subs = [{"company": f"사{i}", "result": "win" if i == 0 else "lose"} for i in range(n_subs)]
    files = [("submission_pdfs", (f"s{i}.pdf", _PDF, "application/pdf")) for i in range(n_subs)]
    data = {
        "competition_name": "테스트공모", "facility_type": "public", "project_number": "P1",
        "submissions_json": json.dumps(subs), "run_compare": "true" if run_compare else "false",
    }
    return client.post("/api/accumulate/run", data=data, files=files)


def _events(resp):
    out = []
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            try:
                out.append(json.loads(line[5:].strip()))
            except Exception:
                pass
    return out


class TestRunCompare:
    def test_two_subs_runs_comparison(self, client):
        evs = _events(_post(client, 2, run_compare=True))
        stages = [e.get("stage") for e in evs if e.get("type") == "stage"]
        assert "compare" in stages                      # 비교분석 단계 실행
        complete = [e for e in evs if e.get("type") == "complete"][-1]
        assert complete["report_available"] is True     # 리포트 생성됨
        assert "comparison" in complete

    def test_off_skips_comparison(self, client):
        evs = _events(_post(client, 2, run_compare=False))
        stages = [e.get("stage") for e in evs if e.get("type") == "stage"]
        assert "compare" not in stages                  # 비교 없음
        complete = [e for e in evs if e.get("type") == "complete"][-1]
        assert complete["report_available"] is False

    def test_single_sub_skipped_with_notice(self, client):
        evs = _events(_post(client, 1, run_compare=True))
        assert any(e.get("type") == "compare_skipped" for e in evs)  # 2개 미만 안내
        complete = [e for e in evs if e.get("type") == "complete"][-1]
        assert complete["report_available"] is False
