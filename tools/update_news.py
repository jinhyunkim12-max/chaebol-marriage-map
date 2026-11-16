"""재벌 뉴스 레이더 — 주요 그룹 총수 이름으로 네이버 뉴스 검색 API를 조회해 data/news.json 을 만든다.

본문은 저장하지 않는다. 제목·언론사 주소·시각·원문 링크만 남기고, 제목에 나온 그룹·인물을 연결한다.
환경변수 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 가 없으면 아무것도 하지 않고 끝난다.
"""
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = dt.timezone(dt.timedelta(hours=9))
API = "https://openapi.naver.com/v1/search/news.json"
TOP_GROUPS = 30


def site_data():
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    ftc = re.findall(r'\[(\d+),"([^"]+)","([^"]+)",', re.search(r"const FTC_RAW = \[(.*?)\n\];", src, re.S).group(1))
    owners = [(int(r), g, o) for r, g, o in ftc if int(r) <= TOP_GROUPS and not re.search(r"\(주\)|중앙회|공제회|\(유\)", o)]
    gen = re.search(r"const GENERATIONS = \[(.*?)\n\];", src, re.S).group(1)
    people = set(re.sub(r"\(.*?\)", "", n).strip() for n in re.findall(r'name:"([^"]+)"', gen))
    return owners, people


def search(cid, secret, query):
    q = urllib.parse.urlencode({"query": query, "display": 50, "sort": "date"})
    req = urllib.request.Request(API + "?" + q, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("items", [])


def clean(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t))).strip()


def norm(t):
    return re.sub(r"[^가-힣A-Za-z0-9]", "", t)[:24]


def main():
    cid, secret = os.environ.get("NAVER_CLIENT_ID", "").strip(), os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("NAVER_CLIENT_ID/SECRET 없음 — 뉴스 레이더 건너뜀")
        return 0
    owners, people = site_data()
    now = dt.datetime.now(KST)
    since = now - dt.timedelta(hours=24)
    seen, items = {}, []
    for rank, group, owner in owners:
        for it in search(cid, secret, owner):
            title = clean(it["title"])
            if owner not in title:
                continue  # 제목에 총수 이름이 없는 기사는 뺀다(동명이인·잡음)
            when = email.utils.parsedate_to_datetime(it["pubDate"]).astimezone(KST)
            if when < since:
                continue
            link = it.get("originallink") or it["link"]
            k = norm(title)
            if k in seen:
                seen[k]["dup"] += 1
                continue
            row = {"title": title, "link": link, "press": urllib.parse.urlparse(link).netloc.replace("www.", ""),
                   "time": when.isoformat(timespec="minutes"), "group": group, "owner": owner,
                   "people": sorted(p for p in people if p in title), "dup": 1}
            seen[k] = row
            items.append(row)
        time.sleep(0.2)
    items.sort(key=lambda r: r["time"], reverse=True)
    top = sorted(items, key=lambda r: (-r["dup"], -len(r["people"]), r["time"]), reverse=False)[:5]
    out = {"generated_at": now.isoformat(timespec="minutes"), "window_hours": 24,
           "source": "네이버 뉴스 검색 API", "top": top, "items": items[:300]}
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "news.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"뉴스 {len(items)}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
