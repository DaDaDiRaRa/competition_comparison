"""README.md(사용자 매뉴얼) → 화이트+건원 RED 테마 HTML 렌더러.

도움말 기능의 단일 소스. main.py 의 `/api/readme` 가 README.md 원문을 읽어
이 모듈로 렌더링한다. 별도 README.html 을 유지하지 않으므로 드리프트가 없다.

- Markdown 확장: tables / fenced_code / sane_lists / toc(slugify_unicode).
  toc 의 slugify_unicode 가 GitHub 호환 한글 슬러그를 생성 → README 의 목차
  앵커(`#1-접속`, `#경쟁-공모-등록-탭` 등)가 그대로 동작.
- 링크 처리(클라이언트 스크립트): http(s) 링크는 새 탭, 그 외 로컬 문서 링크
  (DEVELOPER.md 등 앱이 서빙하지 않음)는 비활성화해 iframe 안에서 404 내비게이션 방지.
- LLM 호출 없음. 색상은 화이트 + 건원 RED(#e60012).
"""
from __future__ import annotations

_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>설계공모 경쟁분석 시스템 — 사용자 매뉴얼</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" rel="stylesheet">
<style>
  :root{
    --accent:#e60012;
    --accent-soft:rgba(230,0,18,.06);
    --accent-strong:rgba(230,0,18,.14);
    --bg:#ffffff;
    --text:#1f2329;
    --muted:#6b7280;
    --border:#e5e7eb;
    --border-strong:#d1d5db;
    --code-bg:#f6f7f9;
    --row-alt:#fafbfc;
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{
    margin:0; padding:0;
    font-family:'Pretendard','Pretendard Variable',-apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic','맑은 고딕','Apple SD Gothic Neo',sans-serif;
    color:var(--text); background:var(--bg);
    font-size:15px; line-height:1.7;
    -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  }
  .doc{max-width:860px; margin:0 auto; padding:40px 28px 80px;}

  h1{
    font-size:26px; font-weight:800; color:var(--accent);
    margin:0 0 18px; padding-bottom:14px; border-bottom:3px solid var(--accent);
    line-height:1.3;
  }
  h2{
    font-size:20px; font-weight:700; color:var(--accent);
    margin:44px 0 14px; padding-bottom:8px; border-bottom:1px solid var(--border);
    scroll-margin-top:16px;
  }
  h3{font-size:16.5px; font-weight:700; color:var(--text); margin:28px 0 10px; scroll-margin-top:16px;}
  h4{font-size:14.5px; font-weight:700; color:var(--text); margin:20px 0 8px;}
  p{margin:10px 0;}
  a{color:var(--accent); text-decoration:none;}
  a:hover{text-decoration:underline;}
  strong{font-weight:700;}

  ul,ol{margin:10px 0; padding-left:22px;}
  li{margin:5px 0;}
  li>ul,li>ol{margin:4px 0;}

  hr{border:none; border-top:1px solid var(--border); margin:32px 0;}

  blockquote{
    margin:16px 0; padding:12px 16px;
    background:var(--accent-soft); border-left:4px solid var(--accent);
    border-radius:0 6px 6px 0; color:var(--text);
  }
  blockquote p{margin:4px 0;}

  code{
    background:var(--code-bg); padding:2px 6px; border-radius:4px;
    font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;
    font-size:.88em; color:#b00010;
  }
  pre{
    background:var(--code-bg); border:1px solid var(--border);
    border-radius:8px; padding:14px 16px; overflow-x:auto; margin:14px 0;
  }
  pre code{background:none; padding:0; color:var(--text); font-size:13px;}

  table{
    border-collapse:collapse; width:100%; margin:16px 0; font-size:14px;
    border:1px solid var(--border-strong);
  }
  th,td{border:1px solid var(--border); padding:9px 12px; text-align:left; vertical-align:top;}
  thead th{background:var(--accent-soft); color:var(--text); font-weight:700; border-bottom:2px solid var(--accent-strong);}
  tbody tr:nth-child(even){background:var(--row-alt);}

  /* 비활성화된 로컬 문서 링크(DEVELOPER.md 등) */
  a.deadlink{color:var(--muted); text-decoration:none; cursor:default;}
  a.deadlink:hover{text-decoration:none;}

  @media print{
    .doc{max-width:none; padding:0;}
    h2{page-break-after:avoid;}
    table,pre,blockquote{page-break-inside:avoid;}
  }
</style>
</head>
<body>
  <article class="doc">
{{BODY}}
  </article>
<script>
  // 외부 링크는 새 탭, 로컬 문서 링크(앱 미서빙)는 비활성화해 iframe 404 방지.
  document.querySelectorAll('a[href]').forEach(function(a){
    var href = a.getAttribute('href') || '';
    if (/^https?:/i.test(href)) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    else if (href.charAt(0) !== '#') { a.removeAttribute('href'); a.className = 'deadlink'; }
  });
</script>
</body>
</html>
"""


def render_readme_html(md_text: str) -> str:
    """README.md 원문(str) → 자체완결 HTML 문서(str).

    markdown 미설치 등 렌더 실패 시에도 원문을 <pre> 로 보여 주는 폴백을 둔다
    (도움말이 완전히 깨지지 않도록).
    """
    try:
        import markdown
        from markdown.extensions.toc import slugify_unicode

        body = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "sane_lists", "toc"],
            extension_configs={"toc": {"slugify": slugify_unicode}},
            output_format="html5",
        )
    except Exception:
        import html as _html
        body = "<pre>" + _html.escape(md_text) + "</pre>"
    return _TEMPLATE.replace("{{BODY}}", body)
