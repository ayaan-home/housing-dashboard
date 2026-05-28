# 💰 가격 추출 가이드 (Price Extraction Guide)

> **버전**: 1.0 (2026-05-28 신설)
> **대상 코드**: `부동산_알리미_v2.py`
> **상위 명세**: `./api-reference.md` (부록 C — 매핑 표)
> **공식 원본**: `./공식문서/` 폴더 (xlsx 3종 + docx 2종)
>
> 본 문서는 알리미가 슬랙 메시지·대시보드에 표시하는 **모든 가격 정보의 추출 경로**를 단일 진실 공급원(single source of truth)으로 정리한 가이드다. 가격이 어디서 왔고, 어떤 단위이고, 슬랙 어떤 배지로 나타나는지를 한 곳에서 추적할 수 있도록 설계됨.

---

## 1. 왜 가격 추출이 어려운가 (Why this is hard)

부동산 공공데이터의 가격 정보는 **출처마다 형식·단위·완전성**이 제각각이다:

| 출처 | 가격 데이터 가용성 |
|---|---|
| 마이홈 HWSPR02 모집공고 (임대) | ❌ 공고 단위에는 가격 없음 |
| 마이홈 HWSPR02 모집공고 (분양) | ✅ 계약금·중도금·잔금 분리 제공 |
| 마이홈 HWSPR04 단지정보 | ✅ 보증금·월임대료·전환보증금 모두 |
| LH 분양임대공고문 OpenAPI | ❌ 본 API는 목록만, 가격은 별도 API |
| LH 청약플러스 HTML | ❌ PDF/JS 동적 렌더 — 파싱 불가 |
| SH/GH 공사 HTML | ❌ 동일 (PDF/JS) |
| 청약홈 APT 주택형별 | ✅ 공급금액(분양최고) 만원 단위 |
| 서울 청년안심주택 (soco) | ✅ 단지비교 API에서 보증금·월세 추출 |

**핵심 통찰**: 임대(특히 LH/SH/GH)는 직접 가격을 가져올 길이 없다. 알리미는 **마이홈 HWSPR04 단지정보 캐시(약 7만건, 96.9% 가격 채워짐)** 를 활용해 (시도, 시군구, 공급유형) 그룹의 **P25~P75 분위수**로 추정한다.

---

## 2. 전체 가격 흐름 (한눈에)

```
[수집 단계]
 ├─ scrape_complex() ──── 마이홈 HWSPR04 → 단지 7만건 캐시 (Supabase kv_cache, 7일)
 ├─ scrape_myhome() ───── 마이홈 HWSPR02 임대 → 공고 (가격 없음)
 ├─ scrape_myhome_sale()  마이홈 HWSPR02 분양 → 공고 + 직접 분양가
 ├─ scrape_cheongyanghome() → 청약홈 APT Mdl → 분양가 LTTOT_TOP_AMOUNT
 ├─ scrape_lh_api() ───── LH lhLeaseNoticeInfo1 → 공고 목록 (가격 없음)
 ├─ scrape_lh_rental() ── LH HTML → 공고 (가격 없음)
 ├─ scrape_sh() / scrape_gh() → SH/GH HTML → 공고 (가격 없음)
 └─ scrape_seoul_youth() → soco AJAX → 청년안심 공고 + 가격 매칭

[가공 단계]
 build_lh_price_map(complex_cache) → {(시도, 시군구, 공급유형): [가격 행들]}
        │
        ▼
 match_lh_price(공고, price_map) → P25~P75 범위 문자열
        │
        ▼
 price_badge_slack(item) ─ 직접값=💰, 추정=📊로 배지 생성
        │
        ▼
 build_slack_message() / build_sale_message() → 슬랙 발송
```

---

## 3. 출처별 추출 방법 상세

### 3.1 마이홈 HWSPR02 분양 가격 (직접 추출)

