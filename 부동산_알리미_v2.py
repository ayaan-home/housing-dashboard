#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏠 부동산 소식 알리미 v2
- 누락 없는 완전 수집 (전체 페이지 + 다중 소스)
- 신규 공고 자동 감지 (이전 수집 데이터와 비교)
- 대시보드에 신규 건수 + NEW 배지 명확히 표시

실행: python3 부동산_알리미_v2.py
"""

import requests
from bs4 import BeautifulSoup
import json
import hashlib
import os
import time
from datetime import datetime

# ══════════════════════════════════════════════
# ⚙️ 설정
# ══════════════════════════════════════════════
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TODAY       = datetime.today().strftime("%Y%m%d")
DASH_FILE   = os.path.join(BASE_DIR, "부동산_대시보드.html")
DEPLOY_DIR  = os.path.join(BASE_DIR, ".deploy")             # GitHub Pages 배포 폴더
DASH_URL    = "https://ayaan-home.github.io/housing-dashboard/"  # 공개 대시보드 URL
SEEN_FILE   = os.path.join(BASE_DIR, "seen_notices.json")   # 신규 감지용
LOG_FILE    = os.path.join(BASE_DIR, "수집로그.txt")

TARGET_REGIONS   = ["서울", "경기", "인천", "전국"]
HIGHLIGHT_KW     = ["신혼", "행복주택", "통합공공임대", "생애최초", "국민임대", "매입임대", "청년"]
PRIORITY_MAP     = {
    "통합공공임대": 0, "국민임대": 0, "행복주택(신혼희망)": 0,
    "공공분양(신혼희망)": 0, "이익공유형 공공분양주택": 1,
    "공공분양(국민)": 1,
    "행복주택": 1, "매입임대": 1, "장기전세": 1, "6년 공공임대주택": 1,
    "전세임대": 2, "공공임대": 2, "집주인임대": 2, "분양주택": 2,
    "공공지원민간임대": 2,
    "민간분양(APT)": 3, "민간분양": 3,
    "영구임대": 3,
}
PRIORITY_LABEL   = {0: "🔴 최고", 1: "🟠 높음", 2: "🟡 보통", 3: "⚪ 낮음"}

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 마이홈포털 공공데이터 API
MYHOME_API_KEY  = os.environ.get("MYHOME_API_KEY", "")   # 시크릿: 환경변수에서만 (public 레포 유출 방지)
MYHOME_API_BASE      = "https://apis.data.go.kr/1613000/HWSPR02"  # 청약공고
MYHOME_API_WAIT_BASE = "https://apis.data.go.kr/1613000/HWSPR03"  # 대기현황
MYHOME_API_CPLX_BASE = "https://apis.data.go.kr/1613000/HWSPR04"  # 단지정보

# ── Supabase(Postgres) 연동 ────────────────────────────────────
#  SUPABASE_DB_URL(env)이 있으면 신규감지(seen_notices)·단지정보캐시(kv_cache)를 DB로 영속화.
#  없으면 기존 로컬 JSON 파일 방식으로 동작(로컬 호환).
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

def _db_conn():
    """Supabase Postgres 연결. Transaction pooler(6543) 안전모드:
    autocommit + prepared statement 비활성(pgBouncer 트랜잭션 모드 호환).
    psycopg 미설치/URL 미설정 시 None 반환(파일 폴백)."""
    if not SUPABASE_DB_URL:
        return None
    try:
        import psycopg
        return psycopg.connect(SUPABASE_DB_URL, autocommit=True, prepare_threshold=None)
    except Exception as e:
        try:
            log(f"  ⚠ Supabase 연결 실패 → 파일 폴백: {e}")
        except Exception:
            pass
        return None

# 서울 25개 구 signguCode (3자리)
SEOUL_SIGNGU = {
    '종로구':110,'중구':140,'용산구':170,'성동구':200,'광진구':215,
    '동대문구':230,'중랑구':260,'성북구':290,'강북구':305,'도봉구':320,
    '노원구':350,'은평구':380,'서대문구':410,'마포구':440,'양천구':470,
    '강서구':500,'구로구':530,'금천구':545,'영등포구':560,'동작구':590,
    '관악구':620,'서초구':650,'강남구':680,'송파구':710,'강동구':740,
}
# 경기 주요 시군 signguCode (3자리)
GYEONGGI_SIGNGU = {
    '수원시 장안구':111,'수원시 권선구':113,'수원시 팔달구':115,'수원시 영통구':117,
    '성남시 수정구':131,'성남시 중원구':133,'성남시 분당구':135,
    '의정부시':150,'안양시 만안구':171,'안양시 동안구':173,
    '부천시':192,'광명시':210,'평택시':220,
    '안산시 상록구':271,'안산시 단원구':273,
    '고양시 덕양구':281,'고양시 일산동구':285,'고양시 일산서구':287,
    '구리시':310,'남양주시':360,'오산시':370,'시흥시':390,
    '군포시':410,'의왕시':430,'하남시':450,
    '용인시 처인구':461,'용인시 기흥구':463,'용인시 수지구':465,
    '파주시':480,'이천시':500,'김포시':570,'화성시':590,'광주시':610,'양주시':630,
}

# 단지정보 캐시 파일 (7일 유효)
COMPLEX_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "단지정보_캐시.json") if 'BASE_DIR' in dir() else "단지정보_캐시.json"

# ══════════════════════════════════════════════
# 🔧 공통 유틸
# ══════════════════════════════════════════════
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def is_target(region: str) -> bool:
    return any(r in (region or "") for r in TARGET_REGIONS)

def get_priority(type_text: str):
    for k, v in PRIORITY_MAP.items():
        if k in (type_text or ""):
            return v, PRIORITY_LABEL[v]
    return 3, "⚪ 낮음"

def is_highlighted(title: str, type_text: str) -> bool:
    txt = (title or "") + (type_text or "")
    return any(k in txt for k in HIGHLIGHT_KW)

# ── 공급대상 계층 (특별공급 대상) ──────────────────────────────
# (태그, 이모지, 청약홈 Mdl 필드, 제목·유형 키워드들)  — 표시 순서대로
# ※ Mdl 필드명·의미는 공식 명세로 검증: 청약홈 분양정보 조회 서비스 Swagger api-docs
#   (https://infuser.odcloud.kr/api/stages/37000/api-docs, getAPTLttotPblancMdl 응답)
#   NWBB=특별공급-신생아, YGMN=특별공급-청년, NWWDS=신혼부부, LFE_FRST=생애최초,
#   MNYCH=다자녀가구, OLD_PARNTS_SUPORT=노부모부양 세대수
TARGET_LAYERS = [
    ("신생아",   "👶", "NWBB_HSHLDCO",             ["신생아"]),
    ("청년",     "🧑", "YGMN_HSHLDCO",             ["청년", "역세권청년"]),
    ("신혼부부", "💑", "NWWDS_HSHLDCO",            ["신혼", "신혼부부", "신혼희망"]),
    ("생애최초", "🌱", "LFE_FRST_HSHLDCO",         ["생애최초", "생애 최초", "생초"]),
    ("다자녀",   "👪", "MNYCH_HSHLDCO",            ["다자녀"]),
    ("노부모",   "👵", "OLD_PARNTS_SUPORT_HSHLDCO", ["노부모", "노부모부양", "고령자"]),
]
LAYER_EMOJI = {tag: emoji for tag, emoji, _, _ in TARGET_LAYERS}
_LAYER_ORDER = [tag for tag, _, _, _ in TARGET_LAYERS]

def layers_from_text(title: str, type_text: str) -> list[str]:
    """공고명·유형 텍스트에서 공급대상 계층 키워드 감지 (Mdl 데이터 없는 소스용 폴백)."""
    txt = f"{title or ''} {type_text or ''}"
    found = []
    for tag, _, _, kws in TARGET_LAYERS:
        if any(k in txt for k in kws):
            found.append(tag)
    return found

def layers_from_mdl(mdl_rows: list[dict]) -> list[str]:
    """청약홈 주택형별(Mdl) 행들을 합산해 특공 물량>0인 계층 태그 반환 (정확).
    + SPSPLY_HSHLDCO(특공 합계)는 명세 일관성 검증용 (6계층 합 ≤ SPSPLY 가 정상).
       — 노출하지 않음. 불일치 시 stderr 경고.
    참고: 청약홈 분양정보 조회 서비스 공식 명세 (15098547 표#23 APT 주택형별 응답)
       .deploy/docs/api-spec/공식문서/15098547_청약홈_기술문서.docx"""
    totals = {field: 0 for _, _, field, _ in TARGET_LAYERS}
    spsply_total = 0  # 명세: SPSPLY_HSHLDCO = 6계층 + 기관추천 + 기타 + 이전기관 합
    for row in mdl_rows:
        for _, _, field, _ in TARGET_LAYERS:
            try:
                totals[field] += int(row.get(field) or 0)
            except (TypeError, ValueError):
                pass
        try:
            spsply_total += int(row.get("SPSPLY_HSHLDCO") or 0)
        except (TypeError, ValueError):
            pass
    six_sum = sum(totals.values())
    if spsply_total > 0 and six_sum > spsply_total:
        try:
            log(f"  ⚠ Mdl 합계 검증: 6계층합({six_sum}) > SPSPLY({spsply_total}) — 명세 확인 필요")
        except NameError:
            pass
    return [tag for tag, _, field, _ in TARGET_LAYERS if totals[field] > 0]

def merge_layers(*layer_lists) -> list[str]:
    """여러 출처의 계층 리스트를 표준 순서로 합집합."""
    s = set()
    for lst in layer_lists:
        s.update(lst or [])
    return [tag for tag in _LAYER_ORDER if tag in s]

def layer_badges_html(layers: list[str], verified: bool = True) -> str:
    """대시보드용 계층 배지 HTML.
    - 계층 있음 → 배지 표시
    - 계층 없음 + 미확인 출처(비청약홈) → '❓특공 미확인' 표시
    - 계층 없음 + 확인됨(청약홈, 특공 0) → 표시 없음"""
    if layers:
        return "".join(
            f'<span class="layer-badge">{LAYER_EMOJI.get(t,"")}{t}</span>' for t in layers
        )
    if not verified:
        return '<span class="layer-badge layer-unknown">❓특공 미확인</span>'
    return ""

def layer_badges_slack(layers: list[str], verified: bool = True) -> str:
    """슬랙용 계층 배지 (이모지+태그, 백틱). 예: ` 👶신생아` ` 🧑청년`
    계층 없음 + 미확인 출처면 ` ❓특공 미확인` 표시."""
    if layers:
        return " " + " ".join(f"`{LAYER_EMOJI.get(t,'')}{t}`" for t in layers)
    if not verified:
        return " `❓특공 미확인`"
    return ""

def format_price_eok(amounts) -> str:
    """만원 단위 금액 리스트 → '3.9~6.7억' / '5.7억'. 유효값 없으면 ''."""
    a = []
    for x in (amounts or []):
        try:
            v = int(x)
            if v > 0:
                a.append(v)
        except (TypeError, ValueError):
            pass
    if not a:
        return ""
    lo, hi = min(a) / 10000, max(a) / 10000
    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{f(lo)}억" if lo == hi else f"{f(lo)}~{f(hi)}억"

def price_badge_slack(item: dict) -> str:
    """슬랙 가격 태그 (유형 뒤에 배치).
    - 직접값(API/Mdl): `💰3.9~6.7억` (확정)
    - 추정값(캐시 P25~P75): `📊보증금... (추정)` (시세 통계)
    - 없음: `💰?` (가격정보 없음). 항상 뒤에 공백."""
    p = (item.get("가격") or "").strip()
    if not p:
        return "`💰?` "
    if not item.get("가격_직접"):
        return f"`📊{p} (추정)` "
    return f"`💰{p}` "

def notice_key(item: dict) -> str:
    """신규 감지용 고유 키 (공고명+출처 해시)"""
    raw = f"{item.get('출처','')}|{item.get('공고명','').strip()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]

def _make_old_ssl_session() -> requests.Session:
    """구형 SSL(SSLv3/TLS1.0) 사이트용 세션 (GH 등)"""
    import ssl
    import urllib3
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.ssl_ import create_urllib3_context
        class _OldSSLAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                ctx = create_urllib3_context()
                ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                kwargs["ssl_context"] = ctx
                super().init_poolmanager(*args, **kwargs)
            def proxy_manager_for(self, proxy, **proxy_kwargs):
                ctx = create_urllib3_context()
                ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                proxy_kwargs["ssl_context"] = ctx
                return super().proxy_manager_for(proxy, **proxy_kwargs)
    except Exception:
        _OldSSLAdapter = HTTPAdapter  # fallback
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    s = requests.Session()
    s.mount("https://", _OldSSLAdapter())
    return s

def fetch(url, retries=3, delay=1.0, verify=True, old_ssl=False) -> BeautifulSoup | None:
    import urllib3
    if not verify or old_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = _make_old_ssl_session() if old_ssl else requests.Session()
    for i in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=15, verify=(False if old_ssl else verify))
            r.raise_for_status()
            r.encoding = "utf-8"
            return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            log(f"  GET 재시도{i+1} {url[:60]}… {e}")
            time.sleep(delay)
    return None

def post_fetch(url, data, retries=3, delay=1.0) -> BeautifulSoup | None:
    for i in range(retries):
        try:
            r = requests.post(url, data=data, headers=HEADERS, timeout=15)
            r.raise_for_status()
            r.encoding = "utf-8"
            return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            log(f"  POST 재시도{i+1} {url[:60]}… {e}")
            time.sleep(delay)
    return None

# ── 공고유형 분류 ──────────────────────────────────────────
# 우선순위 순으로 매칭 (앞 항목이 먼저 적용)
NOTICE_TYPE_RULES = [
    # 🟢 모집공고
    ("🟢 모집공고", ["모집공고", "입주자 모집", "예비입주자 모집", "입주자모집",
                    "예비입주자모집", "모집 공고", "청약공고", "공급공고",
                    "사전청약", "본청약", "공고🆕", "공고 🆕"]),
    # 🔵 당첨자·배정
    ("🔵 당첨·배정", ["당첨자", "동호배정", "예비입주대상자", "입주대상자",
                     "당첨결과", "배정결과", "배정 결과", "예비자 발표",
                     "예비자발표", "당첨자발표", "예비입주자 발표",
                     "경쟁률", "청약접수 결과", "청약경쟁률"]),
    # 🟡 계약·서류
    ("🟡 계약·서류", ["계약안내", "계약결과", "계약 결과", "계약 안내",
                     "서류심사대상자", "서류 심사", "서류제출",
                     "입주자격 심사결과", "입주자격 심사서류",
                     "입주 안내문", "입주안내문", "계약대상자"]),
    # ⚪ 행정공지
    ("⚪ 행정공지", ["홈페이지", "서비스 중단", "전산작업", "서비스 이용",
                    "준공인가증", "주택공개", "사전점검", "재계약",
                    "이전등기", "분할납부제", "공사 시스템", "시행",
                    "변경사항 안내", "잠실르엘", "입주 안내"]),
]
NOTICE_TYPE_DEFAULT = "🔵 당첨·배정"   # 분류 안 된 것 기본값

def classify_notice(title: str) -> str:
    """공고 제목 분류. 여러 키워드가 있으면 '가장 뒤(오른쪽)'에 나오는 키워드 기준.
    한국어 공고는 보통 맨 뒤에 실제 액션이 오기 때문
    (예: '...입주자 모집공고 ... 당첨자 발표' → 당첨·배정).
    위치가 같으면 NOTICE_TYPE_RULES 순서(앞 항목)가 우선."""
    t = title.strip()
    best_pos   = -1
    best_label = None
    for label, keywords in NOTICE_TYPE_RULES:
        for kw in keywords:
            pos = t.rfind(kw)
            if pos > best_pos:           # 더 뒤에 있는 키워드가 이김
                best_pos   = pos
                best_label = label
    return best_label if best_label is not None else NOTICE_TYPE_DEFAULT

def make_item(cat, src, type_, title, region, post_date, deadline, status, views="", link=""):
    pri_num, pri_label = get_priority(type_)
    return {
        "카테고리":    cat,
        "출처":        src,
        "유형":        type_,
        "공고유형분류": classify_notice(title),   # 🟢모집공고 / 🔵당첨·배정 / 🟡계약·서류 / ⚪행정공지
        "공고명":      title.strip(),
        "지역":        region,
        "게시일":      post_date,
        "마감일":      deadline,
        "상태":        status,
        "조회수":      views,
        "우선순위_숫":  pri_num,
        "우선순위":    pri_label,
        "신혼생초":    is_highlighted(title, type_),
        "대상계층":    layers_from_text(title, type_),   # 공급대상 계층 (청약홈은 Mdl로 override)
        "대상계층_확인": False,   # 특공 계층 확인 여부 (청약홈 Mdl 조회 시 True, 그 외 키워드 추정)
        "가격":        "",        # 분양가 등 (청약홈 Mdl에서 채움). 예: '3.9~6.7억'
        "가격_직접":   False,     # True=API 직접값(마이홈 rentGtn 등), False=캐시 P25~P75 추정
        "링크":        link,
        "is_new":      False,   # 나중에 감지 단계에서 업데이트
    }

def _lh_detail_link(title_cell, mi: str) -> str:
    """LH 목록 제목 셀의 <a data-id1~4> → 개별 공고 상세 URL.
    data-id 없으면 목록 URL로 폴백."""
    base = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc"
    a = title_cell.find("a") if title_cell else None
    if a and a.get("data-id1"):
        return (f"{base}/selectWrtancInfo.do"
                f"?panId={a.get('data-id1','')}"
                f"&ccrCnntSysDsCd={a.get('data-id2','')}"
                f"&uppAisTpCd={a.get('data-id3','')}"
                f"&aisTpCd={a.get('data-id4','')}&mi={mi}")
    return f"{base}/selectWrtancList.do?mi={mi}"

import re as _re_corr
# 앞쪽 [정정공고]/[정정]/[재공고]/[연장공고] 류 prefix (반복 포함)
_CORRECTION_RE = _re_corr.compile(r'^\s*(?:\[(?:정정공고|정정|재공고|연장공고|변경공고)\]\s*)+')

def normalize_notice_title(title: str) -> str:
    """[정정공고] 류 prefix + 🆕 제거 → 정규화 제목 (정정공고 변형 그룹핑용)"""
    t = _CORRECTION_RE.sub("", title or "")
    return t.replace("🆕", "").strip()

def _correction_rank(d: dict):
    """정정공고 최신도 키: (정정 횟수, 게시일). 클수록 최신본."""
    title = d.get("공고명", "") or ""
    m = _CORRECTION_RE.match(title)
    corr = title[:m.end()].count("정정") if m else 0
    return (corr, d.get("게시일", "") or "")

# ══════════════════════════════════════════════
# 📡 수집 1: LH청약플러스 — 임대주택 전체
# ══════════════════════════════════════════════
def scrape_lh_rental() -> list[dict]:
    import re
    log("\n▶ [1/5] LH 임대주택 — 전체 페이지 수집")
    results, page = [], 1
    base = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do"
    MAX_PAGES = 20          # 안전장치: 최대 20페이지 (100건×20=2000건)
    prev_titles: set = set()  # 중복 페이지 감지용

    while page <= MAX_PAGES:
        url = f"{base}?mi=1026&pageIndex={page}&recordCountPerPage=100"
        soup = fetch(url)
        if not soup:
            log(f"  ⚠ 페이지{page} 접근 실패 — 중단")
            break

        table = soup.find("table")
        if not table:
            log(f"  ⚠ 페이지{page} 테이블 없음 — 중단")
            break

        rows = table.find_all("tr")[1:]
        found = 0
        page_titles: set = set()
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 8:
                continue
            type_   = cols[1].get_text(strip=True)
            title   = cols[2].get_text(strip=True).replace("1일전","🆕").strip()
            region  = cols[3].get_text(strip=True)
            post_dt = cols[5].get_text(strip=True)
            ddl     = cols[6].get_text(strip=True)
            status  = cols[7].get_text(strip=True)
            views   = cols[8].get_text(strip=True) if len(cols) > 8 else ""

            if not title:
                continue
            page_titles.add(title)
            if not is_target(region):
                continue

            results.append(make_item(
                "장기임대", "LH청약플러스", type_, title, region,
                post_dt, ddl, status, views,
                _lh_detail_link(cols[2], "1026")
            ))
            found += 1

        log(f"  페이지{page}: 수도권 {found}건 (전체행 {len(page_titles)}건)")

        # ① 빈 페이지 → 종료
        if len(page_titles) == 0:
            break

        # ② 총 건수 파싱으로 마지막 페이지 확인
        total = None
        for tag in soup.find_all(string=re.compile(r'\d')):
            m = re.search(r'전체\s*([\d,]+)\s*건', tag)
            if m:
                total = int(m.group(1).replace(",", ""))
                break
        if total is not None and page * 100 >= total:
            log(f"  → 총 {total}건 완료")
            break

        # ③ 중복 페이지 감지 (사이트가 마지막 페이지를 반복 리턴하는 경우)
        if page_titles == prev_titles:
            log(f"  → 중복 페이지 감지 — 수집 완료")
            break

        prev_titles = page_titles
        page += 1
        time.sleep(0.7)

    if page > MAX_PAGES:
        log(f"  ⚠ 최대 페이지({MAX_PAGES}) 도달 — 강제 종료")

    log(f"  ✅ LH 임대 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 2: LH청약플러스 — 공공분양 전체
# ══════════════════════════════════════════════
def scrape_lh_sale() -> list[dict]:
    import re
    log("\n▶ [2/5] LH 공공분양 — 전체 페이지 수집")
    results, page = [], 1
    base = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do"
    MAX_PAGES = 20
    prev_titles: set = set()

    while page <= MAX_PAGES:
        url = f"{base}?mi=1027&pageIndex={page}&recordCountPerPage=100"
        soup = fetch(url)
        if not soup:
            break

        table = soup.find("table")
        if not table:
            break
        rows = table.find_all("tr")[1:]
        found = 0
        page_titles: set = set()
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 8:
                continue
            type_   = cols[1].get_text(strip=True)
            title   = cols[2].get_text(strip=True).replace("1일전","🆕").strip()
            region  = cols[3].get_text(strip=True)
            post_dt = cols[5].get_text(strip=True)
            ddl     = cols[6].get_text(strip=True)
            status  = cols[7].get_text(strip=True)
            views   = cols[8].get_text(strip=True) if len(cols) > 8 else ""
            if not title:
                continue
            page_titles.add(title)
            if not is_target(region):
                continue
            results.append(make_item(
                "청약·공공분양", "LH청약플러스", type_, title, region,
                post_dt, ddl, status, views,
                _lh_detail_link(cols[2], "1027")
            ))
            found += 1

        log(f"  페이지{page}: 수도권 {found}건 (전체행 {len(page_titles)}건)")

        if len(page_titles) == 0:
            break

        total = None
        for tag in soup.find_all(string=re.compile(r'\d')):
            m = re.search(r'전체\s*([\d,]+)\s*건', tag)
            if m:
                total = int(m.group(1).replace(",", ""))
                break
        if total is not None and page * 100 >= total:
            log(f"  → 총 {total}건 완료")
            break

        if page_titles == prev_titles:
            log(f"  → 중복 페이지 감지 — 수집 완료")
            break

        prev_titles = page_titles
        page += 1
        time.sleep(0.7)

    log(f"  ✅ LH 분양 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 3: 마이홈포털 — 서울+경기 임대공고 (공공데이터포털 OpenAPI)
# ══════════════════════════════════════════════
def _myhome_type_from_rent(rentSecdNm: str) -> str:
    """임대유형명 → 내부 유형 매핑"""
    r = rentSecdNm or ""
    if "통합공공임대" in r or "통합" in r: return "통합공공임대"
    if "국민임대" in r:                     return "국민임대"
    if "행복주택" in r:                     return "행복주택"
    if "매입임대" in r:                     return "매입임대"
    if "전세임대" in r:                     return "전세임대"
    if "영구임대" in r:                     return "영구임대"
    if "장기전세" in r:                     return "장기전세"
    if r:                                   return r
    return "공공임대"

def _myhome_type_from_house(houseTy: str) -> str:
    """분양 주택유형 → 내부 유형 매핑"""
    h = houseTy or ""
    if "신혼" in h:   return "공공분양(신혼희망)"
    if "생애" in h:   return "공공분양(생애최초)"
    if "일반" in h:   return "공공분양"
    if h:             return h
    return "공공분양"

def _fetch_myhome_api(endpoint: str, brtc_code: str, brtc_name: str) -> list[dict]:
    """마이홈포털 API 한 엔드포인트·한 지역 전체 페이지 수집"""
    raw_items = []
    page = 1
    url = f"{MYHOME_API_BASE}/{endpoint}"
    while True:
        params = {
            "serviceKey": MYHOME_API_KEY,
            "brtcCode":   brtc_code,
            "pageNo":     page,
            "numOfRows":  100,
            "type":       "json",
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            resp = r.json().get("response", {})
            rc   = resp.get("header", {}).get("resultCode", "00")
            msg  = resp.get("header", {}).get("resultMsg", "")
            if rc not in ("00", "0000"):
                log(f"  ⚠ {brtc_name} [{endpoint}] 제공기관 오류 [{rc}] {msg}")
                break
            body  = resp.get("body", {})
            total = int(body.get("totalCount", 0))
            items = body.get("item", [])
            if isinstance(items, dict):   # 1건이면 dict로 옴
                items = [items]
            if not items:
                break
            raw_items.extend(items)
            log(f"    {brtc_name} p{page}: {len(items)}건 수집 (전체 {total}건)")
            if page * 100 >= total:
                break
            page += 1
            time.sleep(0.4)
        except Exception as e:
            log(f"  ⚠ {brtc_name} [{endpoint}] p{page} 오류: {e}")
            break
    return raw_items

def _fmt_ymd(s: str) -> str:
    """'20260515' → '2026-05-15'. 형식 안 맞으면 원본 반환."""
    s = (s or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s

def scrape_myhome() -> list[dict]:
    """마이홈포털 임대공고 — OpenAPI rsdtRcritNtcList.
    signguNm(구)·fullAdres(주소)·endDe(마감)·url(실링크) 제공."""
    from datetime import timedelta
    log("\n▶ [3/5] 마이홈포털 API — 서울+경기 임대공고")
    results = []
    CUTOFF = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")

    for brtc_code, brtc_name in [("11", "서울특별시"), ("41", "경기도")]:
        items = _fetch_myhome_api("rsdtRcritNtcList", brtc_code, brtc_name)
        for it in items:
            title = (it.get("pblancNm") or "").strip()
            if not title:
                continue
            post_dt = _fmt_ymd(it.get("rcritPblancDe") or "")
            if post_dt and post_dt < CUTOFF:        # 60일 초과 공고 제외
                continue
            brtcNm   = it.get("brtcNm") or brtc_name
            signguNm = (it.get("signguNm") or "").strip()
            region   = f"{brtcNm} {signguNm}".strip() if signguNm else brtcNm
            type_    = (it.get("suplyTyNm") or "").strip() or "공공임대"
            deadline = _fmt_ymd(it.get("endDe") or it.get("przwnerPresnatnDe") or "")
            link     = (it.get("url") or "").strip() or "https://www.myhome.go.kr"
            item = make_item(
                "장기임대", "마이홈포털", type_, title, region,
                post_dt, deadline, "모집중", "", link
            )
            # 💰 직접 가격 (HWSPR02 rentGtn=보증금, mtRntchrg=월임대료 — 원 단위 가정, 단지정보와 동일 패밀리)
            try:
                bo = int(it.get("rentGtn") or 0)
                wo = int(it.get("mtRntchrg") or 0)
            except (TypeError, ValueError):
                bo, wo = 0, 0
            parts = []
            if bo > 0: parts.append(f"보증금{_fmt_won_to_man(bo)}")
            if wo > 0: parts.append(f"월{_fmt_won_to_man(wo)}")
            if parts:
                item["가격"] = " / ".join(parts)
                item["가격_직접"] = True
            results.append(item)

    log(f"  ✅ 마이홈포털 임대 완료: {len(results)}건")
    return results

def scrape_myhome_sale() -> list[dict]:
    """마이홈포털 분양공고 — 공공데이터포털 OpenAPI (ltRsdtRcritNtcList)"""
    log("\n▶ [3b] 마이홈포털 API — 서울+경기 분양공고")
    results = []
    PORTAL_LIST = "https://www.myhome.go.kr/hws/portal/sch/selectRsdtRcritNtcView.do"

    for brtc_code, brtc_name in [("11", "서울특별시"), ("41", "경기도")]:
        items = _fetch_myhome_api("ltRsdtRcritNtcList", brtc_code, brtc_name)
        for it in items:
            pbancNm  = (it.get("pbancNm") or "").strip()
            if not pbancNm:
                continue
            brtcNm   = it.get("brtcNm") or brtc_name
            signguNm = it.get("signguNm") or ""
            region   = f"{brtcNm} {signguNm}".strip() if signguNm else brtcNm
            houseTy  = it.get("houseTy") or ""
            type_    = _myhome_type_from_house(houseTy)
            pbancDe  = it.get("pbancDe") or ""
            deadline = it.get("przwnerPresentnDe") or it.get("rcritPblancDe") or ""
            item = make_item(
                "청약·공공분양", "마이홈포털", type_, pbancNm, region,
                pbancDe, deadline, "모집중", "", PORTAL_LIST
            )
            # 💰 직접 분양가 (HWSPR02 enty=계약금, prtpay=중도금, surlus=잔금 — 원 단위 가정)
            try:
                enty   = int(it.get("enty")   or 0)
                prtpay = int(it.get("prtpay") or 0)
                surlus = int(it.get("surlus") or 0)
            except (TypeError, ValueError):
                enty, prtpay, surlus = 0, 0, 0
            total = enty + prtpay + surlus
            if total > 0:
                item["가격"] = f"분양가{_fmt_won_to_man(total)}"
                item["가격_직접"] = True
            results.append(item)

    log(f"  ✅ 마이홈포털 분양 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 4: SH서울주택도시공사
# ══════════════════════════════════════════════
def scrape_sh() -> list[dict]:
    log("\n▶ [4/5] SH서울주택도시공사")
    results = []
    import re as _re
    from datetime import timedelta

    CUTOFF = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")

    # 새 URL (2024년 이후 변경된 경로)
    sources = [
        ("임대공고", "장기임대",    "서울공공임대",
         "https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/list.do?multi_itm_seq=2"),
        ("분양공고", "청약·공공분양", "서울공공분양",
         "https://www.i-sh.co.kr/app/lay2/program/S48T1581C1617/www/brd/m_244/list.do?multi_itm_seq=1"),
    ]

    for cat_name, cat, type_label, base_url in sources:
        page  = 1
        found = 0
        stop  = False
        MAX_PAGES = 15

        while page <= MAX_PAGES and not stop:
            url = f"{base_url}&page={page}"
            soup = fetch(url)
            if not soup:
                log(f"  ⚠ SH {cat_name} p{page} 접근 실패")
                break

            rows = soup.select("table tbody tr")
            if not rows:
                # 공지사항 스타일의 다른 태그 시도
                rows = soup.find_all("tr")

            page_found = 0
            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 3:
                    continue
                # 제목 td — <a> 태그가 있는 칸 찾기
                a_tag = None
                for td in tds:
                    a_tag = td.find("a")
                    if a_tag:
                        break
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                if not title or len(title) < 4:
                    continue

                # 등록일: td 인덱스 3 (번호|제목|담당부서|등록일|조회수)
                post_dt = tds[3].get_text(strip=True) if len(tds) > 3 else ""
                # 날짜 정규화 (YYYY.MM.DD → YYYY-MM-DD)
                post_dt_norm = _re.sub(r'[\./]', '-', post_dt[:10])

                # 60일 컷오프
                if post_dt_norm and post_dt_norm < CUTOFF:
                    log(f"  → SH {cat_name} 60일 초과 ({post_dt_norm}) — 중단")
                    stop = True
                    break

                # SH 상세 링크: onclick="javascript:getDetailView('304515')" 에서 seq 추출
                # → base_url의 list.do?multi_itm_seq=N → view.do?seq=SEQ&multi_itm_seq=N
                href    = a_tag.get("href", "") or ""
                onclick = a_tag.get("onclick", "") or ""
                seq_m   = _re.search(r"getDetailView\('?(\d+)'?\)", onclick)
                if seq_m:
                    seq  = seq_m.group(1)
                    link = base_url.replace("list.do?", f"view.do?seq={seq}&")
                elif href.startswith("/"):
                    link = "https://www.i-sh.co.kr" + href
                elif href.startswith("http"):
                    link = href
                else:
                    link = base_url

                # 유형 추론
                if "국민임대" in title:       type_ = "국민임대"
                elif "행복주택" in title:     type_ = "행복주택"
                elif "통합공공임대" in title: type_ = "통합공공임대"
                elif "매입임대" in title:     type_ = "매입임대"
                elif "장기전세" in title:     type_ = "장기전세"
                elif "전세임대" in title:     type_ = "전세임대"
                elif "신혼희망타운" in title: type_ = "공공분양(신혼희망)"
                elif "공공분양" in title:     type_ = "공공분양(신혼희망)"
                else:                         type_ = type_label

                results.append(make_item(
                    cat, "SH서울주택도시공사", type_, title, "서울특별시",
                    post_dt_norm, "", "공고중", "", link
                ))
                found += 1
                page_found += 1

            if page_found == 0:
                break
            log(f"  SH {cat_name} p{page}: {page_found}건")
            page += 1
            time.sleep(0.5)

        log(f"  SH {cat_name} 소계: {found}건")

    log(f"  ✅ SH 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 5: GH경기주택도시공사
# ══════════════════════════════════════════════
def scrape_gh() -> list[dict]:
    log("\n▶ [5/5] GH경기주택도시공사")
    results = []
    GH_BASE = "https://apply.gh.or.kr"

    # ── URL 후보 (2026년 기준 신규 URL 우선) ──────────────────────────────
    # ① 신규 URL (2025~): /sb/sr/sr71XX/ 패턴
    # ② 구 URL (2024 이전): /GH/apply/list.do
    try_urls = [
        f"{GH_BASE}/sb/sr/sr7150/selectPbancRentHouseList.do",   # 임대주택 청약공고
        f"{GH_BASE}/sb/sr/sr7155/selectPbancRentHouseList.do",   # 매입임대 청약공고
        f"{GH_BASE}/sb/sr/sr7170/selectPbancRentSopsrtList.do",  # 임대상가
        f"{GH_BASE}/GH/apply/list.do?category=RENTAL",           # 구 URL fallback
        f"{GH_BASE}/GH/apply/list.do?category=SALE",
        f"{GH_BASE}/",
    ]

    for url in try_urls:
        soup = fetch(url, old_ssl=True)   # GH: 구형 SSL + SECLEVEL=1 어댑터 사용
        if not soup:
            continue

        found = 0
        import re as _re_gh
        # ── 방법1: 테이블 행 파싱 (data-pbancno로 상세링크·지역·마감일 추출) ──
        for row in soup.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            a = row.find("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            cells = [c.get_text(strip=True) for c in cols]
            # 게시일/마감일 (YYYY-MM-DD 또는 YYYY.MM.DD)
            dates = [m.group(0).replace(".", "-")
                     for c in cells
                     for m in [_re_gh.search(r'\d{4}[-.]\d{2}[-.]\d{2}', c)] if m]
            post_dt  = dates[0] if len(dates) >= 1 else ""
            deadline = dates[1] if len(dates) >= 2 else ""
            # 지역(시·군·구)
            sigungu = next((c for c in cells if _re_gh.fullmatch(r'[가-힣]{2,4}(시|군|구)', c)), "")
            region  = f"경기도 {sigungu}".strip() if sigungu else "경기도"
            # 상태
            status_text = next((c for c in cells if c in ("접수중","접수마감","공고중","마감","접수예정","접수전")), "공고중")
            # 유형 (data-biztynm 우선)
            type_ = (a.get("data-biztynm") or "").strip() or (
                    "통합공공임대" if "통합" in title else
                    "국민임대"    if "국민" in title else
                    "행복주택"    if "행복" in title else
                    "장기전세"    if "장기전세" in title else
                    "매입임대"    if "매입" in title else "경기공공임대")
            # 상세 링크 (data-pbancno → selectPbancDetailView.do)
            pbancno = a.get("data-pbancno")
            if pbancno:
                detail_base = url.rsplit("/", 1)[0]
                link = (f"{detail_base}/selectPbancDetailView.do"
                        f"?pbancNo={pbancno}&pbancKndCd={a.get('data-pbanckndcd','')}")
            else:
                href = a.get("href", "") or ""
                link = (GH_BASE + href) if href.startswith("/") else (href if href.startswith("http") else url)
            results.append(make_item(
                "장기임대", "GH경기주택도시공사", type_, title, region,
                post_dt, deadline, status_text, "", link
            ))
            found += 1

        # ── 방법2: 링크 직접 파싱 (구 URL / 홈 방식) ─────────────────────
        if found == 0:
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                if len(title) < 8 or "공고" not in title:
                    continue
                href = a["href"]
                link = (GH_BASE + href) if href.startswith("/") else href
                type_ = "통합공공임대" if "통합" in title else \
                        "국민임대"    if "국민" in title else \
                        "행복주택"    if "행복" in title else \
                        "매입임대"    if "매입" in title else \
                        "경기공공임대"
                results.append(make_item(
                    "장기임대", "GH경기주택도시공사", type_, title, "경기도",
                    "", "", "공고중", "", link
                ))
                found += 1
                if found >= 30:
                    break

        if found:
            log(f"  GH ({url.split('/')[-1]}): {found}건")
        time.sleep(0.5)

    # 중복 제거
    seen_titles = set()
    deduped = []
    for item in results:
        t = item.get("공고명", "")
        if t not in seen_titles:
            seen_titles.add(t)
            deduped.append(item)

    if not deduped:
        log("  ⚠ GH 접근 실패 또는 공고 없음 — 건너뜀")
    log(f"  ✅ GH 완료: {len(deduped)}건")
    return deduped

# ══════════════════════════════════════════════
# 📡 수집 5a: 서울시 청년안심주택(역세권청년주택) — soco.seoul.go.kr 게시판
#   민간임대분 청년안심주택은 LH/SH/마이홈/청약홈 어디에도 안 들어와 별도 수집
# ══════════════════════════════════════════════
SOCO_BASE = "https://soco.seoul.go.kr"
SOCO_LIST = SOCO_BASE + "/youth/pgm/home/yohome/bbsListJson.json"      # POST(JSON) 목록
SOCO_VIEW = SOCO_BASE + "/youth/bbs/BMSR00015/view.do?menuNo=400008&boardId="
SOCO_MAP  = SOCO_BASE + "/youth/pgm/home/yohome/maplist.json"          # 단지별 보증금·월세·자치구

# ══════════════════════════════════════════════
# 💰 LH·SH 가격 매칭 — 마이홈 단지정보(HWSPR04) 캐시 활용
#   마이홈 단지정보 API에 보증금·월임대료 필드 이미 포함 (96.9% 채워짐)
#   (시도, 시군구, 공급유형) 단위로 그룹화 → P25~P75 범위로 공고에 적용
# ══════════════════════════════════════════════
# LH/SH/마이홈 공고 유형 → 마이홈 캐시 공급유형 매핑 (substring 매칭 키)
_LH_SUPPLY_TYPE_RULES = [
    ("매입임대",     ["매입임대"]),
    ("행복주택",     ["행복주택"]),
    ("국민임대",     ["국민임대"]),
    ("영구임대",     ["영구임대"]),
    ("장기전세",     ["장기전세"]),
    ("통합공공임대", ["통합공공임대", "행복주택", "국민임대"]),
    ("전세임대",     ["매입임대"]),
    ("신혼희망",     ["행복주택", "매입임대"]),
    ("신혼·신생아",  ["매입임대", "행복주택"]),
    ("기존주택",     ["매입임대"]),
    ("10년임대",     ["10년임대"]),
    ("50년임대",     ["50년임대"]),
    ("5년임대",      ["5년임대"]),
    ("공공임대",     ["매입임대", "행복주택", "국민임대"]),
]

def build_lh_price_map(complex_data: list[dict]) -> tuple[dict, dict]:
    """단지정보 캐시 → (price_map, sgg_alias).
    price_map: {(시도,시군구,공급유형): {'보증금':[..], '월임대료':[..]}}.
    sgg_alias: 시군구 별칭 dict {alias_text → real_signgu_name}.
      예: '부천'→'부천시', '강남'→'강남구', '용인 기흥'→'용인시 기흥구'."""
    from collections import defaultdict
    pm: dict = defaultdict(lambda: {"보증금": [], "월임대료": [], "전환한도": []})
    sgg_real: set = set()
    for d in complex_data or []:
        sido = (d.get("시도") or "").strip()
        sgg  = (d.get("시군구") or "").strip()
        sup  = (d.get("공급유형") or "").strip()
        if not (sido and sgg and sup):
            continue
        sgg_real.add(sgg)
        bo = d.get("보증금") or 0
        wo = d.get("월임대료") or 0
        cv = d.get("전환보증금한도") or 0
        if bo > 0: pm[(sido, sgg, sup)]["보증금"].append(int(bo))
        if wo > 0: pm[(sido, sgg, sup)]["월임대료"].append(int(wo))
        if cv > 0: pm[(sido, sgg, sup)]["전환한도"].append(int(cv))
    # 시군구 별칭 빌드 — 긴 키부터 매칭하도록 정렬
    sgg_alias: dict = {}
    for sgg in sgg_real:
        sgg_alias[sgg] = sgg                  # 풀네임 자기참조
        # "부천시" → "부천", "강남구" → "강남" (마지막 시/군/구 제거)
        for suf in ("시", "군", "구"):
            if sgg.endswith(suf) and len(sgg) > 2:
                short = sgg[:-1]
                # 중복(예: 강남구·강남시 같이) 시 풀네임 우선
                if short not in sgg_alias:
                    sgg_alias[short] = sgg
        # "용인시 기흥구" → "기흥구" / "기흥" 매칭도 가능하도록
        if " " in sgg:
            parts = sgg.split()
            for p in parts:
                if p not in sgg_alias:
                    sgg_alias[p] = sgg
                if len(p) > 2 and p[-1] in "시군구" and p[:-1] not in sgg_alias:
                    sgg_alias[p[:-1]] = sgg
    return dict(pm), sgg_alias

def _fmt_won_to_man(won: int) -> str:
    """원 → '286만' / '5,000만' / '3억'. 만원 단위 반올림."""
    man = round(won / 10000)
    if man >= 10000:
        eok = man // 10000
        rem = man % 10000
        return f"{eok}억" if rem == 0 else f"{eok}.{rem//1000}억"
    return f"{man}만"

def _percentile(sorted_list, p):
    """sorted_list에서 p-percentile 값 (0~100)."""
    if not sorted_list:
        return None
    n = len(sorted_list)
    if n == 1:
        return sorted_list[0]
    k = max(0, min(n-1, int(round(p/100 * (n-1)))))
    return sorted_list[k]

def match_lh_price(item: dict, price_map: dict, sgg_alias: dict) -> str:
    """LH/SH/마이홈 공고에 시군구+공급유형 매칭으로 보증금·월임대료 P25~P75 범위 산출.
    반환: '보증금200만~3000만 / 월18만~78만' 또는 ''.
    sgg_alias: {alias_text → real_signgu_name}. 별칭(부천=부천시)도 매칭."""
    text = f"{item.get('공고명','')} {item.get('지역','')} {item.get('유형','')}"
    # 시군구 추출: alias 중 텍스트에 포함된 것 (긴 alias부터 매칭해야 '용인시 기흥구' 우선)
    aliases_sorted = sorted(sgg_alias.keys(), key=len, reverse=True)
    matched_signgus: list = []
    used_text = text
    for alias in aliases_sorted:
        if alias in used_text:
            real_sgg = sgg_alias[alias]
            if real_sgg not in matched_signgus:
                matched_signgus.append(real_sgg)
            # 매칭 위치를 마스킹해서 중복 매칭 방지 (예: '용인시 기흥구' 매칭 후 '용인시' 재매칭 안됨)
            used_text = used_text.replace(alias, "·" * len(alias), 1)
    # 공급유형 후보 추출 (다중 가능)
    suppls = []
    for keyword, targets in _LH_SUPPLY_TYPE_RULES:
        if keyword in text:
            for t in targets:
                if t not in suppls:
                    suppls.append(t)
    # 시도 후보
    region = item.get("지역", "") + " " + item.get("공고명", "")
    if "서울" in region:    sidos = ["서울특별시"]
    elif "경기" in region:  sidos = ["경기도"]
    else: sidos = ["서울특별시", "경기도"]
    # 매칭된 그룹 합산
    bo_list, wo_list, cv_list = [], [], []
    if matched_signgus and suppls:
        for sido in sidos:
            for sgg in matched_signgus:
                for sup in suppls:
                    grp = price_map.get((sido, sgg, sup))
                    if grp:
                        bo_list.extend(grp["보증금"])
                        wo_list.extend(grp["월임대료"])
                        cv_list.extend(grp.get("전환한도", []))
    # Fallback 1: 시군구 매칭 안 되면 시도+공급유형으로 전체 합산
    if not bo_list and not wo_list and suppls:
        for (sido, sgg, sup), grp in price_map.items():
            if sido in sidos and sup in suppls:
                bo_list.extend(grp["보증금"])
                wo_list.extend(grp["월임대료"])
                cv_list.extend(grp.get("전환한도", []))
    # Fallback 2: 공급유형도 모르면 시군구+전체유형
    if not bo_list and not wo_list and matched_signgus:
        for (sido, sgg, sup), grp in price_map.items():
            if sido in sidos and sgg in matched_signgus:
                bo_list.extend(grp["보증금"])
                wo_list.extend(grp["월임대료"])
                cv_list.extend(grp.get("전환한도", []))
    if not bo_list and not wo_list:
        return ""
    bo_sorted = sorted(bo_list)
    wo_sorted = sorted(wo_list)
    bo_lo, bo_hi = _percentile(bo_sorted, 25), _percentile(bo_sorted, 75)
    wo_lo, wo_hi = _percentile(wo_sorted, 25), _percentile(wo_sorted, 75)
    parts = []
    if bo_lo and bo_hi:
        if bo_lo == bo_hi:
            parts.append(f"보증금{_fmt_won_to_man(bo_lo)}")
        else:
            parts.append(f"보증금{_fmt_won_to_man(bo_lo)}~{_fmt_won_to_man(bo_hi)}")
    if wo_lo and wo_hi:
        if wo_lo == wo_hi:
            parts.append(f"월{_fmt_won_to_man(wo_lo)}")
        else:
            parts.append(f"월{_fmt_won_to_man(wo_lo)}~{_fmt_won_to_man(wo_hi)}")
    base = " / ".join(parts) if parts else ""
    # 🔄 전환보증금 한도 부가 표시 (P50 중앙값) — 있을 때만
    if base and cv_list:
        cv_sorted = sorted(cv_list)
        cv_mid = _percentile(cv_sorted, 50)
        if cv_mid and cv_mid > 0:
            base += f" 🔄전환한도{_fmt_won_to_man(cv_mid)}"
    return base

def fetch_soco_price_map(session) -> dict:
    """청년안심 단지비교(maplist.json) → {단지명: {'gu':자치구, 'price':'월16만~77만'}}.
    공고에 가격·자치구 보강용. 실패해도 빈 dict."""
    out: dict = {}
    try:
        session.get(SOCO_BASE + "/youth/pgm/home/yohome/compareSearchList.do?menuNo=400040", timeout=20)
        for pg in range(1, 9):
            r = session.post(SOCO_MAP, data={"pageIndex": pg}, timeout=20)
            rows = r.json().get("mapResultList", []) or []
            if not rows:
                break
            for it in rows:
                name = (it.get("homeName") or "").strip()
                if not name or name in out:
                    continue
                rl = (it.get("fnMoneyRentalLow") or "").strip()
                rh = (it.get("fnMoneyRentalHigh") or "").strip()
                dl = (it.get("fnMoneyDepositLow") or "").strip()
                if rl and rh:   price = f"월{rl}~{rh}"
                elif rl:        price = f"월{rl}"
                elif dl:        price = f"보증금{dl}"
                else:           price = ""
                out[name] = {"gu": (it.get("adresGu") or "").strip(), "price": price}
            time.sleep(0.2)
    except Exception as e:
        log(f"  ⚠ 청년안심 단지가격 맵 로드 실패: {e}")
    return out

def scrape_seoul_youth() -> list[dict]:
    """서울시 청년안심주택 모집공고 — soco.seoul.go.kr 공동체주택플랫폼 게시판(AJAX).
    필드: nttSj=제목, optn1=공고일, optn4=마감일, optn3=사업자, boardId=상세링크."""
    from datetime import timedelta
    log("\n▶ [5a] 서울시 청년안심주택 게시판 — soco.seoul.go.kr")
    results = []
    CUTOFF    = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    today_str = datetime.today().strftime("%Y-%m-%d")

    s = requests.Session()
    s.headers.update({
        "User-Agent": HEADERS["User-Agent"],
        "Referer": SOCO_BASE + "/youth/bbs/BMSR00015/list.do?menuNo=400008",
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        s.get(SOCO_BASE + "/youth/bbs/BMSR00015/list.do?menuNo=400008", timeout=20)
    except Exception as e:
        log(f"  ⚠ soco 세션 초기화 실패: {e}")
        return []

    # 단지별 가격·자치구 맵 (긴 단지명부터 매칭 위해 길이 내림차순)
    price_map = fetch_soco_price_map(s)
    price_names = sorted(price_map.keys(), key=len, reverse=True)

    page = 1
    while page <= 10:   # 안전 상한 (최근순 정렬이라 60일 넘으면 조기 종료)
        try:
            r = s.post(SOCO_LIST,
                       data={"bbsId": "BMSR00015", "pageIndex": page, "searchKeyword": ""},
                       timeout=20)
            r.raise_for_status()
            data = r.json()
            lst  = data.get("resultList", []) or []
            if not lst:
                break
            all_too_old = True
            for it in lst:
                post_de = (it.get("optn1") or "")[:10]
                if post_de and post_de >= CUTOFF:
                    all_too_old = False
                else:
                    continue
                title = (it.get("nttSj") or "").strip()
                if not title:
                    continue
                end_de   = (it.get("optn4") or "")[:10]
                status   = "공고중" if (not end_de or end_de >= today_str) else "마감"
                board_id = it.get("boardId")
                link     = f"{SOCO_VIEW}{board_id}"
                # 단지가격 맵 매칭(긴 이름 우선) → 가격·자치구 보강
                region = "서울"
                price  = ""
                for nm_key in price_names:
                    if nm_key in title:
                        info = price_map[nm_key]
                        if info.get("gu"):
                            region = f"서울 {info['gu']}"
                        price = info.get("price", "")
                        break
                # 유형: '공공지원민간임대(청년안심)' — 청년안심 태그 + 소득상한(공공지원민간임대 100%) 둘 다 매칭
                item = make_item("장기임대", "서울 청년안심주택", "공공지원민간임대(청년안심)",
                                 title, region, post_de, end_de, status,
                                 str(it.get("inqireCo") or ""), link)
                if price:
                    item["가격"] = price
                    item["가격_직접"] = True   # soco 단지비교 직접값
                results.append(item)
            tot_page = int((data.get("pagingInfo") or {}).get("totPage", 1) or 1)
            if all_too_old or page >= tot_page:
                break
            page += 1
            time.sleep(0.4)
        except Exception as e:
            log(f"  ⚠ soco p{page} 오류: {e}")
            break

    log(f"  ✅ 서울 청년안심주택 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 5b: 청약홈 — APT 분양 (한국부동산원 OpenAPI)
# ══════════════════════════════════════════════
_CHEONG_MDL_CACHE: dict[str, tuple] = {}

def fetch_cheong_mdl_layers(base: str, house_manage_no: str) -> tuple:
    """청약홈 주택형별 상세(getAPTLttotPblancMdl)에서 공고별
    (공급대상 계층 리스트, 분양가 문자열) 추출.
    특공 물량>0 계층 + LTTOT_TOP_AMOUNT(주택형별 분양가) 범위. 결과 캐싱."""
    if not house_manage_no:
        return [], ""
    if house_manage_no in _CHEONG_MDL_CACHE:
        return _CHEONG_MDL_CACHE[house_manage_no]
    layers: list[str] = []
    price: str = ""
    try:
        r = requests.get(
            f"{base}/getAPTLttotPblancMdl",
            params={"page": 1, "perPage": 100, "serviceKey": MYHOME_API_KEY,
                    "cond[HOUSE_MANAGE_NO::EQ]": house_manage_no},
            timeout=20,
        )
        if r.status_code == 200:
            rows   = r.json().get("data", [])
            layers = layers_from_mdl(rows)
            price  = format_price_eok([row.get("LTTOT_TOP_AMOUNT") for row in rows])
        time.sleep(0.2)
    except Exception:
        layers, price = [], ""
    _CHEONG_MDL_CACHE[house_manage_no] = (layers, price)
    return layers, price

def scrape_cheongyanghome() -> list[dict]:
    """청약홈 APT 분양정보 — 한국부동산원 청약홈 분양정보 조회 서비스 (공공데이터포털)
    민간분양 APT, 공공분양 APT (서울·경기·인천 최근 60일)
    공고 URL: https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"""
    import re as _re
    from datetime import timedelta
    log("\n▶ [5b] 청약홈 APT 분양 API — 서울+경기+인천")
    results = []
    CUTOFF = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    base   = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"

    def _extract_district(addr: str, area_nm: str) -> str:
        """공급위치(HSSPLY_ADRES) → '서울 동작구' 형식으로 변환"""
        if not addr:
            return area_nm
        m = _re.search(
            r'(서울특별시|경기도|인천광역시)\s+'
            r'([가-힣]+(?:시|군)(?:\s+[가-힣]+구)?|[가-힣]+구)',
            addr
        )
        if m:
            prefix = {"서울특별시": "서울", "경기도": "경기", "인천광역시": "인천"}.get(
                m.group(1), m.group(1)
            )
            return f"{prefix} {m.group(2).strip()}"
        return area_nm

    def _cheong_type(it: dict) -> str:
        """청약홈 항목 → 내부 유형명"""
        dtl  = it.get("HOUSE_DTL_SECD_NM") or ""
        secd = it.get("HOUSE_SECD_NM") or ""
        rnt  = it.get("RENT_SECD_NM") or ""
        if "국민" in dtl:  return "공공분양(국민)"
        if "신혼" in secd: return "공공분양(신혼희망)"
        if "민영" in dtl:  return "민간분양(APT)"
        if "임대" in rnt:  return "공공지원민간임대"
        return "민간분양"

    today_str = datetime.today().strftime("%Y-%m-%d")
    for area in ["서울", "경기", "인천"]:
        page = 1
        while True:
            try:
                r = requests.get(
                    f"{base}/getAPTLttotPblancDetail",
                    params={
                        "page":       page,
                        "perPage":    100,
                        "serviceKey": MYHOME_API_KEY,
                        "cond[SUBSCRPT_AREA_CODE_NM::EQ]": area,
                    },
                    timeout=20,
                )
                r.raise_for_status()
                data    = r.json()
                items   = data.get("data", [])
                match_c = int(data.get("matchCount") or 0)

                page_found   = 0
                all_too_old  = True      # 이 페이지가 모두 60일 초과면 조기 종료
                for it in items:
                    rcrit_de = (it.get("RCRIT_PBLANC_DE") or "")[:10]
                    if rcrit_de and rcrit_de >= CUTOFF:
                        all_too_old = False
                    else:
                        continue          # 60일 초과 건 스킵

                    title = (it.get("HOUSE_NM") or "").strip()
                    if not title:
                        continue

                    addr      = (it.get("HSSPLY_ADRES") or "").strip()
                    region    = _extract_district(addr, area)
                    type_     = _cheong_type(it)
                    rcept_end = (it.get("RCEPT_ENDDE") or "")[:10]
                    status    = "모집중" if rcept_end >= today_str else "마감"
                    link      = (it.get("PBLANC_URL") or "").strip() or "https://www.applyhome.co.kr"

                    item = make_item(
                        "청약·공공분양", "청약홈", type_, title, region,
                        rcrit_de, rcept_end, status, "", link
                    )
                    item["공고유형분류"] = "🟢 모집공고"   # 청약홈 분양 데이터는 모두 모집공고
                    # 공급대상 계층 + 분양가: Mdl(특공 물량·LTTOT_TOP_AMOUNT) 기반
                    mdl_layers, mdl_price = fetch_cheong_mdl_layers(base, it.get("HOUSE_MANAGE_NO"))
                    item["대상계층"] = merge_layers(item.get("대상계층"), mdl_layers)
                    item["대상계층_확인"] = True   # 청약홈 Mdl로 특공 계층 확인 완료
                    if mdl_price:
                        item["가격"] = mdl_price
                        item["가격_직접"] = True   # LTTOT_TOP_AMOUNT 직접값
                    results.append(item)
                    page_found += 1

                log(f"    {area} p{page}: {page_found}건 수집 (전체 match {match_c}건)")
                if all_too_old or page * 100 >= match_c:
                    break
                page += 1
                time.sleep(0.4)
            except Exception as e:
                log(f"  ⚠ 청약홈 {area} p{page} 오류: {e}")
                break

    log(f"  ✅ 청약홈 분양 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 5c: LH 분양임대공고문 API (한국토지주택공사)
# ══════════════════════════════════════════════
LH_API_BASE = "http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
# 필수 파라미터: ServiceKey, PG_SZ, PAGE, PAN_NT_ST_DT, CLSG_DT
# 옵션: CNP_CD(11=서울, 41=경기), UPP_AIS_TP_CD(05=분양, 06=임대, 39=신혼희망타운)
# 공공데이터포털 신청: 2026-05-21 승인 완료, API 키 전파 후 활성화 예정

def scrape_lh_api() -> list[dict]:
    """LH 분양임대공고문 API (공공데이터포털 B552555).
    LH 스크래핑과 병행 수집 — 중복 제거는 main()의 소스 통합 로직이 처리.
    API 키 전파 완료 전까지 403 오류 시 빈 리스트 반환."""
    import urllib.parse
    from datetime import timedelta
    log("\n▶ [5c] LH 분양임대공고문 API — 서울+경기")

    KEY_ENC = urllib.parse.quote(MYHOME_API_KEY, safe="")
    today    = datetime.today()
    start_dt = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    end_dt   = (today + timedelta(days=365)).strftime("%Y-%m-%d")

    # 유형코드 → 내부 유형명
    # ⚠️ TODO(명세 충돌): 공식 명세(15058530 표#4 UPP_AIS_TP_CD)는 6종
    #   (01=토지, 05=분양주택, 06=임대주택, 13=주거복지, 22=상가, 39=신혼희망타운)뿐.
    #   07~11은 별도 AIS_TP_CD(매물 세부유형)일 가능성. LH API(현재 403)가 활성화되면
    #   실제 응답의 UPP_AIS_TP_CD/AIS_TP_CD 값을 보고 매핑 재확인 필요.
    #   참고: .deploy/docs/api-spec/공식문서/15058530_LH_분양임대공고문_활용가이드.docx
    TYPE_MAP = {
        "05": "분양주택", "06": "공공임대", "39": "공공분양(신혼희망)",
        "07": "국민임대", "08": "행복주택", "09": "영구임대",
        "10": "매입임대", "11": "전세임대",
    }

    results = []
    for cnp_cd, region_prefix in [("11", "서울"), ("41", "경기")]:
        page = 1
        while True:
            url = (
                f"{LH_API_BASE}?ServiceKey={KEY_ENC}"
                f"&PG_SZ=100&PAGE={page}"
                f"&CNP_CD={cnp_cd}"
                f"&PAN_NT_ST_DT={start_dt}&CLSG_DT={end_dt}"
                f"&type=json"
            )
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 403:
                    log(f"  ⚠ LH API 403 (키 전파 대기 중) — 스킵")
                    return []
                r.raise_for_status()
                data = r.json()
                items = data.get("dsList", data.get("body", {}).get("dsList", []))
                if isinstance(items, dict):
                    items = [items]
                if not items:
                    break

                for it in items:
                    title = (it.get("PAN_NM") or "").strip()
                    if not title:
                        continue
                    region    = f"{region_prefix} {(it.get('CTRT_ADDRESS') or '').split()[1] if len((it.get('CTRT_ADDRESS') or '').split()) > 1 else ''}".strip()
                    upp_cd    = it.get("UPP_AIS_TP_CD") or ""
                    type_     = TYPE_MAP.get(upp_cd, it.get("UPP_AIS_TP_CD_NM") or "공공임대")
                    cat       = "청약·공공분양" if "분양" in type_ else "장기임대"
                    post_dt   = (it.get("PAN_NT_ST_DT") or "")[:10]
                    deadline  = (it.get("CLSG_DT") or "")[:10]
                    status    = it.get("PAN_SS_NM") or "공고중"
                    link      = (it.get("DTL_URL") or "").strip() or "https://apply.lh.or.kr"
                    results.append(make_item(cat, "LH공사API", type_, title, region,
                                             post_dt, deadline, status, "", link))

                log(f"    LH API {region_prefix} p{page}: {len(items)}건")
                total = int(data.get("totalCount") or data.get("body", {}).get("totalCount") or 0)
                if total and page * 100 >= total:
                    break
                if len(items) < 100:
                    break
                page += 1
                time.sleep(0.5)
            except Exception as e:
                log(f"  ⚠ LH API {region_prefix} 오류: {e}")
                break

    log(f"  ✅ LH API 완료: {len(results)}건")
    return results

# ══════════════════════════════════════════════
# 📡 수집 6: 마이홈포털 — 예비입주자 대기현황 (HWSPR03)
# ══════════════════════════════════════════════
def scrape_waitlist() -> list[dict]:
    """서울+경기 공공임대 예비입주자 대기현황"""
    log("\n▶ [6] 마이홈포털 대기현황 API — 서울+경기")
    results = []
    url = f"{MYHOME_API_WAIT_BASE}/moveWaitStsList"

    for brtc_code, brtc_name in [("11", "서울특별시"), ("41", "경기도")]:
        page = 1
        while True:
            params = {
                "serviceKey": MYHOME_API_KEY,
                "brtcCode":   brtc_code,
                "pageNo":     page,
                "numOfRows":  1000,
                "type":       "json",
            }
            try:
                r = requests.get(url, params=params, timeout=20)
                r.raise_for_status()
                resp = r.json().get("response", {})
                rc   = resp.get("header", {}).get("resultCode", "00")
                msg  = resp.get("header", {}).get("resultMsg", "")
                if rc not in ("00", "0000"):
                    log(f"  ⚠ 대기현황 [{brtc_name}] 제공기관 오류 [{rc}] {msg}")
                    break
                body  = resp.get("body", {})
                total = int(body.get("totalCount", 0))
                items = body.get("item", [])
                if isinstance(items, dict):
                    items = [items]
                if not items:
                    break
                for it in items:
                    results.append({
                        "시도":       it.get("brtcNm", brtc_name),
                        "시군구":     it.get("signguNm", ""),
                        "단지명":     it.get("hsmpNm", ""),
                        "주소":       it.get("rnAdres", ""),
                        "주택유형":   it.get("houseTyNm", ""),
                        "공급유형":   it.get("suplyTyNm", ""),
                        "주택형":     it.get("styleNm", ""),
                        "대기자수":   int(it.get("waitCo", 0) or 0),
                        "종료자수":   int(it.get("trmnatCo", 0) or 0),
                    })
                log(f"    {brtc_name} p{page}: {len(items)}건 (전체 {total}건)")
                if page * 1000 >= total:
                    break
                page += 1
                time.sleep(0.3)
            except Exception as e:
                log(f"  ⚠ {brtc_name} 대기현황 오류: {e}")
                break

    log(f"  ✅ 대기현황 완료: {len(results)}건")
    return results


# ══════════════════════════════════════════════
# 📡 수집 7: 마이홈포털 — 공공임대 단지정보 (HWSPR04)
# ══════════════════════════════════════════════
def scrape_complex() -> list[dict]:
    """서울+경기 공공임대 단지정보 (7일 캐시 적용)"""
    log("\n▶ [7] 마이홈포털 단지정보 API — 서울+경기")

    # ── 캐시 확인 (Supabase kv_cache 우선, 없으면 파일) ──────────
    cache_path = os.path.join(BASE_DIR, "단지정보_캐시.json")
    _cconn = _db_conn()
    if _cconn is not None:
        try:
            with _cconn.cursor() as cur:
                cur.execute("select data, updated from kv_cache where name = %s", ("complex_cache",))
                row = cur.fetchone()
            if row:
                data_blob, updated_ts = row
                age_days = (datetime.now(updated_ts.tzinfo) - updated_ts).total_seconds() / 86400
                if age_days < 7:
                    log(f"  📦 Supabase 캐시 사용 ({age_days:.1f}일 전, {len(data_blob)}건)")
                    _cconn.close()
                    return data_blob
        except Exception as e:
            log(f"  ⚠ kv_cache 조회 실패 → 신규 수집: {e}")
        finally:
            try: _cconn.close()
            except Exception: pass
    elif os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
            updated = datetime.fromisoformat(cache.get("updated", "2000-01-01"))
            age_days = (datetime.now() - updated).total_seconds() / 86400
            if age_days < 7:
                log(f"  📦 캐시 사용 ({age_days:.1f}일 전, {len(cache['data'])}건)")
                return cache["data"]
        except Exception:
            pass

    url = f"{MYHOME_API_CPLX_BASE}/rentalHouseGwList"
    results = []

    region_map = [
        ("11", SEOUL_SIGNGU),
        ("41", GYEONGGI_SIGNGU),
    ]

    for brtc_code, signgu_map in region_map:
        brtc_name = "서울특별시" if brtc_code == "11" else "경기도"
        for signgu_nm, signgu_code in signgu_map.items():
            page = 1
            while True:
                params = {
                    "serviceKey": MYHOME_API_KEY,
                    "brtcCode":   brtc_code,
                    "signguCode": signgu_code,
                    "pageNo":     page,
                    "numOfRows":  1000,
                    "type":       "json",
                }
                try:
                    r = requests.get(url, params=params, timeout=20)
                    r.raise_for_status()
                    resp = r.json().get("response", {})
                    rc   = resp.get("header", {}).get("resultCode", "00")
                    msg  = resp.get("header", {}).get("resultMsg", "")
                    if rc not in ("00", "0000", "03"):  # 03=데이터없음은 정상처리
                        log(f"  ⚠ 단지정보 [{brtc_name} {signgu_nm}] 오류 [{rc}] {msg}")
                        break
                    body  = resp.get("body", {})
                    total = int(body.get("totalCount", 0) or 0)
                    items = body.get("item", [])
                    if isinstance(items, dict):
                        items = [items]
                    for it in items:
                        results.append({
                            "시도":       it.get("brtcNm", brtc_name),
                            "시군구":     it.get("signguNm", signgu_nm),
                            "단지명":     it.get("hsmpNm", ""),
                            "주소":       it.get("rnAdres", ""),
                            "공급기관":   it.get("insttNm", ""),
                            "공급유형":   it.get("suplyTyNm", ""),
                            "주택유형":   it.get("houseTyNm", ""),
                            "주택형_m2":  it.get("styleNm", ""),
                            "전용면적":   float(it.get("suplyPrvuseAr", 0) or 0),
                            "세대수":     int(it.get("hshldCo", 0) or 0),
                            "보증금":     int(it.get("bassRentGtn", 0) or 0),
                            "월임대료":   int(it.get("bassMtRntchrg", 0) or 0),
                            "전환보증금한도": int(it.get("bassCnvrsGtnLmt", 0) or 0),
                            "난방방식":   it.get("heatMthdDetailNm", ""),
                            "건물유형":   it.get("buldStleNm", ""),
                            "주차대수":   int(it.get("parkngCo", 0) or 0),
                        })
                    if total > 0:
                        log(f"    {brtc_name} {signgu_nm}: {len(items)}건")
                    if page * 1000 >= total:
                        break
                    page += 1
                    time.sleep(0.2)
                except Exception as e:
                    log(f"  ⚠ {brtc_name} {signgu_nm} 오류: {e}")
                    break
            time.sleep(0.15)

    # 캐시 저장 (Supabase kv_cache 우선, 없으면 파일)
    _sconn = _db_conn()
    if _sconn is not None:
        try:
            with _sconn.cursor() as cur:
                cur.execute(
                    "insert into kv_cache(name, data, updated) values (%s, %s::jsonb, now()) "
                    "on conflict (name) do update set data = excluded.data, updated = now()",
                    ("complex_cache", json.dumps(results, ensure_ascii=False)),
                )
            log(f"  ✅ 단지정보 완료: {len(results)}건 (Supabase kv_cache 저장)")
        except Exception as e:
            log(f"  ⚠ kv_cache 저장 실패: {e}")
        finally:
            _sconn.close()
    else:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"updated": datetime.now().isoformat(), "data": results}, f, ensure_ascii=False)
        log(f"  ✅ 단지정보 완료: {len(results)}건 (캐시 저장)")
    return results


# ══════════════════════════════════════════════
# 🆕 신규 공고 감지
# ══════════════════════════════════════════════
def _normalize_post_date(s: str) -> str:
    """게시일 문자열을 'YYYY-MM-DD'로 정규화. '2026.05.21'·'2026-5-21' 등 허용."""
    import re as _re_d
    s = (s or "").strip().replace(".", "-").replace(" ", "")
    m = _re_d.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"

def detect_new(data: list[dict]) -> tuple[list[dict], int]:
    """이전 수집 데이터와 비교해 신규 공고 표시.

    특수 모드: 환경변수 ALIMI_NEW_BY_POSTDATE 가 설정되면(YYYY-MM-DD 또는 'today')
    seen 비교 대신 '게시일 == 해당 날짜'인 공고를 신규로 표시한다.
    이 모드에서는 seen_notices.json을 갱신하지 않아 정기(daily) 실행에 영향이 없다."""
    post_date_mode = os.environ.get("ALIMI_NEW_BY_POSTDATE", "").strip()
    if post_date_mode:
        target = (datetime.today().strftime("%Y-%m-%d")
                  if post_date_mode.lower() == "today"
                  else _normalize_post_date(post_date_mode))
        new_count = 0
        for item in data:
            item["is_new"] = (_normalize_post_date(item.get("게시일", "")) == target)
            if item["is_new"]:
                new_count += 1
        log(f"  ℹ 게시일 기준 신규 모드 (ALIMI_NEW_BY_POSTDATE={target}) → {new_count}건 신규 / seen 미갱신")
        return data, new_count

    # ── 이전 seen 로드 (Supabase 우선, 없으면 파일) ──────────────
    conn = _db_conn()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("select key from seen_notices")
                seen = set(r[0] for r in cur.fetchall())
        except Exception as e:
            log(f"  ⚠ seen_notices 조회 실패 → 파일 폴백: {e}")
            conn = None
    if conn is None:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE, encoding="utf-8") as f:
                seen = set(json.load(f).get("keys", []))
        else:
            seen = set()

    new_count = 0
    current_keys = []
    new_keys = []
    for item in data:
        item["is_new"] = False          # ← 매 실행마다 초기화 (버그 방지)
        key = notice_key(item)
        current_keys.append(key)
        if key not in seen:
            item["is_new"] = True
            new_count += 1
            new_keys.append(key)

    # ── 업데이트된 seen 저장 ─────────────────────────────────────
    if conn is not None:
        try:
            if new_keys:
                with conn.cursor() as cur:
                    cur.executemany(
                        "insert into seen_notices(key) values (%s) on conflict (key) do nothing",
                        [(k,) for k in new_keys],
                    )
            log(f"  💾 Supabase seen_notices: 신규 {len(new_keys)}건 기록 (총 {len(seen)+len(new_keys)})")
        except Exception as e:
            log(f"  ⚠ seen_notices 기록 실패: {e}")
        finally:
            conn.close()
    else:
        all_keys = list(seen | set(current_keys))
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"keys": all_keys, "updated": datetime.now().isoformat()}, f, ensure_ascii=False)

    return data, new_count

# ══════════════════════════════════════════════
# 🌐 HTML 대시보드 v2
# ══════════════════════════════════════════════
def save_dashboard(data: list[dict], new_count: int, waitlist_data: list[dict] = None, complex_data: list[dict] = None):
    rental = [d for d in data if d["카테고리"] == "장기임대"]
    sale   = [d for d in data if d["카테고리"] == "청약·공공분양"]
    new_items = [d for d in data if d.get("is_new")]
    waitlist_data = waitlist_data or []
    complex_data  = complex_data  or []

    total     = len(data)
    star_cnt    = sum(1 for d in data if d.get("신혼생초"))
    star_rental = sum(1 for d in data if d.get("신혼생초") and d.get("카테고리")=="장기임대")
    star_sale   = sum(1 for d in data if d.get("신혼생초") and d.get("카테고리")=="청약·공공분양")
    today_str = datetime.today().strftime("%Y년 %m월 %d일 %H:%M")

    # 사용자 요건 로드 (Python 측 처리용; HTML에는 개인정보 미임베드)
    prefs = load_user_prefs()

    def make_rows(items):
        html = ""
        for d in sorted(items, key=lambda x: x.get('게시일','') or '', reverse=True):
            is_new     = d.get("is_new", False)
            is_star    = d.get("신혼생초", False)
            notice_cls = d.get("공고유형분류","")

            # 행 색상: 신규 > 신혼·생초 (우선순위 개념 제거)
            row_cls = "row-new" if is_new else ("row-star" if is_star else "")
            new_badge  = '<span class="new-badge">🆕 NEW</span>' if is_new else ""
            star_badge = '<span class="badge green">⭐ 신혼·생초</span>' if is_star else ""
            title = (d.get("공고명","") or "").replace("<","&lt;").replace(">","&gt;")
            link  = d.get("링크","#") or "#"
            layers      = d.get("대상계층", []) or []   # 공급대상 계층 (신생아·청년 등)
            layer_html  = layer_badges_html(layers, d.get("대상계층_확인", False))
            type_tag    = notice_type_tag(d)        # 정리 유형 태그 (행복주택·매입임대 등)
            region_disp = region_with_district(d)   # 시·도 + 구 (인천 남동구)
            income_bi   = income_bracket_index(get_income_limit_won(d.get("유형","") or "", d.get("신혼생초", False)))  # 소득구간 0~4
            district    = region_disp if " " in region_disp else ""  # 구 정보 있을 때만

            # 공고유형분류 배지 색상
            nc_style = {
                "🟢 모집공고":  "background:#e8f5e9;color:#1b5e20",
                "🔵 당첨·배정": "background:#e3f2fd;color:#0d47a1",
                "🟡 계약·서류": "background:#fff8e1;color:#f57f17",
                "⚪ 행정공지":  "background:#f5f5f5;color:#616161",
            }.get(notice_cls, "background:#f5f5f5;color:#555")

            nc_badge = f'<span style="display:inline-block;padding:1px 5px;border-radius:4px;font-size:.65rem;font-weight:700;{nc_style}">{notice_cls}</span>' if notice_cls else ""

            html += f"""
<tr class="{row_cls}"
    data-cat="{d.get('카테고리','')}"
    data-region="{d.get('지역','')}"
    data-type="{d.get('유형','')}"
    data-tag="{type_tag}"
    data-noticetype="{notice_cls}"
    data-new="{'1' if is_new else '0'}"
    data-star="{'1' if is_star else '0'}"
    data-src="{d.get('출처','')}"
    data-income="{income_bi}"
    data-layers="{'|'.join(layers)}"
    data-district="{district}">
  <td>{new_badge}{('<br>' if new_badge and star_badge else '')}{star_badge}</td>
  <td class="type-cell">{type_tag}<br>{nc_badge}</td>
  <td class="title-cell"><a href="{link}" target="_blank">{title}</a>{('<br>' + layer_html) if layer_html else ''}</td>
  <td>{region_disp}</td>
  <td>{d.get('게시일','')}</td>
  <td>{d.get('마감일','')}</td>
  <td>{d.get('상태','')}</td>
  <td class="src-cell">{d.get('출처','')}</td>
</tr>"""
        return html

    all_rows    = make_rows(data)
    rental_rows = make_rows(rental)
    sale_rows   = make_rows(sale)
    new_rows    = make_rows(new_items)

    # 시군구(구) 필터 옵션 — 데이터에 실제 존재하는 '시·도 구' 목록
    _districts = sorted({region_with_district(d) for d in data
                         if " " in region_with_district(d)})
    district_options = "".join(f'<option value="{x}">{x}</option>' for x in _districts)

    # ── 대기현황·단지정보 → JSON (JS 렌더링용) ──────────────────────────────
    def make_wait_json(items):
        result = []
        for d in sorted(items, key=lambda x: -x.get("대기자수", 0)):
            result.append([
                d.get('시도',''), d.get('시군구',''), d.get('단지명',''),
                d.get('주소',''), d.get('공급유형',''), d.get('주택유형',''),
                d.get('주택형',''), d.get('대기자수',0), d.get('종료자수',0),
            ])
        return result

    def make_complex_json(items):
        result = []
        for d in sorted(items, key=lambda x: (x.get('시도',''), x.get('시군구',''), x.get('단지명',''))):
            result.append([
                d.get('시도',''), d.get('시군구',''), d.get('단지명',''),
                d.get('주소',''), d.get('공급유형',''), d.get('주택유형',''),
                d.get('주택형_m2',''), round(float(d.get('전용면적',0) or 0), 1),
                int(d.get('세대수',0) or 0), int(d.get('보증금',0) or 0),
                int(d.get('월임대료',0) or 0), d.get('공급기관',''),
            ])
        return result

    wait_json    = json.dumps(make_wait_json(waitlist_data), ensure_ascii=False)
    cplx_json    = json.dumps(make_complex_json(complex_data), ensure_ascii=False)

    # 대기현황 지역 목록 (필터용)
    wait_sidos   = sorted(set(d.get("시도","") for d in waitlist_data if d.get("시도")))
    wait_signgu_seoul = sorted(set(d.get("시군구","") for d in waitlist_data if "서울" in d.get("시도","") and d.get("시군구")))
    wait_signgu_gg    = sorted(set(d.get("시군구","") for d in waitlist_data if "경기" in d.get("시도","") and d.get("시군구")))

    wait_seoul_options = "".join(f'<option value="{s}">{s}</option>' for s in wait_signgu_seoul)
    wait_gg_options    = "".join(f'<option value="{s}">{s}</option>' for s in wait_signgu_gg)

    cplx_sidos   = sorted(set(d.get("시도","") for d in complex_data if d.get("시도")))
    cplx_signgu_seoul = sorted(set(d.get("시군구","") for d in complex_data if "서울" in d.get("시도","") and d.get("시군구")))
    cplx_signgu_gg    = sorted(set(d.get("시군구","") for d in complex_data if "경기" in d.get("시도","") and d.get("시군구")))

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🏠 부동산 소식 알리미 v2</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Apple SD Gothic Neo','Noto Sans KR',sans-serif;background:#f0f2f5;color:#222}}

/* 헤더 */
.header{{background:linear-gradient(135deg,#1a3c5e,#2d6a9f);color:#fff;padding:22px 28px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}}
.header h1{{font-size:1.5rem;margin-bottom:4px}}
.header p{{font-size:.85rem;opacity:.85}}
.hdr-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.hdr-btn{{cursor:pointer;font-size:.82rem;font-weight:600;padding:8px 15px;border-radius:8px;background:rgba(255,255,255,.14);color:#fff;white-space:nowrap;border:1px solid rgba(255,255,255,.3)}}
.hdr-btn:hover{{background:rgba(255,255,255,.28)}}
.hdr-btn.active{{background:#fff;color:#1a3c5e}}
.hdr-btn.prefs{{background:#fff;color:#6a1b9a;font-weight:800;border:none;box-shadow:0 2px 10px rgba(0,0,0,.25);animation:prefsPulse 2.4s ease-in-out infinite}}
.hdr-btn.prefs.active{{background:#f3e5f5;color:#6a1b9a}}
@keyframes prefsPulse{{0%,100%{{box-shadow:0 2px 8px rgba(0,0,0,.2)}}50%{{box-shadow:0 0 16px rgba(255,255,255,.55)}}}}


/* KPI */
.kpi-bar{{display:flex;gap:12px;padding:16px 28px;background:#fff;border-bottom:1px solid #e0e0e0;flex-wrap:wrap}}
.kpi{{background:#f8f9fa;border-radius:10px;padding:12px 18px;min-width:120px;text-align:center;border-top:4px solid #2d6a9f}}
.kpi .num{{font-size:2rem;font-weight:800;color:#1a3c5e;line-height:1}}
.kpi .lbl{{font-size:.75rem;color:#666;margin-top:4px}}
.kpi.new-kpi{{border-top-color:#e65100;background:#fff8f0}}
.kpi.new-kpi .num{{color:#e65100}}
.kpi.red-kpi{{border-top-color:#c62828}}
.kpi.red-kpi .num{{color:#c62828}}
.kpi.green-kpi{{border-top-color:#2e7d32}}
.kpi.green-kpi .num{{color:#2e7d32}}

/* 탭 */
.tab-bar{{display:flex;padding:0 28px;background:#fff;border-bottom:2px solid #e0e0e0;gap:2px}}
.tab{{padding:11px 18px;cursor:pointer;font-size:.88rem;border-bottom:3px solid transparent;color:#888;font-weight:500;white-space:nowrap}}
.tab.active{{color:#1a3c5e;border-bottom-color:#2d6a9f;font-weight:700}}
.tab.new-tab{{color:#e65100}}
.tab.new-tab.active{{border-bottom-color:#e65100}}

/* 필터 */
.filter-bar{{padding:12px 28px;background:#fff;border-bottom:1px solid #eee;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.filter-bar input,.filter-bar select{{padding:7px 10px;border:1px solid #ccc;border-radius:6px;font-size:.84rem}}
.filter-bar input{{width:220px}}
.btn{{padding:7px 14px;border-radius:6px;border:none;cursor:pointer;font-size:.83rem;font-weight:600}}
.btn-primary{{background:#2d6a9f;color:#fff}}
.btn-reset{{background:#eee;color:#555}}
.count-info{{margin-left:auto;font-size:.82rem;color:#888}}
/* 빠른 프리셋 */
.preset-bar{{padding:10px 28px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#fff}}
.preset-lbl{{font-size:.8rem;color:#888;font-weight:600;margin-right:2px}}
.preset-btn{{padding:6px 13px;border:1px solid #d0d7de;border-radius:18px;background:#f6f8fa;color:#333;font-size:.8rem;cursor:pointer;font-weight:600}}
.preset-btn:hover{{background:#2d6a9f;color:#fff;border-color:#2d6a9f}}
.preset-btn.preset-clear{{background:#fff;color:#999;border-style:dashed}}
.preset-btn.preset-clear:hover{{background:#c62828;color:#fff;border-color:#c62828}}
.preset-btn.active{{background:#1565c0;color:#fff;border-color:#1565c0}}
/* 활성 필터 칩 */
.chip-bar{{padding:0 28px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
.chip-bar:not(:empty){{padding-top:10px}}
.chip{{display:inline-flex;align-items:center;gap:6px;background:#e3f2fd;color:#1565c0;border-radius:14px;padding:4px 10px;font-size:.78rem;font-weight:600}}
.chip .x{{cursor:pointer;font-weight:800;opacity:.7}}
.chip .x:hover{{opacity:1}}

/* 범례 */
.legend{{padding:10px 28px 0;display:flex;gap:14px;flex-wrap:wrap;font-size:.78rem;color:#555}}
.legend-item{{display:flex;align-items:center;gap:5px}}
.legend-box{{width:14px;height:14px;border-radius:3px}}

/* 테이블 */
.table-wrap{{padding:16px 28px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:.83rem;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.09)}}
thead tr{{background:#1a3c5e;color:#fff}}
th{{padding:10px 8px;text-align:center;font-weight:600;white-space:nowrap;font-size:.82rem}}
td{{padding:8px 8px;border-bottom:1px solid #f0f0f0;vertical-align:middle}}
.title-cell{{max-width:360px}}
.title-cell a{{color:#1a3c5e;text-decoration:none;font-weight:500;line-height:1.4}}
.title-cell a:hover{{color:#2d6a9f;text-decoration:underline}}
.type-cell{{white-space:nowrap;font-size:.78rem;color:#555}}
.src-cell{{font-size:.75rem;color:#888}}

/* 행 색상 */
.row-new  td{{background:#FFF8DC!important}}
.row-new  td:first-child{{border-left:4px solid #222}}
.row-top  td{{background:#FFD6D6!important}}
.row-best td{{background:#FFECEC!important}}
.row-high td{{background:#FFFDE7!important}}
.row-star td{{background:#F0FFF4!important}}
tr:hover td{{opacity:.92}}

/* 대기현황 행 색상 */
.wait-high td{{background:#fde0e0!important}}
.wait-mid  td{{background:#fff8e1!important}}
.wait-low  td{{background:#f1f8e9!important}}

/* 뱃지 */
.badge{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:.7rem;font-weight:700;margin:1px}}
.badge.red{{background:#fde0e0;color:#c62828}}
.badge.orange{{background:#fff3e0;color:#e65100}}
.badge.yellow{{background:#fffde7;color:#f9a825}}
.badge.gray{{background:#f5f5f5;color:#757575}}
.badge.green{{background:#e8f5e9;color:#2e7d32}}
.layer-badge{{display:inline-block;background:#ede7f6;color:#5e35b1;border-radius:9px;padding:1px 7px;font-size:.68rem;font-weight:700;margin:1px 2px 1px 0}}
.layer-badge.layer-unknown{{background:#f0f0f0;color:#999;font-weight:600}}
.new-badge{{display:inline-block;background:#e65100;color:#fff;padding:2px 8px;border-radius:4px;font-size:.72rem;font-weight:800;margin-right:4px;animation:pulse 1.5s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.7}}}}

.hidden{{display:none}}
.no-data{{text-align:center;color:#aaa;padding:40px;font-size:.9rem}}
.footer{{text-align:center;padding:20px;color:#aaa;font-size:.78rem}}

/* ───── 모바일 반응형 (≤640px) ───── */
@media (max-width: 640px) {{
  .header{{padding:14px 14px;flex-direction:column;align-items:flex-start;gap:10px}}
  .header h1{{font-size:1.15rem}}
  .header p{{font-size:.72rem;line-height:1.4}}
  .hdr-actions{{width:100%;gap:6px}}
  .hdr-btn{{flex:1;text-align:center;padding:8px 6px;font-size:.74rem}}

  .kpi-bar{{padding:10px 12px;gap:8px;flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch}}
  .kpi{{min-width:88px;padding:8px 10px;flex:0 0 auto}}
  .kpi .num{{font-size:1.35rem}}
  .kpi .lbl{{font-size:.64rem;white-space:nowrap}}

  .tab-bar{{padding:0 12px;flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch}}
  .tab{{padding:9px 11px;font-size:.8rem;flex:0 0 auto}}
  .tab[style*="margin-left:auto"]{{margin-left:0 !important}}

  .preset-bar{{padding:10px 12px 0}}
  .filter-bar{{padding:10px 12px;gap:8px}}
  .filter-bar input{{flex:1 1 100%;width:100%}}
  .filter-bar select{{flex:1 1 45%;width:auto;min-width:0}}
  .count-info{{margin-left:0;flex:1 1 100%}}
  .legend,.chip-bar{{padding-left:12px;padding-right:12px}}

  /* 공고 표 — 가로 스크롤 (좁은 화면에서 칸 안 뭉개지게) */
  #tbl-new,#tbl-all,#tbl-rental,#tbl-sale,#tbl-wait,#tbl-cplx{{min-width:660px}}
  th,td{{padding:7px 6px;font-size:.78rem}}
  .title-cell{{max-width:220px}}

  /* 기초학습·활용법 카드 — 1열로 */
  #sec-learn [style*="grid-template-columns:1fr 1fr"],
  #sec-guide [style*="grid-template-columns:1fr 1fr"]{{grid-template-columns:1fr !important}}
  #sec-learn,#sec-guide,#sec-prefs{{padding:16px 14px !important}}
}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>🏠 부동산 소식 알리미 v2</h1>
    <p>기금정책형 | 서울+경기권 | 신혼부부·생애최초 우선 | 마지막 수집: {today_str}</p>
  </div>
  <div class="hdr-actions">
    <div class="hdr-btn prefs" onclick="switchTab('prefs')" id="tab-prefs">✍️ 내 요건 넣기</div>
    <div class="hdr-btn" onclick="switchTab('learn')" id="tab-learn">📚 기초학습</div>
    <div class="hdr-btn" onclick="switchTab('guide')" id="tab-guide">📖 활용법</div>
  </div>
</div>

<div class="kpi-bar">
  <div class="kpi new-kpi"><div class="num">{new_count}</div><div class="lbl">🆕 신규 공고</div></div>
  <div class="kpi"><div class="num">{total}</div><div class="lbl">총 공고 수</div></div>
  <div class="kpi green-kpi"><div class="num">{star_rental}</div><div class="lbl">⭐ 신혼·생초 (임대)</div></div>
  <div class="kpi green-kpi"><div class="num">{star_sale}</div><div class="lbl">⭐ 신혼·생초 (분양)</div></div>
  <div class="kpi"><div class="num">{len(rental)}</div><div class="lbl">🏠 장기임대</div></div>
  <div class="kpi"><div class="num">{len(sale)}</div><div class="lbl">🏗️ 청약·분양</div></div>
</div>

<div class="tab-bar">
  <div class="tab new-tab active" onclick="switchTab('new')"     id="tab-new">🆕 신규 ({new_count}건)</div>
  <div class="tab" onclick="switchTab('all')"    id="tab-all">전체 ({total}건)</div>
  <div class="tab" onclick="switchTab('rental')" id="tab-rental">🏠 장기임대 ({len(rental)}건)</div>
  <div class="tab" onclick="switchTab('sale')"   id="tab-sale">🏗️ 청약·분양 ({len(sale)}건)</div>
  <div class="tab" onclick="switchTab('wait')"   id="tab-wait" style="color:#5c6bc0;margin-left:auto">⏳ 대기현황 ({len(waitlist_data):,}건)</div>
  <div class="tab" onclick="switchTab('cplx')"   id="tab-cplx" style="color:#00897b">🏘️ 단지정보 ({len(complex_data):,}건)</div>
</div>

<div class="legend">
  <span class="legend-item"><span class="legend-box" style="background:#FFF8DC;border-left:4px solid #e65100"></span>신규 공고</span>
  <span class="legend-item"><span class="legend-box" style="background:#F0FFF4"></span>신혼·생초 해당</span>
</div>

<div class="preset-bar">
  <span class="preset-lbl">빠른 필터:</span>
  <button class="preset-btn" data-preset="recruit" onclick="presetRecruit()">🟢 모집공고만</button>
  <button class="preset-btn" data-preset="new" onclick="presetNew()">🆕 오늘 신규만</button>
  <button class="preset-btn" data-preset="rental" onclick="presetRental()">🏠 임대만</button>
  <button class="preset-btn" data-preset="sale" onclick="presetSale()">🏗️ 분양만</button>
  <button class="preset-btn preset-clear" onclick="resetFilter()">✕ 전체 해제</button>
</div>

<div class="filter-bar">
  <input type="text" id="searchInput" placeholder="🔍 공고명 검색..." oninput="applyFilter()">
  <select id="regionSel" onchange="applyFilter()">
    <option value="">지역 전체</option>
    <option value="서울">서울</option>
    <option value="경기">경기</option>
    <option value="인천">인천</option>
    <option value="전국">전국</option>
  </select>
  <select id="districtSel" onchange="applyFilter()">
    <option value="">시·군·구 전체</option>
    {district_options}
  </select>
  <select id="incomeSel" onchange="applyFilter()">
    <option value="">소득구간 전체</option>
    <option value="0">💰 월소득 ~300만원</option>
    <option value="1">💰 월소득 300~400만원</option>
    <option value="2">💰 월소득 400~500만원</option>
    <option value="3">💰 월소득 500~600만원</option>
    <option value="4">💰 월소득 600~700만원</option>
  </select>
  <select id="noticeTypeSel" onchange="applyFilter()">
    <option value="">공고유형 전체</option>
    <option value="🟢 모집공고">🟢 모집공고</option>
    <option value="🔵 당첨·배정">🔵 당첨·배정</option>
    <option value="🟡 계약·서류">🟡 계약·서류</option>
    <option value="⚪ 행정공지">⚪ 행정공지</option>
  </select>
  <select id="typeSel" onchange="applyFilter()">
    <option value="">유형 전체</option>
    <option value="행복주택">행복주택</option>
    <option value="매입임대">매입임대</option>
    <option value="국민임대">국민임대</option>
    <option value="통합임대">통합임대</option>
    <option value="장기전세">장기전세</option>
    <option value="전세임대">전세임대</option>
    <option value="공공분양">공공분양</option>
    <option value="신혼희망">신혼희망</option>
    <option value="청년안심">청년안심</option>
    <option value="기숙사">기숙사</option>
    <option value="두레주택">두레주택</option>
    <option value="든든주택">든든주택</option>
    <option value="영구임대">영구임대</option>
    <option value="공공임대">공공임대</option>
  </select>
  <select id="srcSel" onchange="applyFilter()">
    <option value="">출처 전체</option>
    <option value="LH">LH</option>
    <option value="SH">SH</option>
    <option value="GH">GH</option>
    <option value="마이홈">마이홈포털</option>
  </select>
  <select id="starSel" onchange="applyFilter()">
    <option value="">신혼·생초 전체</option>
    <option value="1">⭐ 신혼·생초만</option>
  </select>
  <select id="layerSel" onchange="applyFilter()">
    <option value="">대상계층 전체</option>
    <option value="신생아">👶 신생아</option>
    <option value="청년">🧑 청년</option>
    <option value="신혼부부">💑 신혼부부</option>
    <option value="생애최초">🌱 생애최초</option>
    <option value="다자녀">👪 다자녀</option>
    <option value="노부모">👵 노부모부양</option>
  </select>
  <button class="btn btn-reset" onclick="resetFilter()">초기화</button>
  <button id="noticeEligBtn" onclick="toggleNoticeElig()"
    style="padding:6px 12px;border:none;border-radius:6px;background:#eee;color:#333;font-size:.8rem;cursor:pointer;font-weight:600">
    🔍 요건 필터
  </button>
  <span class="count-info" id="countInfo"></span>
</div>

<div class="chip-bar" id="chipBar"></div>

<!-- 신규 탭 -->
<div class="table-wrap" id="sec-new">
  <table id="tbl-new"><thead><tr>
    <th>구분</th><th>유형</th><th>공고명</th><th>지역</th>
    <th>게시일</th><th>마감일</th><th>상태</th><th>출처</th>
  </tr></thead><tbody>{new_rows if new_rows else '<tr><td colspan="8" class="no-data">신규 공고가 없습니다</td></tr>'}</tbody></table>
</div>
<!-- 전체 탭 -->
<div class="table-wrap hidden" id="sec-all">
  <table id="tbl-all"><thead><tr>
    <th>구분</th><th>유형</th><th>공고명</th><th>지역</th>
    <th>게시일</th><th>마감일</th><th>상태</th><th>출처</th>
  </tr></thead><tbody>{all_rows}</tbody></table>
</div>
<!-- 장기임대 탭 -->
<div class="table-wrap hidden" id="sec-rental">
  <table id="tbl-rental"><thead><tr>
    <th>구분</th><th>유형</th><th>공고명</th><th>지역</th>
    <th>게시일</th><th>마감일</th><th>상태</th><th>출처</th>
  </tr></thead><tbody>{rental_rows}</tbody></table>
</div>
<!-- 청약 탭 -->
<div class="table-wrap hidden" id="sec-sale">
  <table id="tbl-sale"><thead><tr>
    <th>구분</th><th>유형</th><th>공고명</th><th>지역</th>
    <th>게시일</th><th>마감일</th><th>상태</th><th>출처</th>
  </tr></thead><tbody>{sale_rows}</tbody></table>
</div>

<!-- 대기현황 탭 -->
<div class="table-wrap hidden" id="sec-wait">
  <div class="filter-bar">
    <select id="waitSido" onchange="filterWait()">
      <option value="">시도 전체</option>
      <option value="서울">서울특별시</option>
      <option value="경기">경기도</option>
    </select>
    <select id="waitSigngu" onchange="filterWait()">
      <option value="">시군구 전체</option>
      {wait_seoul_options}
      {wait_gg_options}
    </select>
    <input type="text" id="waitSearch" placeholder="🔍 단지명 검색..." oninput="filterWait()" style="width:200px">
    <button class="btn btn-reset" onclick="resetWait()">초기화</button>
    <span class="count-info" id="waitCount"></span>
  </div>
  <div style="padding:6px 28px;font-size:.78rem;color:#888">
    🔴 대기자 100명 이상 &nbsp;|&nbsp; 🟡 30~99명 &nbsp;|&nbsp; 🟢 30명 미만 → 당첨 가능성 높음
  </div>
  <table id="tbl-wait">
    <thead><tr>
      <th>시도</th><th>시군구</th><th>단지명</th><th>주소</th>
      <th>공급유형</th><th>주택유형</th><th>주택형</th>
      <th onclick="sortWait('대기자수')" style="cursor:pointer">대기자수▼</th>
      <th>종료자수</th>
    </tr></thead>
    <tbody></tbody>
  </table>
</div>

<!-- 단지정보 탭 -->
<div class="table-wrap hidden" id="sec-cplx">
  <div class="filter-bar">
    <select id="cplxSido" onchange="filterCplx()">
      <option value="">시도 전체</option>
      <option value="서울">서울특별시</option>
      <option value="경기">경기도</option>
    </select>
    <select id="cplxSigngu" onchange="filterCplx()">
      <option value="">시군구 전체</option>
      {"".join(f'<option value="{s}">{s}</option>' for s in cplx_signgu_seoul)}
      {"".join(f'<option value="{s}">{s}</option>' for s in cplx_signgu_gg)}
    </select>
    <select id="cplxType" onchange="filterCplx()">
      <option value="">공급유형 전체</option>
      <option value="국민임대">국민임대</option>
      <option value="행복주택">행복주택</option>
      <option value="통합공공임대">통합공공임대</option>
      <option value="매입임대">매입임대</option>
      <option value="영구임대">영구임대</option>
    </select>
    <input type="text" id="cplxSearch" placeholder="🔍 단지명 검색..." oninput="filterCplx()" style="width:200px">
    <button class="btn btn-reset" onclick="resetCplx()">초기화</button>
    <button id="cplxEligBtn" onclick="toggleCplxElig()"
      style="padding:6px 12px;border:none;border-radius:6px;background:#eee;color:#333;font-size:.8rem;cursor:pointer;font-weight:600">
      🔍 요건 필터
    </button>
    <span class="count-info" id="cplxCount"></span>
  </div>
  <table id="tbl-cplx">
    <thead><tr>
      <th>시도</th><th>시군구</th><th>단지명</th><th>주소</th>
      <th>공급유형</th><th>주택유형</th><th>주택형</th><th>전용면적</th>
      <th>세대수</th>
      <th onclick="sortCplx('보증금')" style="cursor:pointer">보증금▲</th>
      <th>월임대료</th><th>공급기관</th>
    </tr></thead>
    <tbody></tbody>
  </table>
</div>

<!-- 내 요건 설정 탭 -->
<div class="table-wrap hidden" id="sec-prefs" style="max-width:560px;margin:0 auto;padding:24px 28px">
  <div style="background:linear-gradient(135deg,#6a1b9a,#ab47bc);color:#fff;border-radius:14px;padding:22px 26px;margin-bottom:20px">
    <div style="font-size:1.3rem;font-weight:800;margin-bottom:4px">⚙️ 내 요건 설정</div>
    <div style="font-size:.85rem;opacity:.85">요건에 맞는 공고만 강조 표시되고, Slack 알림도 이 기준으로 발송됩니다</div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:22px 24px;box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;flex-direction:column;gap:18px">

    <!-- 희망지역 -->
    <div>
      <div style="font-size:.82rem;font-weight:700;color:#555;margin-bottom:8px">📍 희망지역</div>
      <div style="display:flex;gap:16px">
        <label style="display:flex;align-items:center;gap:6px;font-size:.88rem;cursor:pointer;font-weight:600">
          <input type="checkbox" id="pref-region-seoul" checked style="width:17px;height:17px;accent-color:#6a1b9a"> 서울
        </label>
        <label style="display:flex;align-items:center;gap:6px;font-size:.88rem;cursor:pointer;font-weight:600">
          <input type="checkbox" id="pref-region-gg" checked style="width:17px;height:17px;accent-color:#6a1b9a"> 경기
        </label>
        <label style="display:flex;align-items:center;gap:6px;font-size:.88rem;cursor:pointer;font-weight:600">
          <input type="checkbox" id="pref-region-ic" style="width:17px;height:17px;accent-color:#6a1b9a"> 인천
        </label>
      </div>
    </div>

    <!-- 월소득 -->
    <div>
      <label style="font-size:.82rem;font-weight:700;color:#555;display:block;margin-bottom:6px">
        💰 월평균소득 <span style="font-weight:400;color:#888">(만원 · 세전)</span>
      </label>
      <input type="number" id="pref-income" value="500" min="0" placeholder="예: 500"
        style="width:100%;padding:10px 12px;border:1px solid #ccc;border-radius:8px;font-size:.92rem">
      <div style="font-size:.75rem;color:#aaa;margin-top:4px">도시근로자 월평균소득 기준 → 2인 542만원 / 3인 720만원 / 4인 825만원</div>
    </div>

    <!-- 최대보증금 -->
    <div>
      <label style="font-size:.82rem;font-weight:700;color:#555;display:block;margin-bottom:6px">
        🏦 최대보증금 <span style="font-weight:400;color:#888">(만원 · 단지 탭 필터에 적용)</span>
      </label>
      <input type="number" id="pref-deposit" value="40000" min="0" placeholder="예: 40000"
        style="width:100%;padding:10px 12px;border:1px solid #ccc;border-radius:8px;font-size:.92rem">
      <div style="font-size:.75rem;color:#aaa;margin-top:4px">예) 4억 → 40000 · 비워두면 보증금 제한 없음</div>
    </div>

    <!-- 혼인신고일 -->
    <div>
      <label style="font-size:.82rem;font-weight:700;color:#555;display:block;margin-bottom:6px">
        💍 혼인신고일 <span style="font-weight:400;color:#888">(미혼이면 비워두세요)</span>
      </label>
      <input type="date" id="pref-marriage-date"
        style="width:100%;padding:10px 12px;border:1px solid #ccc;border-radius:8px;font-size:.92rem">
      <div style="font-size:.75rem;color:#aaa;margin-top:4px">신혼 공고는 혼인 7년 이내 여부를 자동 계산합니다</div>
    </div>

    <!-- 무주택 -->
    <div style="display:flex;align-items:center;gap:10px;padding:12px 14px;background:#f8f0ff;border-radius:8px">
      <input type="checkbox" id="pref-nohome" checked style="width:19px;height:19px;accent-color:#6a1b9a;cursor:pointer">
      <label for="pref-nohome" style="font-size:.88rem;color:#333;cursor:pointer;font-weight:600">🏠 무주택자입니다</label>
      <span style="font-size:.75rem;color:#999;margin-left:4px">(유주택자는 대부분 공고 대상 외)</span>
    </div>

  </div>

  <!-- 개인정보 안내 -->
  <div style="margin-top:14px;padding:12px 16px;background:#f0f7ff;border-radius:8px;border-left:3px solid #2196f3">
    <div style="font-size:.78rem;color:#1565c0;font-weight:700;margin-bottom:4px">🔒 개인정보 보호 안내</div>
    <div style="font-size:.75rem;color:#444;line-height:1.6">
      입력하신 정보는 <strong>이 브라우저(localStorage)</strong>에만 저장됩니다.<br>
      서버 전송 없음 · 파일에 저장 안 됨 · HTML 공유 시 포함되지 않음.
    </div>
  </div>

  <button onclick="savePrefs()" style="width:100%;padding:14px;background:linear-gradient(135deg,#6a1b9a,#ab47bc);color:#fff;border:none;border-radius:10px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:16px;margin-bottom:8px">
    💾 저장 & 필터 적용
  </button>
  <div id="prefs-save-msg" style="display:none;text-align:center;color:#2e7d32;font-size:.88rem;font-weight:600;margin-bottom:8px">✅ 저장됐습니다! 공고에 요건 배지가 표시됩니다.</div>
  <div style="font-size:.75rem;color:#aaa;text-align:center;line-height:1.6">
    Slack 알림에도 반영하려면 스크립트 폴더의 <code>user_prefs.json</code>을 같은 값으로 업데이트하세요
  </div>
</div>

<!-- 사용법·활용팁 탭 -->
<div class="table-wrap hidden" id="sec-guide" style="max-width:900px;margin:0 auto;padding:24px 28px">

  <div style="background:linear-gradient(135deg,#1a3c5e,#2d6a9f);color:#fff;border-radius:14px;padding:24px 28px;margin-bottom:24px">
    <div style="font-size:1.4rem;font-weight:800;margin-bottom:6px">📖 부동산 소식 알리미 — 사용법 & 활용팁</div>
    <div style="font-size:.88rem;opacity:.85">기금정책형 공공임대·분양 정보를 한눈에 | 신혼부부·생애최초 우선 지원</div>
  </div>

  <!-- ① 탭 구조 설명 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1rem;font-weight:700;color:#1a3c5e;margin-bottom:14px;border-bottom:2px solid #e8edf2;padding-bottom:8px">🗂️ 탭별 기능 설명</div>
    <table style="width:100%;border-collapse:collapse;font-size:.85rem">
      <tr style="background:#f8f9fa">
        <th style="padding:10px 12px;text-align:left;border-radius:6px 0 0 6px;color:#1a3c5e;width:160px">탭</th>
        <th style="padding:10px 12px;text-align:left;color:#1a3c5e">내용</th>
        <th style="padding:10px 12px;text-align:left;border-radius:0 6px 6px 0;color:#1a3c5e">추천 활용</th>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0">
        <td style="padding:10px 12px"><span style="background:#fff3e0;color:#e65100;padding:3px 8px;border-radius:6px;font-weight:700;font-size:.82rem">🆕 신규</span></td>
        <td style="padding:10px 12px">오늘 새로 올라온 공고만 표시</td>
        <td style="padding:10px 12px;color:#555">매일 열 때 <strong>첫 번째로</strong> 확인</td>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0">
        <td style="padding:10px 12px"><span style="background:#e3f2fd;color:#1565c0;padding:3px 8px;border-radius:6px;font-weight:700;font-size:.82rem">전체</span></td>
        <td style="padding:10px 12px">수집된 모든 공고 통합 보기</td>
        <td style="padding:10px 12px;color:#555">키워드 검색 + 지역 필터 조합</td>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0">
        <td style="padding:10px 12px"><span style="background:#e8f5e9;color:#2e7d32;padding:3px 8px;border-radius:6px;font-weight:700;font-size:.82rem">🏠 장기임대</span></td>
        <td style="padding:10px 12px">LH·SH·GH·마이홈 임대 공고</td>
        <td style="padding:10px 12px;color:#555">🟢 모집공고만 필터 → 지금 신청 가능한 것만</td>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0">
        <td style="padding:10px 12px"><span style="background:#fce4ec;color:#c62828;padding:3px 8px;border-radius:6px;font-weight:700;font-size:.82rem">🏗️ 청약·분양</span></td>
        <td style="padding:10px 12px">공공분양·사전청약 공고</td>
        <td style="padding:10px 12px;color:#555">신혼희망타운·생애최초 필터 활용</td>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0">
        <td style="padding:10px 12px"><span style="background:#ede7f6;color:#4527a0;padding:3px 8px;border-radius:6px;font-weight:700;font-size:.82rem">⏳ 대기현황</span></td>
        <td style="padding:10px 12px">단지별 예비입주자 대기자 수</td>
        <td style="padding:10px 12px;color:#555">🟢 초록 행 = 대기 30명 미만 → 당첨 가능성 ↑</td>
      </tr>
      <tr>
        <td style="padding:10px 12px"><span style="background:#e0f2f1;color:#00695c;padding:3px 8px;border-radius:6px;font-weight:700;font-size:.82rem">🏘️ 단지정보</span></td>
        <td style="padding:10px 12px">공공임대 단지 위치·보증금·월임대료</td>
        <td style="padding:10px 12px;color:#555">보증금 낮은 순 확인 → 예산 맞는 단지 탐색</td>
      </tr>
    </table>
  </div>

  <!-- ② 색상 의미 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1rem;font-weight:700;color:#1a3c5e;margin-bottom:14px;border-bottom:2px solid #e8edf2;padding-bottom:8px">🎨 행 색상 의미</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:.84rem">
      <div style="display:flex;align-items:center;gap:10px;background:#FFF8DC;border-left:4px solid #e65100;padding:10px 12px;border-radius:6px">
        <span style="font-size:1.1rem">🆕</span>
        <div><strong>오늘 신규 공고</strong><br><span style="color:#666;font-size:.78rem">오늘 처음 수집된 공고</span></div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;background:#F0FFF4;padding:10px 12px;border-radius:6px">
        <span style="font-size:1.1rem">⭐</span>
        <div><strong>신혼·생애최초 해당</strong><br><span style="color:#666;font-size:.78rem">제목에 신혼·행복·생애최초 키워드 포함</span></div>
      </div>
    </div>
    <div style="font-size:.78rem;color:#999;margin-top:10px">※ 어떤 공고가 더 나은지는 개인 상황(소득·지역·가구)에 따라 다르므로 우선순위 표시는 제공하지 않습니다. <strong>내 요건 넣기</strong>로 적합 공고를 직접 확인하세요.</div>
  </div>

  <!-- ③ 공고유형 분류 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1rem;font-weight:700;color:#1a3c5e;margin-bottom:14px;border-bottom:2px solid #e8edf2;padding-bottom:8px">🏷️ 공고유형 분류 — 어떤 단계인지 바로 파악</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:.84rem">
      <div style="padding:12px;border-radius:8px;background:#e8f5e9;border:1px solid #a5d6a7">
        <div style="font-weight:700;color:#1b5e20;margin-bottom:4px">🟢 모집공고</div>
        <div style="color:#333">지금 청약·신청 접수 중!<br><span style="color:#555;font-size:.78rem">→ 공고 확인 후 바로 신청 가능</span></div>
      </div>
      <div style="padding:12px;border-radius:8px;background:#e3f2fd;border:1px solid #90caf9">
        <div style="font-weight:700;color:#0d47a1;margin-bottom:4px">🔵 당첨·배정</div>
        <div style="color:#333">당첨자 발표, 동호수 배정<br><span style="color:#555;font-size:.78rem">→ 내 이름 있는지 확인</span></div>
      </div>
      <div style="padding:12px;border-radius:8px;background:#fff8e1;border:1px solid #ffe082">
        <div style="font-weight:700;color:#f57f17;margin-bottom:4px">🟡 계약·서류</div>
        <div style="color:#333">서류 제출, 계약 진행 안내<br><span style="color:#555;font-size:.78rem">→ 당첨됐다면 기한 내 제출 필수</span></div>
      </div>
      <div style="padding:12px;border-radius:8px;background:#f5f5f5;border:1px solid #e0e0e0">
        <div style="font-weight:700;color:#616161;margin-bottom:4px">⚪ 행정공지</div>
        <div style="color:#333">시스템 점검, 변경 안내 등<br><span style="color:#555;font-size:.78rem">→ 참고만 해도 됨</span></div>
      </div>
    </div>
  </div>

  <!-- ④ 후배를 위한 활용팁 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1rem;font-weight:700;color:#1a3c5e;margin-bottom:14px;border-bottom:2px solid #e8edf2;padding-bottom:8px">💡 신혼부부를 위한 실전 활용팁</div>
    <div style="display:flex;flex-direction:column;gap:12px;font-size:.85rem">
      <div style="display:flex;gap:12px;align-items:flex-start;padding:12px;background:#f8f9fa;border-radius:8px">
        <span style="font-size:1.4rem;flex-shrink:0">1️⃣</span>
        <div>
          <strong style="color:#1a3c5e">매일 아침 '🆕 신규' 탭 먼저 확인</strong><br>
          <span style="color:#555">신규 공고는 마감이 빠름. 놓치면 6개월~1년 기다려야 다시 기회 옴.</span>
        </div>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-start;padding:12px;background:#f8f9fa;border-radius:8px">
        <span style="font-size:1.4rem;flex-shrink:0">2️⃣</span>
        <div>
          <strong style="color:#1a3c5e">⏳ 대기현황 탭 — 🟢 초록 단지를 공략하라</strong><br>
          <span style="color:#555">대기자 30명 미만인 단지는 당첨 가능성이 상대적으로 높음. 해당 공고가 뜨면 즉시 신청!</span>
        </div>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-start;padding:12px;background:#f8f9fa;border-radius:8px">
        <span style="font-size:1.4rem;flex-shrink:0">3️⃣</span>
        <div>
          <strong style="color:#1a3c5e">🏘️ 단지정보 탭 — 예산 맞는 곳 미리 파악</strong><br>
          <span style="color:#555">보증금·월임대료 컬럼 확인 후 예산에 맞는 지역·단지를 미리 리스트업. 공고 뜨면 바로 지원.</span>
        </div>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-start;padding:12px;background:#fff3e0;border-left:4px solid #e65100;border-radius:8px">
        <span style="font-size:1.4rem;flex-shrink:0">⭐</span>
        <div>
          <strong style="color:#e65100">신혼·생초 필터 = 최우선 확인 항목</strong><br>
          <span style="color:#555">'⭐ 신혼·생초만' 필터 체크 시 신혼부부·생애최초 특별공급 대상 공고만 표시. 일반 공고보다 경쟁 낮고 혜택 큼.</span>
        </div>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-start;padding:12px;background:#f8f9fa;border-radius:8px">
        <span style="font-size:1.4rem;flex-shrink:0">4️⃣</span>
        <div>
          <strong style="color:#1a3c5e">공고유형 '🟢 모집공고'만 필터 — 지금 신청 가능한 것만 보기</strong><br>
          <span style="color:#555">당첨결과·계약안내 등은 제외하고 현재 접수 중인 공고만 빠르게 확인 가능.</span>
        </div>
      </div>
      <div style="display:flex;gap:12px;align-items:flex-start;padding:12px;background:#f8f9fa;border-radius:8px">
        <span style="font-size:1.4rem;flex-shrink:0">5️⃣</span>
        <div>
          <strong style="color:#1a3c5e">이 페이지는 매일 자동 업데이트됨</strong><br>
          <span style="color:#555">스케줄러가 매일 오전 8시에 자동 수집·갱신. 단지정보는 7일 캐시 적용(API 부하 최소화). 상단 '마지막 수집' 시간 확인.</span>
        </div>
      </div>
    </div>
  </div>


  <!-- ⑥ 데이터 출처 -->
  <div style="background:#f8f9fa;border-radius:12px;padding:16px 20px;font-size:.8rem;color:#777;border:1px solid #e0e0e0">
    <strong style="color:#555">📡 데이터 출처</strong><br>
    LH청약플러스(apply.lh.or.kr) · SH서울주택도시공사(i-sh.co.kr) · GH경기주택도시공사(apply.gh.or.kr)<br>
    마이홈포털 OpenAPI — 청약공고(HWSPR02) · 예비입주자 대기현황(HWSPR03) · 단지정보(HWSPR04) — 공공데이터포털 제공<br>
    <span style="color:#e65100">※ 본 페이지 데이터는 참고용입니다. 실제 청약·계약은 반드시 해당 기관 공식 사이트에서 확인하세요.</span>
  </div>

</div>

<!-- ══════════════ 📚 기초학습 패널 ══════════════ -->
<div class="table-wrap hidden" id="sec-learn" style="max-width:900px;margin:0 auto;padding:24px 28px">

  <div style="background:linear-gradient(135deg,#00695c,#26a69a);color:#fff;border-radius:14px;padding:24px 28px;margin-bottom:22px">
    <div style="font-size:1.4rem;font-weight:800;margin-bottom:6px">📚 공공주택 기초학습</div>
    <div style="font-size:.88rem;opacity:.9">알림·대시보드 용어와 통일 — 처음이라면 위에서부터 차근차근 읽어보세요</div>
  </div>

  <!-- 모듈 1: 유형 비교표 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1.05rem;font-weight:700;color:#00695c;margin-bottom:14px;border-bottom:2px solid #e0f2f1;padding-bottom:8px">① 공공주택 유형 한눈에 비교</div>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:.82rem;min-width:640px">
      <tr style="background:#f1f8f6">
        <th style="padding:9px 10px;text-align:left;color:#00695c">유형</th>
        <th style="padding:9px 10px;text-align:left;color:#00695c">주요 대상</th>
        <th style="padding:9px 10px;text-align:left;color:#00695c">소득기준(대략)</th>
        <th style="padding:9px 10px;text-align:left;color:#00695c">임대료·형태</th>
        <th style="padding:9px 10px;text-align:left;color:#00695c">거주기간</th>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:9px 10px;font-weight:700">행복주택</td><td style="padding:9px 10px">청년·신혼·고령자 등</td><td style="padding:9px 10px">도시근로자 100~120%</td><td style="padding:9px 10px">시세 60~80% 임대</td><td style="padding:9px 10px">6~20년</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:9px 10px;font-weight:700">국민임대</td><td style="padding:9px 10px">무주택 저소득</td><td style="padding:9px 10px">70% (소형 50%)</td><td style="padding:9px 10px">시세 60~80% 임대</td><td style="padding:9px 10px">최장 30년</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:9px 10px;font-weight:700">통합공공임대</td><td style="padding:9px 10px">무주택 (소득·자산)</td><td style="padding:9px 10px">기준중위소득 150% 이하</td><td style="padding:9px 10px">시세 35~90% (소득별)</td><td style="padding:9px 10px">최장 30년</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:9px 10px;font-weight:700">매입임대</td><td style="padding:9px 10px">청년·신혼·저소득</td><td style="padding:9px 10px">70~100%</td><td style="padding:9px 10px">시세 30~50% 임대</td><td style="padding:9px 10px">2년 단위 갱신</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:9px 10px;font-weight:700">전세임대</td><td style="padding:9px 10px">청년·신혼·저소득</td><td style="padding:9px 10px">70~100%</td><td style="padding:9px 10px">전세보증금 지원</td><td style="padding:9px 10px">2년 단위 갱신</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:9px 10px;font-weight:700">장기전세</td><td style="padding:9px 10px">무주택 (SH 등)</td><td style="padding:9px 10px">100~150%</td><td style="padding:9px 10px">전세보증금형 (월세 X)</td><td style="padding:9px 10px">최장 20년</td></tr>
      <tr><td style="padding:9px 10px;font-weight:700">공공분양</td><td style="padding:9px 10px">무주택 (특별·일반)</td><td style="padding:9px 10px">유형별 상이</td><td style="padding:9px 10px">분양(소유)</td><td style="padding:9px 10px">소유 (전매제한 有)</td></tr>
    </table>
    </div>
    <div style="font-size:.76rem;color:#999;margin-top:10px">※ 수치는 일반 기준이며 연도·공고별로 달라집니다. 반드시 공고문에서 확인하세요.</div>
  </div>

  <!-- 모듈 2: 소득·자산 기준 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1.05rem;font-weight:700;color:#00695c;margin-bottom:14px;border-bottom:2px solid #e0f2f1;padding-bottom:8px">② 소득·자산 기준 — "내 월급이면 어디까지?"</div>
    <div style="font-size:.85rem;color:#444;margin-bottom:10px">도시근로자 월평균소득(2025년·세전·만원). 알림의 <strong>소득 구간</strong>이 바로 이 표 기준이에요.</div>
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:.82rem;min-width:480px">
      <tr style="background:#f1f8f6">
        <th style="padding:9px 10px;text-align:left;color:#00695c">가구원수</th>
        <th style="padding:9px 10px;text-align:right;color:#00695c">100%</th>
        <th style="padding:9px 10px;text-align:right;color:#00695c">120%(신혼 등)</th>
        <th style="padding:9px 10px;text-align:right;color:#00695c">150%(맞벌이 등)</th>
      </tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:8px 10px">1인</td><td style="padding:8px 10px;text-align:right">348만</td><td style="padding:8px 10px;text-align:right">418만</td><td style="padding:8px 10px;text-align:right">522만</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:8px 10px">2인</td><td style="padding:8px 10px;text-align:right">542만</td><td style="padding:8px 10px;text-align:right">650만</td><td style="padding:8px 10px;text-align:right">813만</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:8px 10px">3인</td><td style="padding:8px 10px;text-align:right">720만</td><td style="padding:8px 10px;text-align:right">864만</td><td style="padding:8px 10px;text-align:right">1,080만</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:8px 10px">4인</td><td style="padding:8px 10px;text-align:right">825만</td><td style="padding:8px 10px;text-align:right">990만</td><td style="padding:8px 10px;text-align:right">1,238만</td></tr>
    </table>
    </div>
    <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
      <div style="flex:1;min-width:200px;background:#f1f8f6;border-radius:8px;padding:12px 14px;font-size:.82rem">
        <strong style="color:#00695c">💰 총자산 기준</strong><br>통합공공임대·장기전세 약 <strong>3.61억</strong> 이하<br>국민·매입·전세임대 약 <strong>2.92억</strong> 이하
      </div>
      <div style="flex:1;min-width:200px;background:#f1f8f6;border-radius:8px;padding:12px 14px;font-size:.82rem">
        <strong style="color:#00695c">🚗 자동차 기준</strong><br>약 <strong>3,683만원</strong> 이하 (현재가치)<br><span style="color:#888;font-size:.76rem">차량가액 초과 시 부적격</span>
      </div>
    </div>
  </div>

  <!-- 모듈 3: 자격 유형 가이드 -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1.05rem;font-weight:700;color:#00695c;margin-bottom:14px;border-bottom:2px solid #e0f2f1;padding-bottom:8px">③ 자격 유형 가이드 — 나는 어디에 해당?</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:.84rem">
      <div style="background:#e8f5e9;border-radius:8px;padding:12px 14px"><strong style="color:#2e7d32">🧑 청년</strong><br>만 19~39세 · 미혼 · 무주택<br><span style="color:#777;font-size:.78rem">대학생·취업준비생·사회초년생 포함</span></div>
      <div style="background:#fce4ec;border-radius:8px;padding:12px 14px"><strong style="color:#c2185b">💍 신혼부부</strong><br>혼인 7년 이내 (예비 포함) · 무주택<br><span style="color:#777;font-size:.78rem">소득기준 우대(120~140%)</span></div>
      <div style="background:#fff3e0;border-radius:8px;padding:12px 14px"><strong style="color:#e65100">👶 신생아</strong><br>2년 이내 출생아 가구 · 무주택<br><span style="color:#777;font-size:.78rem">최근 신설 우선공급 유형</span></div>
      <div style="background:#e3f2fd;border-radius:8px;padding:12px 14px"><strong style="color:#1565c0">🌱 생애최초</strong><br>세대원 전원 주택 소유 이력 없음<br><span style="color:#777;font-size:.78rem">주로 <strong>분양</strong> 특별공급 (임대는 무주택 기준으로 충족)</span></div>
      <div style="background:#ede7f6;border-radius:8px;padding:12px 14px"><strong style="color:#5e35b1">👵 고령자</strong><br>만 65세 이상 · 무주택<br><span style="color:#777;font-size:.78rem">영구·국민임대 우선</span></div>
      <div style="background:#f5f5f5;border-radius:8px;padding:12px 14px"><strong style="color:#555">✅ 공통 필수</strong><br>대부분 <strong>무주택 세대구성원</strong> + 소득·자산 기준 충족</div>
    </div>
  </div>

  <!-- 모듈 4: 절차·용어·FAQ -->
  <div style="background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
    <div style="font-size:1.05rem;font-weight:700;color:#00695c;margin-bottom:14px;border-bottom:2px solid #e0f2f1;padding-bottom:8px">④ 신청 절차 · 용어 · 꿀팁</div>

    <div style="font-weight:700;color:#37474f;margin:4px 0 8px">📋 신청 5단계</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;font-size:.8rem;margin-bottom:18px">
      <span style="background:#e0f2f1;border-radius:20px;padding:6px 12px">1️⃣ 공고 확인</span>
      <span style="color:#bbb;align-self:center">→</span>
      <span style="background:#e0f2f1;border-radius:20px;padding:6px 12px">2️⃣ 자격 체크(소득·무주택)</span>
      <span style="color:#bbb;align-self:center">→</span>
      <span style="background:#e0f2f1;border-radius:20px;padding:6px 12px">3️⃣ 청약통장 확인</span>
      <span style="color:#bbb;align-self:center">→</span>
      <span style="background:#e0f2f1;border-radius:20px;padding:6px 12px">4️⃣ 온라인 신청</span>
      <span style="color:#bbb;align-self:center">→</span>
      <span style="background:#e0f2f1;border-radius:20px;padding:6px 12px">5️⃣ 서류제출·당첨발표</span>
    </div>

    <div style="font-weight:700;color:#37474f;margin:4px 0 8px">📖 핵심 용어</div>
    <table style="width:100%;border-collapse:collapse;font-size:.82rem;margin-bottom:18px">
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:7px 10px;font-weight:700;width:130px;color:#00695c">예비입주자</td><td style="padding:7px 10px">당첨자 외 대기 순번. 앞 순번 포기 시 차례가 옴 (대기현황 탭 참고)</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:7px 10px;font-weight:700;color:#00695c">전매제한</td><td style="padding:7px 10px">분양 후 일정 기간 되팔기 금지</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:7px 10px;font-weight:700;color:#00695c">우선공급</td><td style="padding:7px 10px">신혼·생초·다자녀 등에게 물량 일부 먼저 배정</td></tr>
      <tr style="border-bottom:1px solid #f0f0f0"><td style="padding:7px 10px;font-weight:700;color:#00695c">보증금↔월세 전환</td><td style="padding:7px 10px">보증금 올리면 월세 ↓ (상호 조정 가능한 경우)</td></tr>
      <tr><td style="padding:7px 10px;font-weight:700;color:#00695c">정정공고</td><td style="padding:7px 10px">기존 공고 내용 수정본. <strong>최신 정정본이 유효</strong> (알림은 자동으로 최신만 표시)</td></tr>
    </table>

    <div style="font-weight:700;color:#37474f;margin:4px 0 8px">💡 꿀팁 · FAQ</div>
    <div style="font-size:.83rem;color:#444;line-height:1.7">
      • <strong>대기자 30명 미만 단지</strong>는 당첨 가능성 ↑ → 대기현황 탭 🟢 초록 행 노리기<br>
      • <strong>임대 vs 분양</strong>: 임대는 적은 보증금으로 거주(소유 X), 분양은 소유하지만 목돈·전매제한<br>
      • <strong>중복신청</strong>: 같은 날 여러 공고 신청 가능하나, 동일 공고 내 중복은 부적격될 수 있음<br>
      • <strong>청약통장</strong>: 일부 공공임대는 통장 없이도 가능, 분양은 대부분 필요<br>
      • 신청 전 반드시 <strong>공고문 원문</strong>의 자격·일정·제출서류 확인 (이 페이지는 참고용)
    </div>
  </div>

  <div style="background:#fff8e1;border-radius:10px;padding:14px 18px;font-size:.8rem;color:#7a5c00;border:1px solid #ffe082">
    ⚠️ 본 학습 자료는 이해를 돕기 위한 일반 정보입니다. 실제 자격·기준은 연도·지역·공고별로 다르므로 <strong>반드시 해당 기관 공고문</strong>을 확인하세요.
  </div>

</div>

<div class="footer">수집 데이터는 수집 시점 기준입니다. 정확한 내용은 해당 공급기관에서 확인하세요.</div>

<script>
const WAIT_DATA={wait_json};
const CPLX_DATA={cplx_json};
// 개인정보는 localStorage에만 저장 — HTML에 임베드하지 않음
const USER_PREFS={{}};
</script>
<script>
// ── 도시근로자 월평균 소득 기준 (2025년, 만원) ──────────────
const URBAN_INCOME_BASE = {{1:348,2:542,3:720,4:825,5:878,6:930}};
const INCOME_LIMIT_RATIO = {{
  '통합공공임대':100,'행복주택':100,'장기전세':100,
  '국민임대':70,'매입임대':70,'전세임대':70,'영구임대':50
}};
const ASSET_LIMIT = {{
  '통합공공임대':36100,'행복주택':36100,'장기전세':36100,
  '국민임대':29200,'매입임대':29200,'전세임대':29200,'영구임대':29200
}};
const CAR_ASSET_LIMIT = 3683;

// depositVal: 실제 보증금(만원) — 단지탭에서만 사용, 공고탭은 null
function jsCheckEligibility(regionStr, typeStr, isSinbon, prefs, depositVal) {{
  if(!prefs || Object.keys(prefs).length===0) return {{eligible:true,ok:[],fail:[]}};
  const ok=[], fail=[];
  // 무주택
  if(prefs['무주택']===false) fail.push('무주택 요건 미충족');
  // 희망지역
  const desired = prefs['희망지역']||[];
  if(desired.length>0) {{
    const regionOk = desired.some(r=>regionStr.includes(r)) || regionStr.includes('전국');
    if(regionOk) ok.push('희망지역 포함');
    else fail.push('희망지역 외('+regionStr+')');
  }}
  // 소득 — 실제 금액(만원)으로 비교
  const income = prefs['월소득_만원']||0;
  const fn = Math.min(Math.max(prefs['가구원수']||2,1),6);
  const baseInc = URBAN_INCOME_BASE[fn]||542;
  let limitPct = 100;
  for(const [kw,pct] of Object.entries(INCOME_LIMIT_RATIO)) {{
    if(typeStr.includes(kw)){{ limitPct=pct; break; }}
  }}
  if(isSinbon) limitPct=Math.min(limitPct+20,150);
  const limitWon = Math.round(baseInc * limitPct / 100);
  if(income) {{
    if(income>limitWon) fail.push('월소득 '+income.toLocaleString()+'만원 > 상한 '+limitWon.toLocaleString()+'만원');
    else ok.push('월소득 '+income.toLocaleString()+'만원 ≤ 상한 '+limitWon.toLocaleString()+'만원');
  }}
  // 최대보증금 (단지탭 — depositVal이 있을 때만 체크)
  const maxDep = prefs['최대보증금_만원']||0;
  if(maxDep && depositVal!=null && depositVal>0) {{
    if(depositVal>maxDep) fail.push('보증금 '+fmtMoney(depositVal)+' > 상한 '+fmtMoney(maxDep));
    else ok.push('보증금 '+fmtMoney(depositVal)+' ≤ '+fmtMoney(maxDep));
  }}
  // 신혼 (혼인신고일로 판단)
  if(isSinbon) {{
    const md = prefs['혼인신고일']||'';
    if(md) {{
      const diff = (Date.now()-new Date(md).getTime())/(1000*60*60*24*365.25);
      if(diff>7) fail.push('혼인신고 '+diff.toFixed(1)+'년 경과');
      else ok.push('혼인 '+diff.toFixed(1)+'년 이내');
    }}
    // 혼인신고일 미입력 → 체크 생략 (미혼 가능성 있으므로 통과)
  }}
  return {{eligible:fail.length===0, ok, fail}};
}}

function applyEligibilityBadge() {{
  const prefs = JSON.parse(localStorage.getItem('user_prefs')||'{{}}');
  if(!prefs || Object.keys(prefs).length===0) return;
  document.querySelectorAll('table tbody tr').forEach(row=>{{
    if(row.querySelector('td.no-data')) return;
    const regionStr = row.dataset.region||'';
    const typeStr   = row.dataset.type||'';
    const isSinbon  = row.dataset.star==='1';
    const elig = jsCheckEligibility(regionStr, typeStr, isSinbon, prefs);
    // 기존 배지 제거
    row.querySelectorAll('.elig-badge').forEach(el=>el.remove());
    const firstTd = row.querySelector('td');
    if(!firstTd) return;
    if(elig.eligible) {{
      const span = document.createElement('span');
      span.className='elig-badge';
      span.style.cssText='display:block;font-size:.65rem;color:#2e7d32;font-weight:700;margin-top:3px';
      span.textContent='✅ 내 요건 적합';
      firstTd.appendChild(span);
    }} else if(elig.fail.length>0) {{
      const span = document.createElement('span');
      span.className='elig-badge';
      span.style.cssText='display:block;font-size:.62rem;color:#c62828;margin-top:3px';
      span.textContent='❌ '+elig.fail[0];
      firstTd.appendChild(span);
    }}
  }});
}}

let currentTab = 'new';
let activePreset = null; // 'new' | 'rental' | 'sale' | 'recruit' | null
const tabMap = {{new:'sec-new',all:'sec-all',rental:'sec-rental',sale:'sec-sale',wait:'sec-wait',cplx:'sec-cplx',prefs:'sec-prefs',learn:'sec-learn',guide:'sec-guide'}};

function switchTab(tab){{
  currentTab = tab;
  Object.keys(tabMap).forEach(k=>{{
    document.getElementById(tabMap[k]).classList.toggle('hidden', k!==tab);
    const el=document.getElementById('tab-'+k);
    if(el) el.classList.toggle('active', k===tab);
  }});
  if(tab==='wait') filterWait();
  else if(tab==='cplx') filterCplx();
  else if(tab==='prefs') loadPrefsForm();
  else if(tab==='learn'||tab==='guide') {{ /* 정적 학습/가이드 콘텐츠 — 필터 없음 */ }}
  else {{ applyFilter(); applyEligibilityBadge(); }}
}}

function showNewOnly(){{ switchTab('new'); }}

let noticeEligOnly = false;
function toggleNoticeElig(){{
  noticeEligOnly = !noticeEligOnly;
  const btn = document.getElementById('noticeEligBtn');
  btn.style.background = noticeEligOnly ? '#2e7d32' : '#eee';
  btn.style.color = noticeEligOnly ? '#fff' : '#333';
  btn.textContent = noticeEligOnly ? '✅ 요건 적합만 표시 중' : '🔍 요건 필터';
  applyFilter();
}}

function applyFilter(){{
  const q          = document.getElementById('searchInput').value.toLowerCase();
  const region     = document.getElementById('regionSel').value;
  const district   = document.getElementById('districtSel').value;
  const income     = document.getElementById('incomeSel').value;
  const noticetype = document.getElementById('noticeTypeSel').value;
  const type_      = document.getElementById('typeSel').value;
  const src        = document.getElementById('srcSel').value;
  const star       = document.getElementById('starSel').value;
  const layer      = document.getElementById('layerSel').value;
  const eligPrefs  = noticeEligOnly ? JSON.parse(localStorage.getItem('user_prefs')||'{{}}') : null;
  const tblId      = 'tbl-' + currentTab;
  const rows       = document.querySelectorAll('#'+tblId+' tbody tr');
  let vis = 0;
  rows.forEach(row=>{{
    if(row.querySelector('td.no-data')){{ row.style.display=''; return; }}
    const title   = (row.querySelector('.title-cell')||{{textContent:''}}).textContent.toLowerCase();
    const rg      = row.dataset.region||'';
    const dist    = row.dataset.district||'';
    const inc     = row.dataset.income||'';
    const nt      = row.dataset.noticetype||'';
    const isStar  = row.dataset.star;
    const rowSrc  = row.dataset.src||'';
    const rowType = row.dataset.type||'';   // 원본 유형 (소득 계산용)
    const rowTag  = row.dataset.tag||'';    // 정리 태그 (유형 필터용)
    const rowLayers = row.dataset.layers||''; // 대상계층 (| 구분)
    let ok = (!q||title.includes(q))
          && (!region||rg.includes(region))
          && (!district||dist===district)
          && (!income||inc===income)
          && (!noticetype||nt===noticetype)
          && (!type_||rowTag.includes(type_))
          && (!src||rowSrc.includes(src))
          && (!star||isStar==='1')
          && (!layer||('|'+rowLayers+'|').includes('|'+layer+'|'));
    if(ok && noticeEligOnly && eligPrefs && Object.keys(eligPrefs).length>0) {{
      const elig = jsCheckEligibility(rg, rowType, isStar==='1', eligPrefs, null);
      ok = elig.eligible;
    }}
    row.style.display = ok ? '' : 'none';
    if(ok) vis++;
  }});
  document.getElementById('countInfo').textContent = `${{vis}}건 표시 중`;
  renderChips();
}}

// 활성 필터 칩 렌더링
const INCOME_LABELS = {{'0':'월소득 ~300만','1':'월소득 300~400만','2':'월소득 400~500만','3':'월소득 500~600만','4':'월소득 600~700만'}};
function renderChips(){{
  const bar = document.getElementById('chipBar');
  if(!bar) return;
  const chips = [];
  // 프리셋 탭 칩 (드롭다운에 반영되지 않는 탭 기반 필터)
  const presetLabels = {{new:'🆕 오늘 신규만', rental:'🏠 임대만', sale:'🏗️ 분양만'}};
  if(activePreset && presetLabels[activePreset])
    chips.push(`<span class="chip">${{presetLabels[activePreset]}}<span class="x" onclick="clearPreset()">✕</span></span>`);
  const add = (id, prefix, labelMap) => {{
    const el = document.getElementById(id);
    if(el && el.value){{
      const txt = labelMap ? (labelMap[el.value]||el.value) : (el.options ? el.options[el.selectedIndex].text : el.value);
      chips.push(`<span class="chip">${{prefix}}${{txt}}<span class="x" onclick="clearFilter('${{id}}')">✕</span></span>`);
    }}
  }};
  const qEl = document.getElementById('searchInput');
  if(qEl && qEl.value) chips.push(`<span class="chip">검색: ${{qEl.value}}<span class="x" onclick="clearFilter('searchInput')">✕</span></span>`);
  add('regionSel','지역: ');
  add('districtSel','');
  add('incomeSel','💰 ', INCOME_LABELS);
  add('noticeTypeSel','');
  add('typeSel','유형: ');
  add('srcSel','출처: ');
  add('starSel','');
  add('layerSel','대상: ');
  bar.innerHTML = chips.join('');
}}
function clearFilter(id){{
  const el = document.getElementById(id);
  if(el) el.value = '';
  applyFilter();
}}

// 프리셋 버튼 활성 상태 토글
function setPresetBtnActive(name){{
  document.querySelectorAll('.preset-btn[data-preset]').forEach(b=>{{
    b.classList.toggle('active', b.dataset.preset === name);
  }});
}}

// 프리셋 칩 ✕ 클릭 → 탭 프리셋만 해제 (나머지 드롭다운 필터 유지)
function clearPreset(){{
  activePreset = null;
  setPresetBtnActive(null);
  switchTab('all');
}}

// 빠른 프리셋
function presetRecruit(){{
  resetFilter();
  activePreset = null; // 탭 칩 없음 (noticeTypeSel 칩으로 표시)
  setPresetBtnActive('recruit');
  document.getElementById('noticeTypeSel').value='🟢 모집공고';
  applyFilter();
}}
function presetNew(){{
  resetFilter();
  activePreset = 'new';
  setPresetBtnActive('new');
  switchTab('new');
}}
function presetRental(){{
  resetFilter();
  activePreset = 'rental';
  setPresetBtnActive('rental');
  switchTab('rental');
  document.getElementById('noticeTypeSel').value='🟢 모집공고';
  applyFilter();
}}
function presetSale(){{
  resetFilter();
  activePreset = 'sale';
  setPresetBtnActive('sale');
  switchTab('sale');
  document.getElementById('noticeTypeSel').value='🟢 모집공고';
  applyFilter();
}}

function resetFilter(){{
  activePreset = null;
  setPresetBtnActive(null);
  document.getElementById('searchInput').value='';
  ['regionSel','districtSel','incomeSel','noticeTypeSel','typeSel','srcSel','starSel','layerSel'].forEach(id=>document.getElementById(id).value='');
  applyFilter();
}}

// ── 대기현황 렌더링 ────────────────────────────
const WAIT_PAGE = 500;
function renderWait(data){{
  const tbody = document.querySelector('#tbl-wait tbody');
  if(!data.length){{
    tbody.innerHTML='<tr><td colspan="9" class="no-data">조건에 맞는 단지가 없습니다</td></tr>';
    document.getElementById('waitCount').textContent='0건';
    return;
  }}
  const shown = data.slice(0, WAIT_PAGE);
  tbody.innerHTML = shown.map(d=>{{
    const [si,gu,nm,ad,ty,ht,hm,wait,end_]=d;
    const cls=wait>=100?'wait-high':(wait>=30?'wait-mid':'wait-low');
    const wc=wait>=100?'#c62828':(wait>=30?'#e65100':'#2e7d32');
    return `<tr class="${{cls}}"><td>${{si}}</td><td>${{gu}}</td><td class="title-cell">${{nm}}</td><td style="font-size:.75rem;color:#666">${{ad}}</td><td>${{ty}}</td><td>${{ht}}</td><td>${{hm}}</td><td style="font-weight:700;color:${{wc}}">${{wait.toLocaleString()}}</td><td style="color:#888">${{end_.toLocaleString()}}</td></tr>`;
  }}).join('');
  const total=data.length;
  document.getElementById('waitCount').textContent = total<=WAIT_PAGE
    ? `${{total.toLocaleString()}}건`
    : `${{total.toLocaleString()}}건 중 ${{WAIT_PAGE}}건 표시 (필터로 좁혀주세요)`;
}}
function filterWait(){{
  const sido   = document.getElementById('waitSido').value;
  const signgu = document.getElementById('waitSigngu').value;
  const q      = document.getElementById('waitSearch').value.toLowerCase();
  renderWait(WAIT_DATA.filter(d=>{{
    const [si,gu,nm]=d;
    return (!sido||si.includes(sido))&&(!signgu||gu===signgu)&&(!q||nm.toLowerCase().includes(q));
  }}));
}}
function resetWait(){{
  ['waitSido','waitSigngu'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('waitSearch').value='';
  filterWait();
}}
function sortWait(col){{ /* 이미 대기자 내림차순 고정 */ }}

// ── 단지정보 렌더링 ────────────────────────────
const CPLX_PAGE = 300;
function fmtMoney(v){{
  v=parseInt(v)||0; if(!v) return '-';
  if(v>=10000){{ const e=Math.floor(v/10000),r=v%10000; return r>=1000?`${{e}}억${{Math.floor(r/1000).toLocaleString()}}천만`:`${{e}}억`; }}
  return `${{v.toLocaleString()}}만`;
}}
function renderCplx(data){{
  const tbody = document.querySelector('#tbl-cplx tbody');
  if(!data.length){{
    tbody.innerHTML='<tr><td colspan="12" class="no-data">조건에 맞는 단지가 없습니다</td></tr>';
    document.getElementById('cplxCount').textContent='0건';
    return;
  }}
  const shown = data.slice(0, CPLX_PAGE);
  tbody.innerHTML = shown.map(d=>{{
    const [si,gu,nm,ad,ty,ht,hm,ar,hh,bg,mr,ag]=d;
    return `<tr><td>${{si}}</td><td>${{gu}}</td><td class="title-cell">${{nm}}</td><td style="font-size:.75rem;color:#666">${{ad}}</td><td>${{ty}}</td><td>${{ht}}</td><td style="text-align:right">${{hm}}</td><td style="text-align:right">${{ar}}㎡</td><td style="text-align:right">${{hh.toLocaleString()}}</td><td style="text-align:right;color:#1a3c5e;font-weight:600">${{fmtMoney(bg)}}</td><td style="text-align:right;color:#2d6a9f;font-weight:600">${{fmtMoney(mr)}}</td><td style="font-size:.75rem;color:#888">${{ag}}</td></tr>`;
  }}).join('');
  const total=data.length;
  document.getElementById('cplxCount').textContent = total<=CPLX_PAGE
    ? `${{total.toLocaleString()}}건`
    : `${{total.toLocaleString()}}건 중 ${{CPLX_PAGE}}건 표시 (필터로 좁혀주세요)`;
}}
let cplxEligOnly = false;
function filterCplx(){{
  const sido   = document.getElementById('cplxSido').value;
  const signgu = document.getElementById('cplxSigngu').value;
  const type_  = document.getElementById('cplxType').value;
  const q      = document.getElementById('cplxSearch').value.toLowerCase();
  const prefs  = cplxEligOnly ? JSON.parse(localStorage.getItem('user_prefs')||'{{}}') : null;
  renderCplx(CPLX_DATA.filter(d=>{{
    const [si,gu,nm,,ty,,,,,bg]=d;
    const basicOk = (!sido||si.includes(sido))&&(!signgu||gu===signgu)&&(!type_||ty.includes(type_))&&(!q||nm.toLowerCase().includes(q));
    if(!basicOk) return false;
    if(cplxEligOnly && prefs && Object.keys(prefs).length>0) {{
      const elig = jsCheckEligibility(si, ty, false, prefs, bg);
      return elig.eligible;
    }}
    return true;
  }}));
}}
function resetCplx(){{
  ['cplxSido','cplxSigngu','cplxType'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('cplxSearch').value='';
  filterCplx();
}}
function sortCplx(col){{ /* 보증금 오름차순 고정 */ }}
function toggleCplxElig(){{
  cplxEligOnly = !cplxEligOnly;
  const btn = document.getElementById('cplxEligBtn');
  btn.style.background = cplxEligOnly ? '#2e7d32' : '#eee';
  btn.style.color = cplxEligOnly ? '#fff' : '#333';
  btn.textContent = cplxEligOnly ? '✅ 요건 적합만 표시 중' : '🔍 요건 필터';
  filterCplx();
}}

// ── 내 요건 폼 로직 ────────────────────────────
function loadPrefsForm() {{
  // 개인정보는 localStorage에서만 읽음 (HTML에 임베드 안 함)
  const prefs = JSON.parse(localStorage.getItem('user_prefs')||'null');
  if(!prefs || !Object.keys(prefs).length) return;
  if(prefs['월소득_만원']) document.getElementById('pref-income').value = String(prefs['월소득_만원']);
  if(prefs['최대보증금_만원']) document.getElementById('pref-deposit').value = String(prefs['최대보증금_만원']);
  if(prefs['혼인신고일']) document.getElementById('pref-marriage-date').value = prefs['혼인신고일'];
  document.getElementById('pref-nohome').checked = (prefs['무주택'] !== false);
  const regions = prefs['희망지역'] || [];
  document.getElementById('pref-region-seoul').checked = regions.includes('서울');
  document.getElementById('pref-region-gg').checked    = regions.includes('경기');
  document.getElementById('pref-region-ic').checked    = regions.includes('인천');
}}

function savePrefs() {{
  const regions = [];
  if(document.getElementById('pref-region-seoul').checked) regions.push('서울');
  if(document.getElementById('pref-region-gg').checked)    regions.push('경기');
  if(document.getElementById('pref-region-ic').checked)    regions.push('인천');
  const depVal = parseInt(document.getElementById('pref-deposit').value) || 0;
  const prefs = {{
    '월소득_만원':      parseInt(document.getElementById('pref-income').value) || 0,
    '최대보증금_만원':  depVal || null,
    '혼인신고일':      document.getElementById('pref-marriage-date').value || '',
    '무주택':          document.getElementById('pref-nohome').checked,
    '희망지역':        regions,
  }};
  localStorage.setItem('user_prefs', JSON.stringify(prefs));
  const msg = document.getElementById('prefs-save-msg');
  msg.style.display = 'block';
  setTimeout(()=>{{msg.style.display='none';}}, 2500);
  applyEligibilityBadge();
}}

// 초기 실행
applyFilter();
// localStorage에서 요건 로드 → 배지 적용
(function() {{
  applyEligibilityBadge();
}})();
</script>
</body>
</html>"""

    with open(DASH_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  🌐 대시보드 저장: {DASH_FILE}")

# ══════════════════════════════════════════════
# 📲 Slack 알림
# ══════════════════════════════════════════════
def load_slack_config() -> dict:
    """slack_config.json 로드. 단, 환경변수 SLACK_WEBHOOK_URL이 있으면 그 값을 우선 사용
    (CI에선 파일이 없으므로 env로 주입)."""
    config_path = os.path.join(BASE_DIR, "slack_config.json")
    cfg: dict = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    env_webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if env_webhook:
        cfg["webhook_url"] = env_webhook
    return cfg


def send_slack_webhook(webhook_url: str, text: str) -> bool:
    """Incoming Webhook으로 채널에 메시지 전송 (스코프 승인 불필요)"""
    try:
        r = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"text": text},
            timeout=10,
        )
        if r.status_code == 200 and r.text == "ok":
            return True
        else:
            log(f"  ⚠ 웹훅 전송 실패: HTTP {r.status_code} — {r.text[:100]}")
            return False
    except Exception as e:
        log(f"  ⚠ 웹훅 오류: {e}")
        return False


