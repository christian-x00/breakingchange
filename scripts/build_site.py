from pathlib import Path
import json, time, html

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = ROOT / "data"
DIFF = DATA / "diffs"

DOCS.mkdir(exist_ok=True, parents=True)
(DOCS / "diffs").mkdir(exist_ok=True)

events = []
events_path = DATA / "events.jsonl"
if events_path.exists():
    with open(events_path) as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except Exception:
                pass
events.sort(key=lambda e: e["ts"], reverse=True)

for e in events[:200]:
    src = ROOT / e["diff_file"]
    dst = DOCS / "diffs" / Path(e["diff_file"]).name
    if src.exists():
        dst.write_text(src.read_text())

def row(e):
    when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(e["ts"]))
    link = f"diffs/{Path(e['diff_file']).name}"
    return f"<tr><td>{when}</td><td>{html.escape(e['vendor'])}</td><td>{html.escape(e['type'])}</td><td>{html.escape(e['severity'])}</td><td><a href='{html.escape(e['url'])}'>source</a> · <a href='{link}'>diff</a></td></tr>"

html_page = f"""<!doctype html><html><head>
<meta charset="utf-8"><title>BreakingChange – Vendor Change Feed</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>body{{font-family:system-ui,Segoe UI,Arial;margin:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #eee;padding:8px}}th{{background:#fafafa;text-align:left}}</style>
</head><body>
<h1>BreakingChange – Vendor Policy & API Change Feed</h1>
<p>Automated diffs of ToS, Privacy, Pricing, API & Changelog updates. Bookmark this page and share it on LinkedIn.</p>
<table>
<tr><th>When (UTC)</th><th>Vendor</th><th>Type</th><th>Severity</th><th>Links</th></tr>
{''.join(row(e) for e in events)}
</table>
</body></html>"""
(DOCS / "index.html").write_text(html_page)
print("Site built at /docs/index.html")