**출처**: `https://apis.data.go.kr/1613000/HWSPR02/ltRsdtRcritNtcList`
**필드**: `enty`(계약금) + `prtpay`(중도금) + `surlus`(잔금) — 단위 **원**
**코드**: `scrape_myhome_sale()` L670-680

```python
enty   = int(it.get("enty")   or 0)   # 계약금
prtpay = int(it.get("prtpay") or 0)   # 중도금
surlus = int(it.get("surlus") or 0)   # 잔금
total  = enty + prtpay + surlus       # 총 분양가 (원)
```

**파인만 방식 설명**: 분양은 보통 *계약 → 중도금 분납 → 잔금* 세 단계로 돈을 낸다. 마이홈은 이 세 단계 금액을 따로따로 응답한다. 우리는 셋을 더해 "**총 분양가**"를 만든다. 합계가 0이면 가격이 아직 미설정인 공고로 판단해 표시하지 않는다.

**슬랙 배지**: `💰분양가XX억` (직접값이므로 💰 이모지)

---

### 3.2 마이홈 HWSPR04 단지정보 (캐시)

**출처**: `https://apis.data.go.kr/1613000/HWSPR04/getRsdtCmpInfoList`
**필드** (단위 모두 **원**):

| 필드 | 한글 | 의미 |
|---|---|---|
| `bassRentGtn` | 기본 임대보증금 | 입주 시 내는 보증금 |
| `bassMtRntchrg` | 기본 월임대료 | 매월 내는 임대료 |
| `bassCnvrsGtnLmt` | 전환보증금 한도 | 월세를 보증금으로 환산 가능한 최대 금액 |

**코드**: `scrape_complex()` L1551-1553

```python
"보증금":       int(it.get("bassRentGtn", 0) or 0),
"월임대료":     int(it.get("bassMtRntchrg", 0) or 0),
"전환보증금한도": int(it.get("bassCnvrsGtnLmt", 0) or 0),
```

**저장**: Supabase `kv_cache` 테이블에 `complex_cache`라는 이름으로 jsonb 저장, 7일 캐시. Supabase 미연결 시 파일(`단지정보_캐시.json`)로 폴백.

**중요 캐비엇**:

- `bassMtRntchrg`는 `Rnt` + `chrg` 표기 (Rent의 줄임이 Rnt). `bassMtRentChrg`(중간에 e가 들어간 표기)는 **틀린 표기** — 마이홈 응답에 그런 필드 없음.
- HWSPR04는 단지(=건물) 단위. 한 단지에 여러 평형(`styleNm`)이 있으므로 같은 단지 여러 행이 응답된다.

---

### 3.3 LH/SH/GH 임대 가격 — 마이홈 캐시 기반 P25~P75 추정 (핵심 알고리즘)

직접 가격 데이터가 없는 임대 공고에는 **마이홈 캐시의 통계적 추정값**을 매칭한다.

#### Step 1. 캐시를 그룹화 — `build_lh_price_map()` L953

```python
price_map = {
    ("서울", "강남구", "행복주택"): {
        "deposits": [120_000_000, 130_000_000, ...],  # 보증금 리스트
        "rents":    [510_000, 530_000, ...],           # 월임대료 리스트
        "convs":    [140_000_000, ...],                # 전환보증금 한도
    },
    ...
}
```

#### Step 2. 시군구 별칭 빌드 — `build_lh_price_map()` 내부

공고문 텍스트의 "강남"·"부천" 등 약식 표기를 마이홈의 정식 "강남구"·"부천시"로 매칭하기 위한 alias dict(약 165개) 자동 빌드.

#### Step 3. 공고별 매칭 — `match_lh_price()` L1014

```python
# 1순위: (시도, 시군구, 공급유형) 정확 매칭
# 2순위 fallback: (시도, 공급유형) 매칭
# 3순위 fallback: (시군구, 전체) 매칭
```

#### Step 4. 분위수 계산 — `_percentile()` L1004

