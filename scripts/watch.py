import os, re, json, time, difflib, hashlib
from pathlib import Path
import requests, yaml
from slugify import slugify
from trafilatura import extract

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SNAP = DATA / "snapshots"
DIFF = DATA / "diffs"
EVENTS = DATA / "events.jsonl"

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
REPO = os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

SNAP.mkdir(parents=True, exist_ok=True)
DIFF.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

def fetch_text(url: str) -> str:
    headers = {
        "User-Agent": "BreakingChangeBot/0.1 (+https://github.com/)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=45)
    r.raise_for_status()
    html = r.text
    text = extract(html, include_comments=False, include_links=False) or ""
    text = re.sub(r"\s+", " ", text).strip()
    return text

def meaningful_delta(a: str, b: str):
    a_lines, b_lines = a.split(), b.split()
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines)
    ratio = sm.quick_ratio()
    diff = difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="")
    diff_text = "\n".join(diff)
    magnitude = sum(1 for l in diff_text.splitlines() if l.startswith(("+","-")) and not l.startswith(("+++","---")))
    changed = (ratio < 0.995) and (len(diff_text) > 120) and (magnitude > 8)
    return changed, diff_text, magnitude

CATS = {
    "pricing": ["price", "pricing", "fee", "charge", "cost", "tier", "billing"],
    "data_usage": ["data", "collect", "share", "retain", "store", "process", "retention"],
    "ip_ai_training": ["train", "training", "ai", "model", "license", "ip"],
    "deprecation": ["deprecat", "sunset", "remove", "eol", "replacement", "migrate"],
    "rate_limits": ["rate limit", "quota", "rpm", "rps", "requests per", "throughput"],
    "acceptable_use": ["prohibited", "abuse", "spam", "illegal", "malware", "harmful"],
    "privacy": ["privacy", "gdpr", "ccpa", "pii", "data subject", "controller", "processor"],
}
def classify(before: str, after: str, diff_text: str):
    changed_text = " ".join([l[1:] for l in diff_text.splitlines() if l.startswith(("+","-"))])
    text = (after + " " + changed_text).lower()
    category, best_hits = "privacy", 0
    for cat, kws in CATS.items():
        hits = sum(1 for k in kws if k in text)
        if hits > best_hits:
            category, best_hits = cat, hits
    if best_hits >= 5: sev = "critical"
    elif best_hits >= 3: sev = "high"
    elif best_hits >= 2: sev = "medium"
    else: sev = "low"
    eff = None
    m = re.search(r"(effective|starts|applies)\s+(on|from)?\s*([A-Z][a-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})", after, re.I)
    if m: eff = m.group(3)
    tl = f"{category.replace('_',' ').title()} change detected"
    return {"category": category, "severity": sev, "tl;dr": tl, "effective_date": eff}

def post_slack(title: str, summary: str, url: str, severity: str):
    if not SLACK_WEBHOOK: return
    color = {"low":"#8ea6c9","medium":"#f2c744","high":"#f29f05","critical":"#d73a49"}[severity]
    payload = {
      "attachments": [{
        "color": color,
        "title": title,
        "title_link": url,
        "text": summary
      }]
    }
    try:
        requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
    except Exception:
        pass

def create_issue(title: str, body: str):
    if not (GITHUB_TOKEN and REPO): return
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        requests.post(url, headers=headers, json={"title": title, "body": body}, timeout=20)
    except Exception:
        pass

def run():
    config = yaml.safe_load((ROOT / "watchers.yml").read_text())
    for s in config["sources"]:
        vendor, slug, typ, url = s["vendor"], s["slug"], s["type"], s["url"]
        key = f"{slug}-{typ}"
        snap_path = SNAP / f"{key}.txt"
        before = snap_path.read_text() if snap_path.exists() else ""
        try:
            after = fetch_text(url)
        except Exception as e:
            print(f"Fetch error {url}: {e}")
            continue
        changed, diff_text, magnitude = meaningful_delta(before, after)
        if not changed:
            print(f"[=] {vendor} {typ}: no meaningful change")
            continue

        snap_path.write_text(after)
        h = hashlib.sha1((str(time.time()) + url).encode()).hexdigest()[:12]
        diff_file = DIFF / f"{key}-{h}.diff"
        diff_file.write_text(diff_text)

        meta = classify(before, after, diff_text)
        event = {
            "ts": int(time.time()),
            "vendor": vendor,
            "slug": slug,
            "type": typ,
            "url": url,
            "diff_file": str(diff_file.relative_to(ROOT)),
            "magnitude": magnitude,
            **meta
        }
        with open(EVENTS, "a") as f:
            f.write(json.dumps(event) + "\n")

        title = f"{vendor} {typ.title()} update — {meta['severity'].upper()}"
        summary = f"{meta['tl;dr']}. {('Effective ' + meta['effective_date']) if meta['effective_date'] else ''}"
        post_slack(title, summary, url, meta["severity"])
        issue_body = f"{summary}\n\nDiff: ./{diff_file.relative_to(ROOT)}\nSource: {url}"
        create_issue(title, issue_body)
        print(f"[+] Change recorded for {vendor} {typ}")

if __name__ == "__main__":
    run()
