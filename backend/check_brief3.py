import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

path = r"C:\Users\20260102\AppData\Local\Temp\p03_yeongdp_brief.json"
data = json.load(open(path, encoding="utf-8"))

# brief_program 항목 샘플 확인
bp_section = data.get("brief_program", [])
if isinstance(bp_section, list):
    print(f"brief_program: {len(bp_section)}개")
    # area_rows 있는 것 먼저 찾기
    has_ar = [bp for bp in bp_section if bp and bp.get("area_rows")]
    no_ar  = [bp for bp in bp_section if bp and not bp.get("area_rows")]
    print(f"  area_rows 있는 항목: {len(has_ar)}")
    print(f"  area_rows 없는 항목: {len(no_ar)}")
    print()
    # 없는 항목 3개 키 확인
    for i, bp in enumerate(no_ar[:5]):
        if not bp:
            continue
        print(f"--- [항목 {i}] 키: {list(bp.keys())[:10]}")
        # 구 area_table 있나?
        at = bp.get("area_table")
        rooms = bp.get("rooms")
        req_areas = bp.get("required_areas")
        optional = bp.get("optional_areas")
        print(f"  area_table: {len(at) if at else 0}")
        print(f"  rooms: {len(rooms) if rooms else 0}")
        print(f"  required_areas: {len(req_areas) if req_areas else 0}")
        print(f"  optional_areas: {len(optional) if optional else 0}")
        # 첫 번째 항목 전체 출력 (짧을 경우)
        if i == 0:
            txt = json.dumps(bp, ensure_ascii=False)
            print("  전체:", txt[:500])
        print()
