"""오늘의 재벌 역사 — 사이트 인물(GENERATIONS)의 출생·별세일을 한국어 위키백과에서 확인해 data/history.json 을 만든다.

사용: python tools/build_history.py   (한 번 돌리면 되고, 인물을 추가했을 때 다시 돌린다)

동명이인을 막으려고 위키백과의 출생연도가 사이트에 적힌 출생연도와 같을 때만 넣는다.
요청 사이에 1초씩 쉰다.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "chaebol-archive-history/1.0"
DATE = r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"


def people():
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const GENERATIONS = \[(.*?)\n\];", src, re.S).group(1)
    out = []
    for m in re.finditer(r"\{[^{}]*?name:\"([^\"]+)\"[^{}]*?group:\"([^\"]+)\"[^{}]*?\}", block):
        row = m.group(0)
        born = re.search(r'born:"(\d{4})"', row)
        role = re.search(r'role:"([^"]*)"', row)
        if "skip:" in row:
            continue
        name = re.sub(r"\(.*?\)", "", m.group(1)).strip()
        out.append({"name": name, "group": m.group(2), "born": born.group(1) if born else None,
                    "role": role.group(1) if role else ""})
    return out


def summary(title):
    url = "https://ko.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (attempt + 1))
    return None


def dates_from(extract):
    head = extract.split(")")[0] if "(" in extract[:40] else extract[:120]
    found = re.findall(DATE, head)
    return [(int(y), int(m), int(d)) for y, m, d in found]


def main():
    events, checked = [], 0
    for p in people():
        if not p["born"]:
            continue
        checked += 1
        s, ds = None, None
        # 동명이인 문서는 '이름 (출생연도년)', '이름 (기업인)' 식으로 나뉘어 있다
        for title in (p["name"], f"{p['name']} ({p['born']}년)", f"{p['name']} (기업인)", f"{p['name']} (경영인)"):
            cand = summary(title)
            time.sleep(1)
            if not cand or cand.get("type") != "standard":
                continue
            cds = dates_from(cand.get("extract", ""))
            if cds and str(cds[0][0]) == p["born"]:
                s, ds = cand, cds
                break
        if not s:
            continue  # 출생연도가 맞는 문서가 없으면 동명이인일 수 있으니 버린다
        src = s.get("content_urls", {}).get("desktop", {}).get("page", "")
        y, mo, d = ds[0]
        events.append({"md": f"{mo:02d}-{d:02d}", "year": y, "type": "birth", "name": p["name"], "group": p["group"],
                       "role": p["role"], "src": src})
        if len(ds) > 1:
            y, mo, d = ds[1]
            events.append({"md": f"{mo:02d}-{d:02d}", "year": y, "type": "death", "name": p["name"], "group": p["group"],
                           "role": p["role"], "src": src})
    events.sort(key=lambda e: (e["md"], e["year"]))
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "history.json").write_text(json.dumps({
        "source": "한국어 위키백과(출생연도가 사이트 기록과 일치하는 인물만)",
        "count": len(events), "items": events}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"인물 {checked}명 확인, 기념일 {len(events)}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
