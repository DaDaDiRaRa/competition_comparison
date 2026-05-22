"""
audit_tokens.py — 프론트엔드 JSX/JS 파일에서 하드코딩된 스타일 값을
파일명·줄 번호와 함께 추출해 DESIGN_AUDIT.md로 저장.

실행: python tools/audit_tokens.py
"""
import re
from pathlib import Path
from collections import defaultdict

SRC  = Path(__file__).parent.parent / 'frontend' / 'src'
OUT  = Path(__file__).parent.parent / 'DESIGN_AUDIT.md'

# ── 토큰 매핑 ─────────────────────────────────────────────────────────────────

COLOR_TOKENS = {
    '#fafafa'  : 'var(--color-bg-page)',
    '#ffffff'  : 'var(--color-bg-surface)',
    '#fff'     : 'var(--color-bg-surface)',
    '#f9fafb'  : 'var(--color-bg-surface-alt)',
    '#f3f4f6'  : 'var(--color-bg-input-disabled)',
    '#e5e7eb'  : 'var(--color-border)',
    '#e2e2e2'  : 'var(--color-border)',
    '#d1d5db'  : 'var(--color-border-strong)',
    '#cccccc'  : 'var(--color-border-strong)',
    '#001623'  : 'var(--color-text-primary)',
    '#1f2937'  : 'var(--color-text-body)',
    '#4b5563'  : 'var(--color-text-muted)',
    '#6b7280'  : 'var(--color-text-faint)',
    '#9ca3af'  : 'var(--color-text-subtle)',
    '#334155'  : 'var(--color-accent)',
    '#475569'  : 'var(--color-accent-hover)',
    '#f1f5f9'  : 'var(--color-accent-soft)',
    '#e60012'  : 'var(--color-accent)',
    '#c8000f'  : 'var(--color-accent-hover)',
    '#fff0f0'  : 'var(--color-accent-soft)',
    '#16a34a'  : 'var(--color-success)',
    '#15803d'  : 'var(--color-success)',        # 더 진한 녹색 → 토큰 근사치
    '#dcfce7'  : 'var(--color-success-bg)',
    '#86efac'  : 'var(--color-success-border)',
    '#ca8a04'  : 'var(--color-warning)',
    '#fef3c7'  : 'var(--color-warning-bg)',
    '#fef9c3'  : 'var(--color-warning-bg)',
    '#92400e'  : '—',                           # 토큰 없음 (amber-800 경고 텍스트)
    '#ea580c'  : '—',                           # 토큰 없음 (D등급·주황 경고)
    '#fed7aa'  : '—',                           # 토큰 없음 (D등급 배경)
    '#dc2626'  : 'var(--color-danger)',
    '#b91c1c'  : '—',                           # 토큰 없음 (danger 더 진한 버튼)
    '#fee2e2'  : 'var(--color-danger-bg)',
    '#fca5a5'  : 'var(--color-danger-border)',
    '#0891b2'  : 'var(--color-info)',
    '#cffafe'  : 'var(--color-info-bg)',
    '#67e8f9'  : 'var(--color-info-border)',
    # 특수 목적 색상 (토큰 없음)
    '#0d9488'  : '—',   # teal — 당선 결과색
    '#6d28d9'  : '—',   # 보라 — 리포트 버튼
    '#7c3aed'  : '—',   # 보라 — 진단 액센트
    '#5b21b6'  : '—',   # 보라 진함
    '#a78bfa'  : '—',   # 보라 연함
    '#ede9fe'  : '—',   # 보라 배경
    '#d97706'  : '—',   # amber — 1위 메달
    '#c2410c'  : '—',   # orange — 3위 메달
    '#374151'  : '—',   # gray-700
    '#4a5568'  : '—',   # slate-600 (≠ #475569)
    '#64748b'  : '—',   # slate-500
    '#1a2a1a'  : '—',   # 다크 그린 (비교결과 배경)
    '#db2777'  : '—',   # pink
    '#ec4899'  : '—',   # pink-500 (차트)
    '#0284c7'  : '—',   # sky-600 (차트)
    '#22d3ee'  : '—',   # cyan (차트)
    '#bbf7d0'  : '—',   # green 연함 (차트)
    '#fbcfe8'  : '—',   # pink 연함 (차트)
    '#fef08a'  : '—',   # yellow 연함 (차트)
    '#444'     : '—',   # 단축 gray
    '#555'     : '—',   # 단축 gray
    '#666'     : '—',   # 단축 gray
    '#999'     : '—',   # 단축 gray
    '#aaa'     : '—',   # 단축 gray
}