numpy 없이 순수 파이썬으로 P25·P50·P75 계산. 분위수 사용 이유: 평균은 극단값에 휘둘리지만 **P25~P75 사분위 범위**는 "가운데 절반"을 가리키므로 더 현실적.

```python
보증금_P25 = _percentile(sorted(deposits), 0.25)
보증금_P75 = _percentile(sorted(deposits), 0.75)
# → "보증금1.4억~2.1억"
```

**슬랙 배지**: `📊보증금1.4억~2.1억 / 월51만~77만 (추정)` — 추정값이므로 `📊` 이모지로 차별화.

#### `_LH_SUPPLY_TYPE_RULES` (L936) — 유형명 정규화

LH 공고문은 "공공임대(국민)"·"통합공공임대" 등 다양한 표기를 사용. 마이홈의 `suplyTyNm`(예: "국민임대", "통합공공임대")로 정규화하는 룰셋.

---

### 3.4 청약홈 APT 분양가 — `LTTOT_TOP_AMOUNT`

**출처**: `https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancMdl`
**필드**: `LTTOT_TOP_AMOUNT` 공급금액(분양최고) — 단위 **만원**
**코드**: `fetch_cheong_mdl_layers()` L1206-1216

```python
rows  = r.json().get("data", [])
price = format_price_eok([row.get("LTTOT_TOP_AMOUNT") for row in rows])
```

**중요**: 한 공고에 여러 주택형(예: 59㎡, 84㎡, 114㎡)이 있으면 각자 다른 `LTTOT_TOP_AMOUNT`. `format_price_eok`이 min~max 범위로 변환 → `💰3.9~6.7억`.

**단위 변환**:

- 만원 → 억 = 만원 / 10000
- 예: 80,720만원 = 8.072억 → "8.1억"으로 반올림

---

### 3.5 서울 청년안심주택 — soco 단지비교 매칭

**출처**: `https://soco.seoul.go.kr/youth/pgm/home/yohome/maplist.json` (POST JSON)
**코드**: `fetch_soco_price_map()`
**매칭 방법**: 단지명 substring 매칭. soco의 단지 좌표 API에는 보증금·월세 범위가 들어 있어, 청년안심 공고의 단지명과 substring으로 매칭.

**커버리지**: 약 78% (46건 중 36건)
**슬랙 배지**: `💰월16만~77만` (보증금이 0인 경우가 많아 월세 위주)

---

## 4. 슬랙 배지 표시 규칙

`price_badge_slack()` L223가 결정:

| 케이스 | 배지 형식 | 이모지 |
|---|---|---|
| 직접 분양가 (마이홈/청약홈 분양) | `💰분양가X.X억` | 💰 |
| 직접 임대료 (청년안심·일부) | `💰월X만~Y만` | 💰 |
| 캐시 추정 임대 (LH/SH/GH) | `📊보증금X.X억~Y.Y억 / 월X만~Y만 (추정)` | 📊 |
| 전환보증금 있을 때 부가 | ` 🔄전환한도X억` | 🔄 |
| 가격 데이터 없음 | `💰?` | – |

**`item["가격_직접"]` 플래그**: 직접 추출 가격은 `True`, 추정값은 `False` 또는 미설정. 이게 배지 이모지를 결정한다.

---

## 5. Phase 2 검증 결과 (2026-05-28)

공식 명세서 5종을 코드와 1:1 매칭 검증한 결과:

### 5.1 ✅ 일치한 항목

| 영역 | 결과 |
|---|---|
| 마이홈 HWSPR02 분양가 (`enty`+`prtpay`+`surlus`) | 명세 부합 |
| 마이홈 HWSPR04 단지가격 (`bassRentGtn`/`bassMtRntchrg`/`bassCnvrsGtnLmt`) | 명세 부합 |
| 청약홈 APT 6개 특공 계층 (NWBB/YGMN/NWWDS/LFE_FRST/MNYCH/OLD_PARNTS_SUPORT) | 명세 부합 |
| 청약홈 APT 분양가 (`LTTOT_TOP_AMOUNT`) | 명세 부합 |

