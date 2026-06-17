import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

path = r"C:\Users\20260102\AppData\Local\Temp\p03_yeongdp_brief.json"
data = json.load(open(path, encoding="utf-8"))

pages = data.get("pages", [])
from collections import Counter
cnt = Counter(p.get("type") for p in pages)
print("총 페이지 수:", len(pages))
print("페이지 타입 분포:", dict(cnt))

print()
bp_pages = [p for p in pages if p.get("type") == "BRIEF_PROGRAM"]
print("BRIEF_PROGRAM 페이지 수:", len(bp_pages))
for p in bp_pages:
    ar = (p.get("data") or {}).get("area_rows")
    at = (p.get("data") or {}).get("area_table")
    merged = p.get("_merged")
    stacked = p.get("_stacked_pages")
    pg = p.get("page")
    print(f"  p.{pg}: area_rows={len(ar) if ar else 0} area_table={len(at) if at else 0} _merged={merged} _stacked={stacked}")

print()
be_pages = [p for p in pages if p.get("type") == "BRIEF_EVALUATION"]
print("BRIEF_EVALUATION 페이지 수:", len(be_pages))
for p in be_pages:
    cats = (p.get("data") or {}).get("evaluation_categories", [])
    pg = p.get("page")
    merged = p.get("_merged")
    stacked = p.get("_stacked_pages")
    print(f"  p.{pg}: categories={len(cats)} _merged={merged} _stacked={stacked}")
    for c in cats:
        print(f"    - {c.get('name')}: points={c.get('points')} shared_with={c.get('shared_with')}")

print()
# brief_program 섹션
bp_section = data.get("brief_program")
if bp_section:
    if isinstance(bp_section, list):
        total_rows = sum(len((bp or {}).get("area_rows") or []) for bp in bp_section)
        print(f"brief_program section: {len(bp_section)}개 항목, 총 area_rows={total_rows}")
    else:
        ar = (bp_section or {}).get("area_rows")
        print(f"brief_program section: area_rows={len(ar) if ar else 0}")
else:
    print("brief_program section: None")