def send_slack_dm(token: str, user_id: str, text: str) -> bool:
    """Slack DM 전송 (chat.postMessage API — chat:write 스코프 필요)"""
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            json={"channel": user_id, "text": text},
            timeout=10,
        )
        resp = r.json()
        if resp.get("ok"):
            return True
        else:
            log(f"  ⚠ Slack 전송 실패 [{user_id}]: {resp.get('error','')}")
            return False
    except Exception as e:
        log(f"  ⚠ Slack 오류 [{user_id}]: {e}")
        return False


def upload_slack_file(token: str, user_id: str, file_path: str, title: str, comment: str) -> bool:
    """Slack 파일 업로드 (신규 API: getUploadURLExternal → PUT → completeUploadExternal)"""
    headers_json = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        # Step 1: DM 채널 ID 확보
        r_dm = requests.post(
            "https://slack.com/api/conversations.open",
            headers=headers_json,
            json={"users": user_id},
            timeout=10,
        )
        dm = r_dm.json()
        if not dm.get("ok"):
            log(f"  ⚠ DM 채널 열기 실패 [{user_id}]: {dm.get('error','')}")
            return False
        channel_id = dm["channel"]["id"]

        # Step 2: 업로드 URL 발급
        r1 = requests.get(
            "https://slack.com/api/files.getUploadURLExternal",
            headers={"Authorization": f"Bearer {token}"},
            params={"filename": file_name, "length": file_size},
            timeout=15,
        )
        resp1 = r1.json()
        if not resp1.get("ok"):
            log(f"  ⚠ 업로드 URL 발급 실패 [{user_id}]: {resp1.get('error','')}")
            return False
        upload_url = resp1["upload_url"]
        file_id    = resp1["file_id"]

        # Step 3: 파일 전송
        with open(file_path, "rb") as f:
            r2 = requests.post(upload_url, data=f, timeout=120)
        if r2.status_code != 200:
            log(f"  ⚠ 파일 전송 실패 [{user_id}]: HTTP {r2.status_code}")
            return False

        # Step 4: 업로드 완료 + 채널 공유
        r3 = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers=headers_json,
            json={
                "files": [{"id": file_id, "title": title}],
                "channel_id": channel_id,
                "initial_comment": comment,
            },
            timeout=30,
        )
        resp3 = r3.json()
        if resp3.get("ok"):
            return True
        else:
            log(f"  ⚠ 파일 완료 처리 실패 [{user_id}]: {resp3.get('error','')}")
            return False
    except Exception as e:
        log(f"  ⚠ 파일 업로드 오류 [{user_id}]: {e}")
        return False


