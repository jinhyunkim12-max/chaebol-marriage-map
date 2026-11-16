"""재벌 순위 — 그룹별 상장 계열사 시가총액 합계와 전일·1주·1개월 변화를 data/rank.json 으로 만든다.

데이터: 공공데이터포털 '금융위원회_주식시세정보'(getStockPriceInfo). 기준일 다음 영업일 오후에 공개된다.
환경변수 DATA_GO_KR_KEY(일반 인증키, Decoding)가 없으면 아무것도 하지 않고 끝난다.
그룹 판정 규칙은 update_today.py 와 같다.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_today import group_of, KST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"


def fetch_day(key, day):
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({"serviceKey": key, "resultType": "json", "numOfRows": 1000,
                                    "pageNo": page, "basDt": day.strftime("%Y%m%d")})
        with urllib.request.urlopen(API + "?" + q, timeout=60) as r:
            body = json.load(r)["response"]["body"]
        items = body.get("items", {}) or {}
        got = items.get("item", []) if isinstance(items, dict) else []
        rows += got
        if len(rows) >= int(body.get("totalCount", 0)) or not got:
            return rows
        page += 1
        time.sleep(0.5)


def latest_day(key, start, back=10):
    for i in range(back):
        day = start - dt.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        rows = fetch_day(key, day)
        if rows:
            return day, rows
    return None, []


def by_group(rows):
    out = {}
    for r in rows:
        g = group_of(r.get("itmsNm", ""))
        if not g:
            continue
        cap = int(r.get("mrktTotAmt") or 0)
        e = out.setdefault(g, {"group": g, "cap": 0, "stocks": []})
        e["cap"] += cap
        e["stocks"].append({"name": r["itmsNm"], "code": r.get("srtnCd"), "cap": cap,
                            "close": int(r.get("clpr") or 0), "chg": float(r.get("fltRt") or 0)})
    for e in out.values():
        e["stocks"].sort(key=lambda s: -s["cap"])
    return out


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY 없음 — 재벌 순위 건너뜀")
        return 0
    today = dt.datetime.now(KST).date()
    day, rows = latest_day(key, today - dt.timedelta(days=1))
    if not day:
        print("최근 시세 없음", file=sys.stderr)
        return 1
    cur = by_group(rows)
    prev_caps = {}
    for label, delta in (("d1", 1), ("w1", 7), ("m1", 30)):
        pday, prows = latest_day(key, day - dt.timedelta(days=delta))
        prev_caps[label] = ({g: e["cap"] for g, e in by_group(prows).items()}, pday)
    groups = []
    for g, e in cur.items():
        row = {"group": g, "cap": e["cap"], "n": len(e["stocks"]), "top": e["stocks"][:5]}
        for label, (caps, pday) in prev_caps.items():
            p = caps.get(g)
            row[label] = round((e["cap"] / p - 1) * 100, 2) if p else None
        groups.append(row)
    groups.sort(key=lambda r: -r["cap"])
    for i, r in enumerate(groups, 1):
        r["rank"] = i
    out = {"date": day.isoformat(), "generated_at": dt.datetime.now(KST).isoformat(timespec="minutes"),
           "compare": {k: (v[1].isoformat() if v[1] else None) for k, v in prev_caps.items()},
           "source": "금융위원회 주식시세정보(공공데이터포털)", "groups": groups}
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "rank.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{day} 그룹 {len(groups)}곳 순위 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