FONTSIZE_TOKENS = {
    '11': 'var(--font-size-xs)',
    '12': 'var(--font-size-sm)',
    '14': 'var(--font-size-base)',
    '15': 'var(--font-size-md)',
    '18': 'var(--font-size-lg)',
    '20': 'var(--font-size-xl)',
    '24': 'var(--font-size-2xl)',
    # 토큰 없는 크기
    '10': '—',
    '13': '—',
    '16': '—',
    '22': '—',
    '28': '—',
    '36': '—',
}

FONTWEIGHT_TOKENS = {
    '400': 'var(--font-weight-regular)',
    '500': 'var(--font-weight-medium)',
    '600': 'var(--font-weight-semibold)',
    '700': 'var(--font-weight-bold)',
    '800': '—',
}

GAP_TOKENS = {
    '4' : 'var(--gap-xs)',
    '6' : '—',
    '8' : 'var(--gap-sm)',
    '10': '—',
    '12': 'var(--gap-md)',
    '14': '—',
    '16': '—',
    '20': 'var(--gap-lg)',
    '24': '—',
    '32': 'var(--gap-xl)',
}

BORDERRADIUS_TOKENS = {
    '4' : '—',
    '6' : 'var(--btn-radius) / var(--card-radius-sm)',
    '8' : '—',
    '10': 'var(--card-radius)',
    '12': 'var(--modal-radius)',
    '14': '—',
    '20': 'var(--badge-radius)',
    '50': '—',  # circle
}

RGBA_TOKENS = {
    'rgba(0,0,0,0.45)'     : 'var(--color-overlay)',
    'rgba(0, 0, 0, 0.45)'  : 'var(--color-overlay)',
    'rgba(0,0,0,0.75)'     : '—',
    'rgba(0, 0, 0, 0.75)'  : '—',
}

# ── 스캔 ──────────────────────────────────────────────────────────────────────

Row = tuple  # (value, filename, lineno, token)
rows: list[Row] = []
seen: set = set()   # 중복 제거용

def add(value: str, filepath: Path, lineno: int, token: str):
    key = (value, filepath.name, lineno)
    if key not in seen:
        seen.add(key)
        rows.append((value, filepath.name, lineno, token))

def is_comment(line: str) -> bool:
    s = line.strip()
    return s.startswith('//') or s.startswith('*') or s.startswith('/*')

files = sorted(
    f for f in (list(SRC.rglob('*.jsx')) + list(SRC.rglob('*.js')))
    if 'node_modules' not in str(f) and 'kunwon-tokens' not in str(f)
)

