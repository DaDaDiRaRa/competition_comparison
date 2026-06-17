import json, glob, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

db_cfg = "D:/APPS/competition_comparison/backend/app_settings.json"
try:
    cfg = json.load(open(db_cfg, encoding="utf-8"))
    db_path = cfg.get("db_path", "")
    print("DB path:", db_path)
except Exception as e:
    print("cfg error:", e)
    db_path = ""

briefs_dir = db_path + "/_briefs"
print("_briefs dir:", briefs_dir)
print("exists:", os.path.isdir(briefs_dir))

if os.path.isdir(briefs_dir):
    jsons = sorted(glob.glob(briefs_dir + "/*.json"), key=os.path.getmtime, reverse=True)
    print("최근 brief JSON:", jsons[:5])
    if jsons:
        data = json.load(open(jsons[0], encoding="utf-8"))
        pages = data.get("pages", [])
        from collections import Counter
        cnt = Counter(p.get("type") for p in pages)
        print("페이지 타입 분포:", dict(cnt))
        bp_pages = [p.get("page") for p in pages if p.get("type") == "BRIEF_PROGRAM"]
        print("BRIEF_PROGRAM 페이지:", bp_pages)
        for p in [x for x in pages if x.get("type") == "BRIEF_PROGRAM"]:
            ar = (p.get("data") or {}).get("area_rows")
            merged = p.get("_merged")
            stacked = p.get("_stacked_pages")
            pg = p.get("page")
            ar_len = len(ar) if ar is not None else "None"
            print(f"  p.{pg}: area_rows={ar_len} _merged={merged} _stacked={stacked}")

        # brief_program 섹션도 확인
        bp_section = data.get("brief_program")
        if bp_section:
            if isinstance(bp_section, list):
                for i, bp in enumerate(bp_section):
                    ar = (bp or {}).get("area_rows")
                    print(f"brief_program[{i}]: area_rows len={len(ar) if ar else 0}")
            else:
                ar = (bp_section or {}).get("area_rows")
                print(f"brief_program: area_rows len={len(ar) if ar else 0}")
        else:
            print("brief_program section: None/missing")
else:
    print("_briefs 폴더 없음")