### 5.2 🔧 적용된 패치

#### 패치 1 — `TYPE_MAP` TODO 주석 추가 (L1344)

공식 명세 `UPP_AIS_TP_CD`는 6종 코드만 정의(01/05/06/13/22/39). 코드는 07~11을 추가로 매핑 중이라 명세와 불일치. LH API가 현재 403 상태라 즉시 영향은 없지만, 활성화 시 회귀 가능성 → **TODO 주석으로 명시**하여 향후 검증 트리거를 남김.

#### 패치 2 — `layers_from_mdl()` SPSPLY 일관성 검증 추가 (L152)

`SPSPLY_HSHLDCO`(특공 합계)는 명세상 "6계층 + 기관추천 + 기타 + 이전기관"의 합. 우리는 6계층만 추적하므로 **6계층 합 ≤ SPSPLY** 가 정상. 위반 시 stderr 경고:

```
⚠ Mdl 합계 검증: 6계층합(N) > SPSPLY(M) — 명세 확인 필요
```

단위 테스트 5건 모두 통과.

### 5.3 ⏸️ 미해결 (의도적 보류)

#### Issue B — 청약홈 공공지원 민간임대 Mdl

명세상 별도 엔드포인트(`spsply_ygmn_hshldco`/`spsply_new_mrrg_hshldco`/`spsply_aged_hshldco`)가 존재. 그러나 현재 알리미는 청약홈에서 **APT만 호출**하므로 영향 없음. 공공지원민간임대(청년안심)는 soco.seoul.go.kr 스크래핑 경로로 별도 수집 중. **코드 수정 불필요**, 본 가이드에 사실로 명시함.

#### Issue D — LH 공급정보 후속 API 미구현

명세 정식 흐름: `lhLeaseNoticeInfo1` → `SPL_INF_TP_CD`+`PAN_ID` 키로 별도 "공급정보 조회" API 호출 → 임대조건 추출. 현재는 마이홈 캐시 P25~P75 추정으로 우회. 기능적으로 작동하나, 정식 흐름 구현 시 정확도 향상 가능. **향후 개선 과제**.

---

## 6. 단위·표기 일관성 체크리스트

가격 처리 시 자주 빠지는 함정:

- [ ] **단위**: 마이홈=원, 청약홈=만원, soco=원/만원 혼재 → 모두 **만원** 또는 **억** 으로 변환 전 확인
- [ ] **필드명 대소문자**: 명세는 소문자(`lttot_top_amount`), odcloud 응답은 **대문자**로 변환됨(`LTTOT_TOP_AMOUNT`) — 마이홈은 **카멜 케이스** 유지(`bassRentGtn`)
- [ ] **0 처리**: 가격 0은 "미설정"이지 "무료"가 아님 — 표시 생략
- [ ] **None vs 0**: `it.get("enty") or 0`로 둘 다 안전 처리
- [ ] **`bassMtRntchrg`**: `Rnt+chrg` 표기 (Rent의 줄임이 Rnt). `bassMtRentChrg`(중간 e)는 잘못된 표기
- [ ] **`_HSHLDCO` 접미사**: 청약홈 Mdl 특공 필드는 모두 `_HSHLDCO`로 끝남 (HouseHold Count의 줄임)
- [ ] **추정 vs 직접**: 배지 이모지로 사용자가 즉시 구분 가능해야 함 (💰 vs 📊)

---

## 7. 다음 세션에 남기는 메모

- LH OpenAPI(15058530) 키 전파 완료되면 → `scrape_lh_api()` 실제 응답으로 TYPE_MAP 재검증
- 정확도 욕심 내면 → LH "공급정보 조회" 후속 API 추가 구현
- 청년안심 매칭 커버리지 78% → 단지명 정규화 강화 시 90%+ 가능

**원본 명세서**: `./공식문서/` (5종)
**상위 명세**: `./api-reference.md`
**HANDOFF**: `../../HANDOFF.md`