for filepath in files:
    text = filepath.read_text(encoding='utf-8')
    lines = text.splitlines()

    for lineno, line in enumerate(lines, 1):
        if is_comment(line):
            continue
        # CSS var() 줄은 이미 토큰화된 것 — 단, 같은 줄에 하드코딩도 있을 수 있음
        # 그래도 줄 전체를 분석

        # ── 색상: 3~6자리 hex ────────────────────────────────────────────────
        for m in re.finditer(r"['\"]( #[0-9A-Fa-f]{3,8})['\"]|['\"]( #[0-9A-Fa-f]{3,8})['\"]", line):
            pass  # placeholder — use simpler pattern below

        for m in re.finditer(r"'(#[0-9A-Fa-f]{3,8})'", line):
            val = m.group(1).lower()
            token = COLOR_TOKENS.get(val, '—')
            add(val, filepath, lineno, token)

        for m in re.finditer(r'"(#[0-9A-Fa-f]{3,8})"', line):
            val = m.group(1).lower()
            token = COLOR_TOKENS.get(val, '—')
            add(val, filepath, lineno, token)

        # ── 색상: rgba() ─────────────────────────────────────────────────────
        for m in re.finditer(r"rgba\([^)]+\)", line):
            val = m.group(0)
            # CSS var() 안에 있으면 스킵
            if 'var(' in line[:m.start()].split('\n')[-1]:
                continue
            token = RGBA_TOKENS.get(val, '—')
            add(val, filepath, lineno, token)

        # ── fontSize ─────────────────────────────────────────────────────────
        for m in re.finditer(r"fontSize:\s*(\d+)(?!\d|px)", line):
            num = m.group(1)
            if num in FONTSIZE_TOKENS:
                add(f'fontSize: {num}', filepath, lineno, FONTSIZE_TOKENS[num])

        for m in re.finditer(r"fontSize:\s*'(\d+)px'", line):
            num = m.group(1)
            if num in FONTSIZE_TOKENS:
                add(f"fontSize: '{num}px'", filepath, lineno, FONTSIZE_TOKENS[num])

        # ── fontWeight ───────────────────────────────────────────────────────
        for m in re.finditer(r"fontWeight:\s*(\d{3})(?!\d)", line):
            num = m.group(1)
            if num in FONTWEIGHT_TOKENS:
                add(f'fontWeight: {num}', filepath, lineno, FONTWEIGHT_TOKENS[num])

        # ── gap ──────────────────────────────────────────────────────────────
        for m in re.finditer(r"(?<![A-Za-z])gap:\s*(\d+)(?!\d)", line):
            num = m.group(1)
            if num in GAP_TOKENS:
                add(f'gap: {num}', filepath, lineno, GAP_TOKENS[num])

        # ── borderRadius ─────────────────────────────────────────────────────
        for m in re.finditer(r"borderRadius:\s*(\d+)(?!\d)", line):
            num = m.group(1)
            token = BORDERRADIUS_TOKENS.get(num, '—')
            add(f'borderRadius: {num}', filepath, lineno, token)

# ── 출력 ──────────────────────────────────────────────────────────────────────

# 카테고리 분류
def categorize(value: str) -> str:
    if value.startswith('#') or value.startswith('rgba'):
        return '색상'
    if value.startswith('fontSize'):
        return '폰트 크기'
    if value.startswith('fontWeight'):
        return '폰트 굵기'
    if value.startswith('gap'):
        return '간격 (gap)'
    if value.startswith('borderRadius'):
        return '보더 반경'
    return '기타'

by_cat: dict[str, list] = defaultdict(list)
for row in rows:
    by_cat[categorize(row[0])].append(row)

CAT_ORDER = ['색상', '폰트 크기', '폰트 굵기', '간격 (gap)', '보더 반경', '기타']

with OUT.open('w', encoding='utf-8') as f:
    total = len(rows)
    no_token = sum(1 for r in rows if r[3] == '—')

    f.write('# Design Audit — 하드코딩 스타일 값 전체 목록\n\n')
    f.write(f'> 총 **{total}개** 하드코딩 값 발견 · 토큰 없음 **{no_token}개**  \n')
    f.write(f'> 스캔 대상: `frontend/src/**/*.jsx`, `**/*.js`  \n\n')
    f.write('---\n\n')

    for cat in CAT_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue

        no_tok_cnt = sum(1 for r in items if r[3] == '—')
        f.write(f'## {cat}  ({len(items)}개 · 토큰 없음 {no_tok_cnt}개)\n\n')
        f.write('| 값 | 파일 | 줄 | 교체할 토큰 |\n')
        f.write('|---|---|---:|---|\n')

        # 파일명 → 줄 번호 순 정렬
        for val, fname, lno, token in sorted(items, key=lambda r: (r[1], r[2])):
            token_cell = f'`{token}`' if token != '—' else '—'
            f.write(f'| `{val}` | {fname} | {lno} | {token_cell} |\n')

        f.write('\n')

    # 토큰 없는 것 요약
    f.write('---\n\n')
    f.write('## 토큰 없음 — 신규 토큰 추가 권고\n\n')
    f.write('| 값 | 등장 횟수 | 권고 토큰 이름 |\n')
    f.write('|---|---:|---|\n')
    from collections import Counter
    no_tok_vals = Counter(r[0] for r in rows if r[3] == '—')
    for val, cnt in sorted(no_tok_vals.items(), key=lambda x: -x[1]):
        suggest = val.replace('#', '--color-').replace('rgba(', '--color-overlay-').replace(')', '').replace(',', '-').replace(' ', '')
        f.write(f'| `{val}` | {cnt} | `{suggest}` |\n')

print(f'Done: {total} entries → {OUT}')