# ══════════════════════════════════════════════
# 👤 사용자 요건 관리
# ══════════════════════════════════════════════

# 도시근로자 월평균 소득 기준 (2025년, 만원)
URBAN_INCOME_BASE = {1: 348, 2: 542, 3: 720, 4: 825, 5: 878, 6: 930}

# 주택유형별 소득 상한 비율(%)
INCOME_LIMIT_RATIO = {
    "통합공공임대": 100,
    "행복주택":     100,
    "장기전세":     100,
    "국민임대":      70,
    "매입임대":      70,
    "전세임대":      70,
    "영구임대":      50,
    # 청약홈 민간분양: 소득제한 없음 → 최고 구간에 배치 (만 원 단위로 상한 없음 = 99999)
    "민간분양":     999,
    "공공분양(국민)": 100,
    "공공지원민간임대": 100,
}

# 주택유형별 총자산 상한(만원)
ASSET_LIMIT = {
    "통합공공임대": 36100,
    "행복주택":     36100,
    "장기전세":     36100,
    "국민임대":     29200,
    "매입임대":     29200,
    "전세임대":     29200,
    "영구임대":     29200,
}

CAR_ASSET_LIMIT = 3683  # 자동차 자산 상한(만원)


def load_user_prefs() -> dict:
    """user_prefs.json 읽기. 없으면 {}"""
    prefs_path = os.path.join(BASE_DIR, "user_prefs.json")
    if not os.path.exists(prefs_path):
        return {}
    try:
        with open(prefs_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_income_limit_won(type_text: str, is_sinhon: bool, family_n: int = 2) -> int:
    """공고 유형 + 신혼 여부 → 소득 상한 (만원/월). 2인 가구 기본."""
    base = URBAN_INCOME_BASE.get(min(max(family_n, 1), 6), 542)
    limit_pct = 100
    for kw, pct in INCOME_LIMIT_RATIO.items():
        if kw in type_text:
            limit_pct = pct
            break
    if is_sinhon:
        limit_pct = min(limit_pct + 20, 150)
    return round(base * limit_pct / 100)


def notice_income_label(type_text: str, is_sinhon: bool, family_n: int = 2) -> str:
    """공고에 표시할 소득 기준 문자열 (실제 금액). 예: '월 650만원 이하 (연 7,800만원)'"""
    monthly = get_income_limit_won(type_text, is_sinhon, family_n)
    annual  = monthly * 12
    return f"월 {monthly:,}만원 이하 (연 {annual:,}만원)"


def check_notice_eligibility(item: dict, prefs: dict) -> dict:
    """
    공고가 사용자 요건에 부합하는지 체크.
    반환: {"eligible": bool, "ok": [str], "fail": [str]}
    ok/fail 문자열은 실제 금액(만원) 기준으로 표시 — 퍼센트 없음.
    prefs가 비어있으면 eligible=True 반환.
    """
    if not prefs:
        return {"eligible": True, "ok": [], "fail": []}

    ok_list   = []
    fail_list = []

    # ── 1. 무주택 ──────────────────────────────
    if not prefs.get("무주택", True):
        fail_list.append("유주택자 (대부분 공고 대상 외)")

    # ── 2. 희망지역 ────────────────────────────
    region = item.get("지역", "") or ""
    desired = prefs.get("희망지역", [])
    if desired:
        region_ok = any(r in region for r in desired) or "전국" in region
        if region_ok:
            ok_list.append(f"지역 OK ({region})")
        else:
            fail_list.append(f"희망지역 외 ({region})")

    # ── 3. 소득 기준 (실제 금액으로 표시) ──────────────────────
    income    = prefs.get("월소득_만원", 0)
    family_n  = min(max(prefs.get("가구원수", 2), 1), 6)
    type_text = item.get("유형", "") or ""
    is_sinhon = item.get("신혼생초", False)
    limit_won = get_income_limit_won(type_text, is_sinhon, family_n)

    if income:
        if income > limit_won:
            fail_list.append(f"월소득 {income:,}만원 > 상한 {limit_won:,}만원")
        else:
            ok_list.append(f"월소득 {income:,}만원 ≤ 상한 {limit_won:,}만원 ✓")

    # ── 4. 총자산/자동차자산: 입력한 경우에만 체크 ──────────────
    total_asset = prefs.get("총자산_만원")
    car_asset   = prefs.get("자동차자산_만원")

    if total_asset is not None:
        asset_limit = 36100
        for kw, lim in ASSET_LIMIT.items():
            if kw in type_text:
                asset_limit = lim
                break
        if total_asset > asset_limit:
            fail_list.append(f"총자산 {total_asset:,}만원 > 상한 {asset_limit:,}만원")
        else:
            ok_list.append(f"총자산 {total_asset:,}만원 ≤ {asset_limit:,}만원 ✓")

    if car_asset is not None and car_asset > CAR_ASSET_LIMIT:
        fail_list.append(f"차량가액 {car_asset:,}만원 > 상한 {CAR_ASSET_LIMIT:,}만원")

    # ── 5. 신혼 여부 ──────────────────────────────────────────
    if item.get("신혼생초", False):
        marriage_date = prefs.get("혼인신고일", "")
        if marriage_date:
            try:
                m_dt  = datetime.strptime(marriage_date, "%Y-%m-%d")
                years = (datetime.today() - m_dt).days / 365.25
                if years > 7:
                    fail_list.append(f"혼인 {years:.1f}년 경과 (7년 초과 — 신혼 자격 없음)")
                else:
                    ok_list.append(f"혼인 {years:.1f}년차 (7년 이내 ✓)")
            except ValueError:
                pass

    eligible = len(fail_list) == 0
    return {"eligible": eligible, "ok": ok_list, "fail": fail_list}


# 소득 구간 (월소득 상한 기준, 만원) — 200~700 5구간, 그 밖은 양 끝에 포함
INCOME_BRACKETS = [
    (0,   300, "200~300만원"),   # 300 미만 (200 미만 포함)
    (300, 400, "300~400만원"),
    (400, 500, "400~500만원"),
    (500, 600, "500~600만원"),
    (600, 10**9, "600~700만원"),  # 600 이상 (700 초과 포함)
]

def _slack_escape(s: str) -> str:
    """Slack mrkdwn 특수문자 이스케이프 (링크 텍스트용)"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# 시·도 축약 (메시지 지역 태그용)
_REGION_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}
def short_region(region: str) -> str:
    """'서울특별시 강남구' → '서울', '경기도 성남시' → '경기'. 시·도 단위로 축약."""
    r = (region or "").strip()
    if not r:
        return "지역미상"
    if "전국" in r:
        return "전국"
    first = r.split()[0]
    return _REGION_SHORT.get(first, first)

import re as _re_region
# 앞뒤가 한글이 아닐 때만 매칭 → '부상제대군인' 같은 단어 내부 오탐 방지
_DISTRICT_RE   = _re_region.compile(r'(?<![가-힣])[가-힣]{2,3}(?:시|군|구)(?![가-힣])')
_DISTRICT_STOP = {"도시"}   # '도시형생활주택' 등 오탐 방지

def region_with_district(item: dict) -> str:
    """시·도 + 시·군·구. 지역 필드에 시군구가 있으면(마이홈) 그대로,
    없으면(LH·SH) 제목에서 추출. 예: '인천 남동구', '서울 구로구', '서울'."""
    raw   = (item.get("지역", "") or "").strip()
    parts = raw.split()
    sido  = short_region(raw)
    # ① 지역 필드에 시군구가 이미 포함된 경우 (마이홈 signguNm)
    if len(parts) >= 2 and parts[1] and parts[1] != sido:
        return f"{sido} {parts[1]}"
    # ② 없으면 제목에서 시·군·구 추출 (LH·SH)
    title = item.get("공고명", "") or ""
    for m in _DISTRICT_RE.finditer(title):
        tok = m.group(0)
        if tok in _DISTRICT_STOP:
            continue
        if tok == sido or tok.rstrip("시군구") == sido:
            continue
        return f"{sido} {tok}"
    return sido

# 주택유형 태그 (사용자가 유형을 한눈에 구분) — 위 항목 우선 매칭
NOTICE_HOUSING_TAGS = [
    ("기숙사",   ["희망하우징", "공공기숙사", "기숙사"]),
    ("청년안심", ["청년안심", "역세권청년"]),
    ("사회주택", ["사회주택", "토지지원"]),
    ("두레주택", ["두레주택"]),
    ("든든주택", ["든든주택"]),
    ("공공한옥", ["공공한옥", "한옥"]),
    ("공공원룸", ["공공원룸"]),
    ("신혼희망", ["신혼희망"]),
    ("장기전세", ["장기전세"]),
    ("행복주택", ["행복주택"]),
    ("국민임대", ["국민임대"]),
    ("영구임대", ["영구임대"]),
    ("통합임대", ["통합공공임대", "통합임대"]),
    ("매입임대", ["매입임대", "매입형"]),
    ("전세임대", ["전세임대"]),
    ("공공분양", ["공공분양", "분양주택", "토지임대부", "신혼희망타운"]),
    ("민간분양", ["민간분양(APT)", "민간분양", "민영APT", "민영 APT"]),
    ("공공지원임대", ["공공지원민간임대", "공공지원임대"]),
    ("도시형",   ["도시형생활주택", "원룸"]),
    ("공공임대", ["공공임대", "50년", "10년", "5년"]),
]

def notice_type_tag(item: dict) -> str:
    """공고명+유형에서 주택유형 태그 추출. 예: '행복주택', '기숙사', '매입임대'."""
    text = f"{item.get('공고명','') or ''} {item.get('유형','') or ''}"
    for tag, kws in NOTICE_HOUSING_TAGS:
        if any(k in text for k in kws):
            return tag
    return "기타"

def income_bracket_index(limit_won: int) -> int:
    """소득 상한(만원) → 구간 인덱스 (0~4)"""
    for i, (lo, hi, _) in enumerate(INCOME_BRACKETS):
        if lo <= limit_won < hi:
            return i
    return len(INCOME_BRACKETS) - 1

def build_slack_message(unique: list[dict], category: str, header: str,
                        empty_msg: str = "✅ 오늘은 신규 모집공고가 없습니다.") -> str:
    """Slack 알림 메시지 — 특정 카테고리(장기임대 / 청약·공공분양)의 신규 🟢모집공고를
    '소득 상한 구간'별로 그룹. 개인정보(소득·지역 등)는 메시지에 일절 표시하지 않음.
    사용자는 본인 소득 구간을 보고 직접 공고를 클릭한다."""
    today_str = datetime.today().strftime("%Y.%m.%d (%a)")

    # 해당 카테고리의 신규 🟢모집공고만 (당첨결과·계약·행정공지 제외)
    new_recruit = [d for d in unique
                   if d.get("is_new") and d.get("공고유형분류") == "🟢 모집공고"
                   and d.get("카테고리") == category]

    lines = [f"{header} — {today_str}"]

    if not new_recruit:
        lines.append("")
        lines.append(empty_msg)
        return "\n".join(lines)

    lines.append(f"🆕 *신규 모집공고 {len(new_recruit)}건* — 월소득 상한 구간별")
    lines.append("💡 _본인 월소득이 속한 구간부터 위쪽 구간 공고를 신청할 수 있어요_")
    lines.append("")

    # 구간별 버킷 분류 (공고 소득 상한 기준)
    buckets: list[list[dict]] = [[] for _ in INCOME_BRACKETS]
    for d in new_recruit:
        limit = get_income_limit_won(d.get("유형", "") or "", d.get("신혼생초", False))
        buckets[income_bracket_index(limit)].append(d)

    SHOW_PER = 5
    for i, (_, _, label) in enumerate(INCOME_BRACKETS):
        items = buckets[i]
        if not items:
            lines.append(f"💰 *월소득 {label} 이하 대상* — 신규 0건")
            lines.append("")
            continue
        lines.append(f"💰 *월소득 {label} 이하 대상* — 신규 {len(items)}건")
        for d in items[:SHOW_PER]:
            nm   = _slack_escape(d.get("공고명", "")[:42])
            rg   = region_with_district(d)
            tag  = notice_type_tag(d)
            prc  = price_badge_slack(d)
            lyr  = layer_badges_slack(d.get("대상계층"), d.get("대상계층_확인", False))
            link = d.get("링크", "")
            if link:
                lines.append(f"   • `{rg}` `{tag}` {prc}<{link}|{nm}>{lyr}")
            else:
                lines.append(f"   • `{rg}` `{tag}` {prc}{nm}{lyr}")
        if len(items) > SHOW_PER:
            lines.append(f"   …외 {len(items) - SHOW_PER}건은 대시보드에서")
        lines.append("")

    return "\n".join(lines)


# 분양·청약 메시지 지역 표시 순서
SALE_REGION_ORDER = ["서울", "경기", "인천"]

def build_sale_message(unique: list[dict], category: str, header: str,
                       empty_msg: str = "✅ 오늘은 신규 분양·청약 공고가 없습니다.") -> str:
    """분양·청약(청약·공공분양) 전용 Slack 메시지 — '지역별'로 그룹.
    분양은 소득 상한 의미가 약해(민간분양 등) 소득구간 대신 지역으로 묶고
    각 공고에 유형 태그를 표시한다."""
    today_str = datetime.today().strftime("%Y.%m.%d (%a)")

    new_recruit = [d for d in unique
                   if d.get("is_new") and d.get("공고유형분류") == "🟢 모집공고"
                   and d.get("카테고리") == category]

    lines = [f"{header} — {today_str}"]

    if not new_recruit:
        lines.append("")
        lines.append(empty_msg)
        return "\n".join(lines)

    lines.append(f"🆕 *신규 분양·청약 {len(new_recruit)}건* — 지역별")
    lines.append("")

    # 지역(시·도) 버킷 분류
    buckets: dict[str, list[dict]] = {}
    for d in new_recruit:
        sido = short_region(d.get("지역", "") or "")
        key  = sido if sido in SALE_REGION_ORDER else "기타"
        buckets.setdefault(key, []).append(d)

    order = SALE_REGION_ORDER + [k for k in buckets if k not in SALE_REGION_ORDER]
    SHOW_PER = 6
    for key in order:
        items = buckets.get(key)
        if not items:
            continue
        lines.append(f"📍 *{key}* — {len(items)}건")
        for d in items[:SHOW_PER]:
            nm   = _slack_escape(d.get("공고명", "")[:42])
            rg   = region_with_district(d)
            tag  = notice_type_tag(d)
            prc  = price_badge_slack(d)
            lyr  = layer_badges_slack(d.get("대상계층"), d.get("대상계층_확인", False))
            link = d.get("링크", "")
            if link:
                lines.append(f"   • `{rg}` `{tag}` {prc}<{link}|{nm}>{lyr}")
            else:
                lines.append(f"   • `{rg}` `{tag}` {prc}{nm}{lyr}")
        if len(items) > SHOW_PER:
            lines.append(f"   …외 {len(items) - SHOW_PER}건은 대시보드에서")
        lines.append("")

    return "\n".join(lines)


def send_slack_notifications(unique: list[dict], new_count: int):
    """slack_config.json 기반으로 Slack 알림 발송.

    우선순위:
      1. webhook_url 설정 시 → Incoming Webhook으로 채널(#ayaan_auto_bot) 발송 (스코프 불필요, 즉시 사용 가능)
      2. bot_token + 유효 recipients 설정 시 → DM 발송 (chat:write·im:write·files:write 스코프 필요)
    """
    cfg = load_slack_config()
    webhook_url  = cfg.get("webhook_url", "")
    token        = cfg.get("bot_token", "")
    recipients   = cfg.get("recipients", {})
    webhook_chan = cfg.get("webhook_channel", "#ayaan_auto_bot")

    # 유효한 User ID만 필터링 (U로 시작)
    valid_recipients = {
        name: uid for name, uid in recipients.items()
        if uid and uid.startswith("U") and len(uid) > 5
    }

    # 발송 수단이 없으면 종료
    if not webhook_url and not (token and valid_recipients):
        log("  ⚠ Slack 발송 수단 없음 — webhook_url 또는 (bot_token + recipients) 설정 필요")
        return

    # 카테고리별 신규 🟢모집공고 (임대 / 분양·청약 분리 발송)
    rental_new = [d for d in unique if d.get("is_new") and d.get("공고유형분류") == "🟢 모집공고"
                  and d.get("카테고리") == "장기임대"]
    sale_new   = [d for d in unique if d.get("is_new") and d.get("공고유형분류") == "🟢 모집공고"
                  and d.get("카테고리") == "청약·공공분양"]

    today_str = datetime.today().strftime("%Y.%m.%d")
    # 발송할 메시지 정의: (카테고리, 헤더, 신규 리스트, 빌더, 0건 안내문구)
    #  - 임대: 소득구간별 그룹(build_slack_message)
    #  - 분양·청약: 지역별 그룹(build_sale_message)
    #  - 신규 0건이어도 항상 발송 (각 카테고리 구독자가 매번 확인할 수 있도록)
    msg_specs = [
        ("장기임대",      "🏠 *부동산 소식 — 임대 알리미*",      rental_new, build_slack_message, "✅ 오늘은 신규 임대 모집공고가 없습니다."),
        ("청약·공공분양", "🏗️ *부동산 소식 — 분양·청약 알리미*", sale_new,   build_sale_message,   "✅ 오늘은 신규 분양·청약 공고가 없습니다."),
    ]

    # ── DRY RUN: 환경변수 ALIMI_DRY_RUN 설정 시 실제 발송 없이 미리보기만 로그 ──
    if os.environ.get("ALIMI_DRY_RUN", "").strip().lower() in ("1", "true", "yes"):
        log("\n🧪 [DRY RUN] 실제 발송 생략 — 아래는 발송 예정 메시지 미리보기")
        for category, header, items, builder, empty_msg in msg_specs:
            log("\n" + "="*50)
            log(builder(unique, category, header, empty_msg))
        log("\n🧪 [DRY RUN] 끝 — 슬랙 발송 안 함")
        return

    # ── 모드 1: Incoming Webhook (현재 기본 모드) ──────────────────────────────
    if webhook_url:
        log(f"\n📲 Slack 웹훅 알림 발송 중... → {webhook_chan} (임대 + 분양·청약)")
        all_ok = True
        for category, header, items, builder, empty_msg in msg_specs:
            body     = builder(unique, category, header, empty_msg)
            full_msg = body + f"\n\n📊 *대시보드 보기* → {DASH_URL}"
            ok = send_slack_webhook(webhook_url, full_msg)
            status = "✅" if ok else "❌"
            log(f"  {status} 웹훅 발송 ({header}, {len(items)}건) → {webhook_chan}")
            all_ok = all_ok and ok
            time.sleep(1)   # 두 메시지 사이 약간의 간격
        if all_ok:
            return  # 웹훅 성공 시 DM 발송 스킵
        else:
            log("  ⚠ 웹훅 일부 실패 — DM 발송 시도")

    # ── 모드 2: DM (chat:write·im:write·files:write 스코프 필요) ────────────
    if not token:
        log("  ⚠ Slack 토큰 없음 → 알림 생략")
        return
    if not valid_recipients:
        log("  ⚠ Slack 수신자 User ID 미설정 → slack_config.json에서 설정 필요")
        log("     ☞ 내 User ID: Slack → 프로필 클릭 → 더보기(...) → '멤버 ID 복사'")
        return

    log("\n📲 Slack DM 발송 중... (임대 + 분양·청약)")
    for name, uid in valid_recipients.items():
        # 1) 카테고리별 텍스트 메시지 (임대 → 분양·청약, 0건이어도 항상 발송)
        msg_ok = True
        for category, header, items, builder, empty_msg in msg_specs:
            ok_msg = send_slack_dm(token, uid, builder(unique, category, header, empty_msg))
            msg_ok = msg_ok and ok_msg
            time.sleep(1)
        # 2) HTML 대시보드 파일 첨부 (1회)
        ok_file = upload_slack_file(
            token, uid,
            file_path=DASH_FILE,
            title=f"부동산 대시보드 {today_str}",
            comment="📊 오늘의 전체 공고 대시보드입니다. 브라우저에서 열어 확인하세요.",
        )
        status = "✅" if (msg_ok and ok_file) else ("⚠" if (msg_ok or ok_file) else "❌")
        log(f"  {status} {name} ({uid}) — 메시지={'✅' if msg_ok else '❌'} 파일={'✅' if ok_file else '❌'}")


# ══════════════════════════════════════════════
# 🌐 GitHub Pages 배포
# ══════════════════════════════════════════════
def deploy_to_github_pages():
    """대시보드를 .deploy/index.html로 복사 후 GitHub Pages에 force-push.
    단일 커밋 유지(--amend)로 14MB 파일이 git 히스토리에 누적되지 않게 함."""
    import shutil, subprocess
    if os.environ.get("GITHUB_ACTIONS"):
        log("  ℹ GitHub Actions 환경 — 스크립트 자가배포 생략 (워크플로가 Pages 배포)")
        return
    if not os.path.isdir(os.path.join(DEPLOY_DIR, ".git")):
        log("  ⚠ .deploy git 미설정 → GitHub Pages 배포 생략")
        return
    try:
        shutil.copy(DASH_FILE, os.path.join(DEPLOY_DIR, "index.html"))
        def run(*args):
            return subprocess.run(["git", *args], cwd=DEPLOY_DIR,
                                  capture_output=True, text=True, timeout=180)
        run("add", "index.html")
        run("commit", "--amend", "-m", "Update dashboard", "--date=now")
        r = run("push", "-f", "origin", "main")
        if r.returncode == 0:
            log(f"  🌐 GitHub Pages 배포 완료 → {DASH_URL}")
        else:
            log(f"  ⚠ Pages 배포 실패: {(r.stderr or '').strip()[:150]}")
    except Exception as e:
        log(f"  ⚠ Pages 배포 오류: {e}")


# ══════════════════════════════════════════════
# 🚀 메인
# ══════════════════════════════════════════════
def main():
    log("="*60)
    log(f"🏠 부동산 소식 알리미 v2 시작 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log("="*60)

    # 수집
    all_data = []
    all_data += scrape_lh_rental()
    all_data += scrape_lh_sale()
    all_data += scrape_myhome()        # 마이홈포털 임대 (OpenAPI)
    all_data += scrape_myhome_sale()   # 마이홈포털 분양 (OpenAPI)
    all_data += scrape_sh()
    all_data += scrape_gh()
    all_data += scrape_seoul_youth()     # 서울시 청년안심주택(민간임대) ← NEW
    all_data += scrape_cheongyanghome()  # 청약홈 APT 분양 (한국부동산원 OpenAPI) ← NEW
    all_data += scrape_lh_api()          # LH 분양임대공고문 API (2026-05-21 승인, 키 전파 후 활성화)

    # 대기현황 + 단지정보 (별도 데이터셋)
    waitlist_data = scrape_waitlist()
    complex_data  = scrape_complex()

    if not all_data:
        log("⚠ 수집 데이터 없음 — 종료")
        return

    # 중복 제거 — 시·도 + 정규화 제목 기준 (소스 통합: LH/SH/GH + 마이홈 동일 공고 병합)
    # 우선순위: 구 정보 有 > 마감일 有 > 최신 정정본 (마이홈이 구·마감 보유 → 우선 채택)
    def _merge_rank(d):
        has_dist = 1 if len((d.get('지역', '') or '').split()) >= 2 else 0
        has_ddl  = 1 if (d.get('마감일', '') or '').strip() else 0
        corr, pdate = _correction_rank(d)
        return (has_dist, has_ddl, corr, pdate)

    best: dict = {}
    order: list = []
    for d in all_data:
        key = f"{short_region(d.get('지역',''))}|{normalize_notice_title(d['공고명'])}"
        if key not in best:
            best[key] = d
            order.append(key)
        else:
            # 대상계층(공급대상)은 어느 소스 버전이든 합집합으로 보존
            #  (청약홈 Mdl 기반 정확 계층이 마이홈 버전 채택 시에도 살아남도록)
            merged_layers = merge_layers(best[key].get("대상계층"), d.get("대상계층"))
            # 확인 여부도 OR — 한 버전이라도 청약홈 Mdl로 확인됐으면 확인됨 처리
            merged_verified = bool(best[key].get("대상계층_확인") or d.get("대상계층_확인"))
            # 가격: 직접값 우선, 둘 다 직접 or 둘 다 추정이면 비어있지 않은 값 보존
            b_p, b_dir = (best[key].get("가격") or "").strip(), bool(best[key].get("가격_직접"))
            d_p, d_dir = (d.get("가격") or "").strip(), bool(d.get("가격_직접"))
            if b_dir and b_p:
                merged_price, merged_direct = b_p, True
            elif d_dir and d_p:
                merged_price, merged_direct = d_p, True
            else:
                merged_price = b_p or d_p
                merged_direct = False
            if _merge_rank(d) > _merge_rank(best[key]):
                best[key] = d   # 더 풍부한(구·마감 有) 버전으로 교체, 위치는 최초 등장 순 유지
            best[key]["대상계층"] = merged_layers
            best[key]["대상계층_확인"] = merged_verified
            best[key]["가격"] = merged_price
            best[key]["가격_직접"] = merged_direct
    unique = [best[k] for k in order]

    log(f"\n📋 수집: {len(all_data)}건 → 중복제거 후 {len(unique)}건 (소스 통합 포함)")

    # ── LH·SH·마이홈 임대 공고에 가격 보강 (마이홈 단지정보 캐시 활용 — 추정) ────
    if complex_data:
        lh_price_map, sgg_alias = build_lh_price_map(complex_data)
        _PRICE_SOURCES = {"LH청약플러스", "SH공사", "GH(경기주택도시공사)", "마이홈포털", "LH공사API"}
        matched = 0
        for d in unique:
            if (d.get("가격") or "").strip():
                continue  # 이미 가격 있으면 skip (직접값 — 청약홈 분양 / 청년안심 / 마이홈 임대 직접 등)
            if d.get("출처") not in _PRICE_SOURCES:
                continue
            if d.get("카테고리") != "장기임대":
                continue  # 임대 공고에만 (분양은 별도)
            price = match_lh_price(d, lh_price_map, sgg_alias)
            if price:
                d["가격"] = price
                d["가격_직접"] = False   # 캐시 P25~P75 추정
                matched += 1
        log(f"  💰 LH/SH 임대 가격 매칭(추정): {matched}건 (단지정보 {len(complex_data):,}건 기반)")

    # 📊 직접 vs 추정 가격 카운트 로그
    direct_cnt = sum(1 for d in unique if (d.get("가격") or "").strip() and d.get("가격_직접"))
    est_cnt    = sum(1 for d in unique if (d.get("가격") or "").strip() and not d.get("가격_직접"))
    empty_cnt  = sum(1 for d in unique if not (d.get("가격") or "").strip())
    log(f"  📊 가격 분포: 직접={direct_cnt}건 | 추정={est_cnt}건 | 없음={empty_cnt}건 (총 {len(unique)}건)")

    # 신규 감지
    unique, new_count = detect_new(unique)
    log(f"🆕 신규 공고: {new_count}건")

    # 정렬: 신규 → 신혼생초 → 게시일 (우선순위 개념 제거)
    unique.sort(key=lambda d: (
        0 if d.get("is_new") else 1,
        0 if d.get("신혼생초") else 1,
        d.get("게시일","") or "0",
    ), reverse=False)

    # TOP 신규 출력
    if new_count:
        log("\n" + "─"*55)
        log(f"🆕 신규 공고 TOP {min(new_count,10)}")
        log("─"*55)
        for i, d in enumerate([x for x in unique if x.get("is_new")][:10], 1):
            log(f"  {i:2}. [{d['유형']}] {d['공고명'][:42]} | {d['지역']} | ~{d['마감일']}")

    # 저장
    log("\n💾 저장 중...")
    save_dashboard(unique, new_count, waitlist_data, complex_data)

    # GitHub Pages 배포 (폰에서 링크로 보기)
    deploy_to_github_pages()

    # Slack 알림 발송
    send_slack_notifications(unique, new_count)

    log("\n" + "="*60)
    log("✅ 완료!")
    log(f"  🆕 신규: {new_count}건 | 전체: {len(unique)}건")
    log(f"  🌐 {os.path.basename(DASH_FILE)}")
    log("="*60)

if __name__ == "__main__":
    main()
