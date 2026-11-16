"""오늘의 재벌 동향 — DART '오늘의 공시' 목록에서 주요 그룹 계열사 공시만 골라 data/today.json 을 만든다.

사용:
    python tools/update_today.py                # 가장 최근 공시일(오늘부터 거꾸로 7일 안)
    python tools/update_today.py --date 2026-11-13

출처: 금융감독원 전자공시시스템(DART) 공시 목록 https://dart.fss.or.kr/dsac001/mainAll.do
API 키 없이 공개 목록만 읽는다. 요청 사이에 1초씩 쉰다.
그룹 판정은 회사명 규칙으로 하므로 틀릴 수 있다(화면에 그렇게 밝힌다).
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://dart.fss.or.kr/dsac001/search.ax"
UA = "Mozilla/5.0 (compatible; chaebol-archive-daily/1.0)"
KST = dt.timezone(dt.timedelta(hours=9))

# 그룹명은 사이트(공정위 명단) 표기를 따른다. 동명 회사가 많은 브랜드는 회사명을 직접 적었다.
GROUP_RULES = [
    ("삼성", r"^(삼성(전자|물산|SDI|에스디아이|전기|SDS|에스디에스|생명|화재|증권|카드|중공업|E&A|이앤에이|바이오로직스|바이오에피스|디스플레이|자산운용|웰스토리|메디슨|라이온즈|벤처투자|액티브자산운용|선물|생명서비스)|제일기획|에스원|호텔신라|멀티캠퍼스|시큐아이)"),
    ("에스케이", r"^(SK|에스케이)(?!증권)"),
    ("현대자동차", r"^(현대자동차|현대차|기아|현대모비스|현대글로비스|현대제철|현대건설|현대엔지니어링|현대오토에버|현대위아|현대로템|현대트랜시스|현대케피코|현대캐피탈|현대카드|현대커머셜|현대비앤지스틸|이노션)"),
    ("HD현대", r"^((HD|에이치디)(현대|한국조선해양)|현대(중공업|미포|삼호|오일뱅크|일렉트릭|건설기계|인프라코어))"),
    ("엘지", r"^(LG|엘지)"),
    ("LX", r"^(LX|엘엑스)"),
    ("지에스", r"^(GS|지에스)"),
    ("엘에스", r"^(LS|엘에스)(?!증권)"),
    ("한화", r"^한화"),
    ("롯데", r"^롯데"),
    ("신세계", r"^(신세계|이마트|에스에스지닷컴|SSG닷컴)"),
    ("씨제이", r"^(CJ|씨제이)"),
    ("두산", r"^두산"),
    ("카카오", r"^카카오"),
    ("네이버", r"^(NAVER|네이버)"),
    ("셀트리온", r"^셀트리온"),
    ("효성", r"^(효성|HS효성)"),
    ("HDC", r"^(HDC|에이치디씨)"),
    ("코오롱", r"^코오롱"),
    ("한진", r"^(한진칼|대한항공|진에어|한국공항|정석기업|아시아나항공|\(주\)한진$|한진$)"),
    ("금호석유화학", r"^(금호석유|금호미쓰이|금호피앤비)"),
    ("영풍", r"^(영풍|고려아연|코리아써키트|인터플렉스)"),
    ("포스코", r"^(POSCO|포스코)"),
    ("케이티", r"^(KT|케이티)(?!&G|앤지)"),
    ("농심", r"^농심"),
    ("태광", r"^(태광산업|흥국생명|흥국화재|대한화섬)"),
    ("DB", r"^DB"),
    ("현대백화점", r"^(현대백화점|현대홈쇼핑|현대그린푸드|현대리바트|한섬|현대이지웰|현대지에프)"),
    ("OCI", r"^OCI"),
    ("하이브", r"^하이브"),
    ("쿠팡", r"^쿠팡"),
    ("중흥건설", r"^(중흥|대우건설)"),
    ("아모레퍼시픽", r"^아모레"),
    ("HL", r"^HL"),
    ("KCC", r"^(KCC|케이씨씨)"),
    ("하이트진로", r"^하이트진로"),
    ("F&F", r"^(F&F|에프앤에프)"),
]
GROUP_RULES = [(g, re.compile(p)) for g, p in GROUP_RULES]

# 보고서명 → 분류. 위에서부터 먼저 맞는 것.
CATS = [
    ("stake",  r"임원ㆍ주요주주특정증권등소유상황보고서|최대주주등소유주식변동신고서|주식등의대량보유상황보고서|특수관계인의주식|특수관계인으로부터의주식|특수관계인에대한주식|주식등의 대량보유"),
    ("gov",    r"최대주주변경|회사합병결정|회사분할결정|회사분할합병결정|주식교환|주식이전|공개매수|자기주식(취득|처분|소각)|지주회사|의결권|계열회사의 편입|계열회사의 제외"),
    ("deal",   r"타법인주식및출자증권(취득|처분)결정|영업(양수|양도)결정|유형자산(양수|양도)결정|신규시설투자|자산양수도|투자판단관련주요경영사항|합작"),
    ("exec",   r"대표이사|대표집행임원|사외이사의선임|임원ㆍ주요주주 변동|임원의 변동"),
    ("biz",    r"단일판매ㆍ공급계약|유상증자결정|무상증자결정|소송등의|횡령ㆍ배임|조회공시|공정공시"),
]
CATS = [(c, re.compile(p)) for c, p in CATS]
SKIP = re.compile(r"계열회사등과의상품ㆍ용역거래|대규모기업집단현황공시|특수관계인에대한(자금대여|담보제공|채무보증|출자)|특수관계인과의|감사보고서|기업설명회|주주총회소집|증권발행실적|투자설명서|일괄신고|분기보고서|반기보고서|사업보고서|기업지배구조보고서|결산실적|영업\(잠정\)실적|매출액또는손익구조")


def owner_names():
    """사이트 데이터(GENERATIONS)에 등록된 오너 일가 이름."""
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    m = re.search(r"const GENERATIONS = \[(.*?)\n\];", src, re.S)
    block = m.group(1) if m else ""
    return set(re.findall(r'name:"([^"]{2,4})"', block))


def fetch_page(day, page):
    body = urllib.parse.urlencode({
        "currentPage": page, "maxResults": 100, "maxLinks": 10, "sort": "", "series": "",
        "pageGrouping": "A", "mdayCnt": 0, "selectDate": day.strftime("%Y.%m.%d"), "textCrpNm": "",
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
TAG = re.compile(r"<[^>]+>")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", s))).strip()


def parse(page_html):
    rows = []
    for r in ROW.findall(page_html):
        rcp = re.search(r"rcpNo=(\d{14})", r)
        corp = re.search(r"openCorpInfoNew\('(\d+)'.*?title=\"(.*?) 기업개황", r, re.S)
        if not rcp or not corp:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(tds) < 5:
            continue
        mk = re.search(r'tagCom_(\w+)"', tds[1])
        report = clean(tds[2])
        rows.append({
            "time": clean(tds[0]),
            "corp": html.unescape(corp.group(2)).strip(),
            "corp_code": corp.group(1),
            "market": {"kospi": "유가", "kosdaq": "코스닥", "konex": "코넥스"}.get(mk.group(1) if mk else "", "기타"),
            "report": report.replace("[기재정정]", "").strip(),
            "correction": "[기재정정]" in report,
            "rcpNo": rcp.group(1),
            "filer": clean(tds[3]),
        })
    total = re.search(r'id="txtCB">([\d,]+)</span>', page_html)
    return rows, int(total.group(1).replace(",", "")) if total else 0


def group_of(name):
    for g, rx in GROUP_RULES:
        if rx.search(name):
            return g
    return None


def classify(report):
    if SKIP.search(report):
        return None
    for c, rx in CATS:
        if rx.search(report):
            return c
    return None


def collect(day):
    rows, total = [], None
    page = 1
    while True:
        got, tot = parse(fetch_page(day, page))
        total = tot if total is None else total
        rows += got
        if not got or len(rows) >= total or page > 40:
            break
        page += 1
        time.sleep(1)
    return rows, total or 0


def build(day, rows, total, owners):
    items = []
    for r in rows:
        g = group_of(r["corp"])
        if not g:
            continue
        c = classify(r["report"])
        if not c:
            continue
        owner = r["filer"] in owners
        # 임원 개인의 소유 보고는 오너 일가일 때만 남긴다(일반 임원은 잡음)
        if c == "stake" and "임원ㆍ주요주주" in r["report"] and not owner:
            continue
        r.update(group=g, cat=c, owner=owner)
        items.append(r)
    items.sort(key=lambda x: (x["time"]), reverse=True)
    return {
        "date": day.isoformat(),
        "generated_at": dt.datetime.now(KST).isoformat(timespec="minutes"),
        "source": "금융감독원 전자공시시스템(DART) 오늘의 공시",
        "source_url": "https://dart.fss.or.kr/dsac001/mainAll.do",
        "total_disclosures": total,
        "items": items,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    a = ap.parse_args()
    owners = owner_names()
    if a.date:
        days = [dt.date.fromisoformat(a.date)]
    else:
        today = dt.datetime.now(KST).date()
        days = [today - dt.timedelta(days=i) for i in range(7)]
    for day in days:
        rows, total = collect(day)
        if rows:
            break
        time.sleep(1)
    else:
        print("최근 7일 공시 없음", file=sys.stderr)
        return 1
    out = build(day, rows, total, owners)
    data = ROOT / "data"
    (data / "archive").mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, ensure_ascii=False, indent=1)
    (data / "today.json").write_text(text, encoding="utf-8")
    (data / "archive" / f"{day.isoformat()}.json").write_text(text, encoding="utf-8")
    days_saved = sorted((p.stem for p in (data / "archive").glob("????-??-??.json")), reverse=True)
    (data / "archive" / "index.json").write_text(json.dumps(days_saved[:60]), encoding="utf-8")
    print(f"{day} 전체 {total}건 중 그룹 공시 {len(out['items'])}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
