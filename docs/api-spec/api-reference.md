# 부동산 알리미 — 공공데이터 API 명세 아카이브

> **생성일**: 2026-05-27
> **출처**: 공공데이터포털 (data.go.kr) + odcloud.kr Swagger
> **대상 코드**: `부동산_알리미_v2.py`
> **인증**: 모든 API의 `serviceKey`는 환경변수 `MYHOME_API_KEY`로 주입 (코드·문서에 절대 노출 금지, 본 문서에서는 `YOUR_SERVICE_KEY_HERE`로 마스킹)

---

## 📑 목차

1. [국토교통부_마이홈포털 공공주택 모집공고 조회 서비스 (15108420)](#1-국토교통부_마이홈포털-공공주택-모집공고-조회-서비스-15108420)
2. [국토교통부_마이홈포털 예비입주자 대기현황 조회서비스 (15108378)](#2-국토교통부_마이홈포털-예비입주자-대기현황-조회서비스-15108378)
3. [국토교통부_마이홈포털 공공임대주택 단지정보 조회 서비스 (15110581)](#3-국토교통부_마이홈포털-공공임대주택-단지정보-조회-서비스-15110581)
4. [한국토지주택공사_분양임대공고문 조회 서비스 (15058530)](#4-한국토지주택공사_분양임대공고문-조회-서비스-15058530)
5. [한국부동산원_청약홈 분양정보 조회 서비스 (15098547)](#5-한국부동산원_청약홈-분양정보-조회-서비스-15098547)
6. [📚 부록 A — 코드값 사전 (공식 활용가이드 추출)](#-부록-a--코드값-사전-공식-활용가이드-추출)
7. [부록 B — 비-OpenAPI 스크래핑 출처](#부록-b--비-openapi-스크래핑-출처)

---

## 1. 국토교통부_마이홈포털 공공주택 모집공고 조회 서비스 (15108420)

**Base URL**: `https://apis.data.go.kr/1613000/HWSPR02`
**제공기관**: 국토교통부 (마이홈포털)
**관리부서**: 청년주거정책과 (☎ 044-201-3630)
**등록일**: 2022-11-25 | **수정일**: 2026-04-08 | **업데이트 주기**: 실시간
**API 유형**: REST | **데이터포맷**: JSON
**공식 명세**: <https://www.data.go.kr/data/15108420/openapi.do>
**참고문서**: `붙임1. 요청 파라미터 코드(공공주택 모집공고)_260331.xlsx` ✅ **분석 완료** → [부록 A-1~A-4](#a-1-광역시도-코드-마이홈-api-공통--brtccode) 참조
**코드 사용 위치**: `부동산_알리미_v2.py` L53 (상수 정의), L552 (`_fetch_myhome_api`), L604 (`scrape_myhome`), L633 (`scrape_myhome_sale`)

### 개요
국토교통부에서 제공하는 마이홈포털 공공임대주택 모집공고 조회 서비스. 광역시도, 시군구, 공급유형, 주택유형, 전세형 여부, 월임대료 범위, 모집공고월을 기준으로 공공임대주택/공공분양주택 모집공고 정보를 조회한다. 본 알리미가 가장 핵심적으로 의존하는 API.

### 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/rsdtRcritNtcList` | 공공임대주택 모집공고 조회 |
| GET | `/ltRsdtRcritNtcList` | 공공분양주택 모집공고 조회 |

### 요청 파라미터 — `rsdtRcritNtcList` (공공임대)

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|------|------|
| `serviceKey` | query | string | ✅ | 공공데이터포털에서 받은 인증키 |
| `brtcCode` | query | string | – | 광역시도 코드 (예: `11`=서울, `41`=경기) |
| `signguCode` | query | string | – | 시군구 코드 |
| `numOfRows` | query | string | – | 페이지당 데이터 개수 (기본 10) |
| `pageNo` | query | string | – | 페이지 번호 (기본 1) |
| `suplyTy` | query | string | – | 공급유형 |
| `houseTy` | query | string | – | 주택유형 |
| `lfstsTyAt` | query | string | – | 전세형 모집 여부 |
| `bassMtRntchrgSe` | query | string | – | 월임대료 구분 |
| `yearMtBegin` | query | string | – | 모집공고월 시작 (YYYYMM) |
| `yearMtEnd` | query | string | – | 모집공고월 종료 (YYYYMM) |

### 요청 파라미터 — `ltRsdtRcritNtcList` (공공분양)

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|------|------|
| `serviceKey` | query | string | ✅ | 공공데이터포털에서 받은 인증키 |
| `brtcCode` | query | string | – | 광역시도 코드 |
| `signguCode` | query | string | – | 시군구 코드 |
| `numOfRows` | query | string | – | 페이지당 데이터 개수 |
| `pageNo` | query | string | – | 페이지 번호 |
| `houseTy` | query | string | – | 주택유형 |
| `yearMtBegin` | query | string | – | 모집공고월 시작 (YYYYMM) |
| `yearMtEnd` | query | string | – | 모집공고월 종료 (YYYYMM) |

### 응답 schema — 공통 (`item` 객체)

| 필드 | 타입 | 설명 |
|------|------|------|
| `pblancId` | string | 공고 ID |
| `houseSn` | number | 주택 일련번호 |
| `sttusNm` | string | 상태명 |
| `pblancNm` | string | 공고명 |
| `suplyInsttNm` | string | 공급 기관명 |
| `houseTyNm` | string | 주택유형명 |
| `suplyTyNm` | string | 공급유형명 (rsdtRcritNtcList 전용) |
| `suplyHoCo` | string | 공급 호수 (전세임대 해당, rsdtRcritNtcList 전용) |
| `beforePblancId` | string | 이전 공고 ID |
| `rcritPblancDe` | string | 모집공고 일자 |
| `przwnerPresnatnDe` | string | 당첨자 발표 일자 |
| `refrnc` | string | 문의처 |
| `url` | string | 모집공고 URL |
| `pcUrl` | string | 마이홈포털 PC URL |
| `mobileUrl` | string | 마이홈포털 Mobile URL |
| `hsmpNm` | string | 단지명 |
| `brtcNm` | string | 광역시도명 |
| `signguNm` | string | 시군구명 |
| `fullAdres` | string | 전체 주소 |
| `rnCodeNm` | string | 도로명 (도로명주소일 때) |
| `refrnLegaldongNm` | string | 참조 법정동명 (지번주소일 때) |
| `pnu` | string | PNU |
| `heatMthdNm` | string | 난방 방식명 |
| `totHshldCo` | string | 총 세대수 (rsdtRcritNtcList 전용) |
| `sumSuplyCo` | number | 공급 호수 |
| `rentGtn` | number | 최소 임대보증금 (rsdtRcritNtcList 전용) |
| `enty` | number | 최소 계약금 |
| `prtpay` | number | 최소 중도금 |
| `surlus` | number | 최소 잔금 |
| `mtRntchrg` | number | 최소 월 임대료 (rsdtRcritNtcList 전용) |
| `beginDe` | string | 모집 시작 일자 |
| `endDe` | string | 모집 종료 일자 |

### 인증
`serviceKey` (Query Parameter, URL-encoded). 본 알리미는 `os.environ["MYHOME_API_KEY"]`로 주입하고 GitHub Actions Secret에서 관리.

### 호출 예시 (마스킹)
```
GET https://apis.data.go.kr/1613000/HWSPR02/rsdtRcritNtcList?
    serviceKey=YOUR_SERVICE_KEY_HERE
    &brtcCode=11
    &pageNo=1
    &numOfRows=100
```

---

## 2. 국토교통부_마이홈포털 예비입주자 대기현황 조회서비스 (15108378)

**Base URL**: `https://apis.data.go.kr/1613000/HWSPR03`
**제공기관**: 국토교통부 (마이홈포털)
**관리부서**: 청년주거정책과 (☎ 044-201-3630)
**등록일**: 2022-11-24 | **수정일**: 2026-04-08 | **업데이트 주기**: 실시간
**API 유형**: REST | **데이터포맷**: JSON
**공식 명세**: <https://www.data.go.kr/data/15108378/openapi.do>
**참고문서**: `붙임1. 요청 파라미터 코드(예비입주자 대기현황)_260331.xlsx` ✅ **분석 완료** → [부록 A-1~A-3](#a-1-광역시도-코드-마이홈-api-공통--brtccode) 참조 (15108420과 코드 일부 차이!)
**코드 사용 위치**: `부동산_알리미_v2.py` L54 (상수 정의), L1378 (`scrape_waitlist`)

### 개요
광역시도, 시군구, 임대종류, 주택유형을 기준으로 예비입주자 대기현황 정보를 조회. 입주대기자수·퇴거건수 등을 제공.

### 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/moveWaitStsList` | 예비입주자 대기현황 조회 |

### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|------|------|
| `serviceKey` | query | string | ✅ | 공공데이터포털에서 받은 인증키 |
| `brtcCode` | query | string | ✅ | 광역시도 코드 |
| `signguCode` | query | string | – | 시군구 코드 |
| `numOfRows` | query | string | – | 페이지당 데이터 개수 (기본 10) |
| `pageNo` | query | string | – | 페이지 번호 (기본 1) |
| `suplyTy` | query | string | – | 임대종류 |
| `houseTy` | query | string | – | 주택유형 |

### 응답 schema — `item`

| 필드 | 타입 | 설명 |
|------|------|------|
| `rtsInsttNm` | string | 임대사업자명 |
| `brtcNm` | string | 광역시도명 |
| `signguNm` | string | 시군구명 |
| `rnAdres` | string | 도로명 주소 |
| `hsmpSn` | number | 단지 일련번호 |
| `hsmpNm` | string | 단지명 |
| `houseTyNm` | string | 주택유형명 |
| `suplyTyNm` | string | 공급유형명 |
| `styleNm` | string | 형명 |
| `drwtUnit` | string | 추첨단위 |
| `waitCo` | number | 입주대기자 수 |
| `trmnatCo` | number | 퇴거건수 |

### 인증
`serviceKey` (Query Parameter)

---

## 3. 국토교통부_마이홈포털 공공임대주택 단지정보 조회 서비스 (15110581)

**Base URL**: `https://apis.data.go.kr/1613000/HWSPR04`
**제공기관**: 국토교통부 (마이홈포털)
**관리부서**: 청년주거정책과 (☎ 044-201-3630)
**등록일**: 2022-12-16 | **수정일**: 2026-04-08 | **업데이트 주기**: 실시간
**API 유형**: REST | **데이터포맷**: JSON
**공식 명세**: <https://www.data.go.kr/data/15110581/openapi.do>
**참고문서**: `붙임1. 요청 파라미터 코드(공공임대주택 단지정보)_260331.xlsx` ✅ **분석 완료** → [부록 A-1](#a-1-광역시도-코드-마이홈-api-공통--brtccode) 참조 (광역시도+시군구 코드 257행)
**코드 사용 위치**: `부동산_알리미_v2.py` L55 (상수 정의), L1479 (`scrape_complex`)

### 개요
공공임대주택 단지별 보증금·월임대료·세대수·면적·난방방식 등 상세 단지정보를 조회. 본 알리미에서 가격 매칭(`💰` 태그) 캐시(7일, Supabase `kv_cache`)의 원천 데이터로 사용.

### 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/rentalHouseGwList` | 공공임대주택 단지정보 조회 |

### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|------|------|
| `serviceKey` | query | string | ✅ | 공공데이터포털에서 받은 인증키 |
| `brtcCode` | query | string | ✅ | 광역시도 코드 |
| `signguCode` | query | string | ✅ | 시군구 코드 |
| `numOfRows` | query | string | ✅ | 페이지당 데이터 개수 (기본 10) |
| `pageNo` | query | string | ✅ | 페이지 번호 (기본 1) |

### 응답 schema — `item` (23 필드)

| 필드 | 타입 | 설명 |
|------|------|------|
| `hsmpSn` | number | 단지 식별자 |
| `insttNm` | string | 기관명 |
| `brtcCode` | string | 광역시도 코드 |
| `brtcNm` | string | 광역시도명 |
| `signguCode` | string | 시군구 코드 |
| `signguNm` | string | 시군구명 |
| `hsmpNm` | string | 단지명 |
| `rnAdres` | string | 도로명 주소 |
| `pnu` | string | PNU |
| `competDe` | string | 준공 일자 |
| `hshldCo` | number | 세대수 |
| `suplyTyNm` | string | 공급유형명 |
| `styleNm` | string | 형명 |
| `suplyPrvuseAr` | number | 공급 전용면적 |
| `suplyCmnuseAr` | number | 공급 공용면적 |
| `houseTyNm` | string | 주택유형명 |
| `heatMthdDetailNm` | string | 난방방식 |
| `buldStleNm` | string | 건물 형태 |
| `elvtrInstlAtNm` | string | 승강기 설치 여부 |
| `parkngCo` | number | 주차수 |
| `bassRentGtn` | number | 기본 임대보증금 |
| `bassMtRntchrg` | number | 기본 월임대료 |
| `bassCnvrsGtnLmt` | number | 기본 전환보증금 한도 |

### 인증
`serviceKey` (Query Parameter)

### 비고
- 한 번 호출 시 ~7만 건 반환 → 본 알리미에서는 7일 캐시(Supabase `kv_cache` jsonb 또는 로컬 `단지정보_캐시.json` 폴백)로 운영.

---

## 4. 한국토지주택공사_분양임대공고문 조회 서비스 (15058530)

**Base URL (서비스 URL)**: `http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1`
**Call Back URL (실제 호출 엔드포인트)**: `http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1` ← **이중 경로 주의**
**서비스 명세 URL (WADL)**: `http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1?_wadl&type=json`
**제공기관**: 한국토지주택공사 (LH)
**관리부서**: IT운영처 데이터운영팀 (☎ 055-922-5513)
**등록일**: 2019-08-14 | **서비스 시작일**: 2019-08-01 | **수정일**: 2026-03-17 | **업데이트 주기**: 수시
**API 유형**: REST (GET) | **데이터포맷**: JSON | **서비스 버전**: 1.0 | **메시지 교환유형**: Request-Response
**평균 응답시간**: 500 ms | **초당 최대 트랜잭션**: 30 tps | **최대 메시지 사이즈**: 4000 byte
**보안적용 수준**: serviceKey 인증 / 전자서명·암호화 없음 / SSL 미적용 (HTTP)
**공식 명세**: <https://www.data.go.kr/data/15058530/openapi.do>
**참고문서**: `OpenAPI활용가이드_한국토지주택공사_분양임대공고조회_20260316.docx` ✅ **활용가이드 docx 기반 보완 완료 (2026-05-28)** → [부록 A-5](#a-5-lh-분양임대공고문-15058530-코드-사전) 참조
**코드 사용 위치**: `부동산_알리미_v2.py` L1279 (상수 `LH_API_BASE`), L1316 (`scrape_lh_api`)
**상태**: 2026-05-21 활용신청 승인, 키 전파 대기 — 현재 403 graceful 처리 중
**확신도**: **100%** (활용가이드 docx 기반 보완 완료, 2026-05-28) — 이전 92%(DOM 파싱)에서 갱신
**⚠️ 중요**: Swagger UI의 파라미터명(`PAN_NT_ST_DT`, `CLSG_DT`)은 활용가이드의 정식 명세(`PAN_ST_DT`, `PAN_ED_DT`, `CLSG_ST_DT`, `CLSG_ED_DT`)와 다름. **활용가이드가 정식 — 본 섹션 요청 파라미터 표 및 부록 A-5의 매핑 표 참조하여 코드 수정 필요**.

### 개요
광역시도 코드, 공고유형코드, 공고상태코드, 공고명을 기준으로 LH의 분양·임대 공고문 목록을 조회. 알리미는 공고 게시일/마감일 범위 검색용으로 사용. 응답에 포함된 `PAN_ID`, `SPL_INF_TP_CD`, `CCR_CNNT_SYS_DS_CD`는 LH의 후속 API(분양임대공고별 공급정보 조회 등) 호출 키로 사용됨.

### 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1` | 분양·임대공고문 목록 조회 (Base URL 뒤에 `/lhLeaseNoticeInfo1` 한 번 더 붙임) |

### 요청 파라미터 (활용가이드 기준 정식 11개)

> 항목구분: 필수(1) / 옵션(0) — 활용가이드 docx 1.1다)b) 표 그대로 반영.

| 한글명 | 영문 변수명 | 항목크기 | 필수 | 샘플 | 설명 |
|--------|------------|---------|------|------|------|
| 인증키 | `serviceKey` | 100 | ✅ | 인증키 (URL Encode) | 공공데이터포털에서 발급받은 인증키 |
| 한 페이지 결과 수 | `PG_SZ` | 4 | ✅ | `10` | 한 페이지 결과 수 |
| 페이지 번호 | `PAGE` | 4 | ✅ | `1` | 페이지 번호 |
| 공고명 | `PAN_NM` | 50 | – | `대전` | 공고명으로 조회 (부분일치) |
| 공고유형코드 | `UPP_AIS_TP_CD` | 10 | – | `01` | 공고유형코드 (01토지·05분양·06임대·13주거복지·22상가·39신혼희망타운) |
| 지역코드 | `CNP_CD` | 10 | – | `11` | 지역코드 (11서울·41경기·28인천 등) |
| 공고상태코드 | `PAN_SS` | 10 | – | `공고중` | 공고상태 (공고중·접수중·접수마감·상담요청·정정공고중) |
| 기간검색 게시일-시작일 | `PAN_ST_DT` | 8 | ✅ | `20190815` | YYYYMMDD (초기값: 현재일 −2개월) |
| 기간검색 게시일-종료일 | `PAN_ED_DT` | 8 | ✅ | `20191015` | YYYYMMDD (초기값: 현재일) |
| 기간검색 마감일-시작일 | `CLSG_ST_DT` | 8 | – | `20191015` | YYYYMMDD |
| 기간검색 마감일-종료일 | `CLSG_ED_DT` | 8 | – | `20191015` | YYYYMMDD |

### 응답 schema — Response Element (활용가이드 기준 정식 18개 + PAN_DT 옵션)

| 한글명 | 영문 변수명 | 항목크기 | 필수 | 샘플 | 설명 |
|--------|------------|---------|------|------|------|
| 결과코드 | `SS_CODE` | 2 | ✅ | `Y` | 결과코드 (참고: 오류 시 에러코드는 부록 A-5 참조) |
| 출력일시 | `RS_DTTM` | 20 | ✅ | `20190723054417` | 출력일시 |
| 순번 | `RNUM` | 10 | ✅ | `1` | 데이터 순번 |
| 공고유형명 | `UPP_AIS_TP_NM` | 10 | ✅ | `임대주택` | 공고유형명 |
| 공고세부유형명 | `AIS_TP_CD_NM` | 10 | ✅ | `행복주택` | 공고세부유형명 |
| 공고명 | `PAN_NM` | 100 | ✅ | `행복도시3-1M5블록 10년 공공임대주택리츠` | 데이터 조회용 키값 |
| 지역명 | `CNP_CD_NM` | 50 | ✅ | `전국` | 지역명 |
| 공고게시일 | `PAN_NT_ST_DT` | 10 | ✅ | `2019.07.23` | 공고게시일 (응답은 `YYYY.MM.DD` 점 구분자) |
| 공고마감일 | `CLSG_DT` | 10 | ✅ | `2019.08.22` | 공고마감일 (응답은 `YYYY.MM.DD`) |
| 공고상태 | `PAN_SS` | 10 | ✅ | `공고중` | 공고상태 |
| 전체조회건수 | `ALL_CNT` | 10 | ✅ | `21710` | 전체조회건수 |
| 공고상세URL | `DTL_URL` | 100 | ✅ | `https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=…` | PC용 공고상세 URL |
| 공고상세 모바일 URL | `DTL_URL_MOB` | 100 | ✅ | (동일 URL) | 모바일용 공고상세 URL |
| 공급정보구분코드 | `SPL_INF_TP_CD` | 2 | ✅ | `010` | **후속 API**(분양임대공고별 공급정보조회) 호출용 키 |
| 고객센터연계시스템구분코드 | `CCR_CNNT_SYS_DS_CD` | 2 | ✅ | `02` | **후속 API** 호출용 키 |
| 공고아이디 | `PAN_ID` | 30 | ✅ | `0000061060` | **후속 API의 핵심 키** |
| 상위매물유형코드 | `UPP_AIS_TP_CD` | 2 | ✅ | `01` | 후속 API 호출용 키 |
| 매물유형코드 | `AIS_TP_CD` | 2 | ✅ | `01` | 후속 API 호출용 키 |
| 모집공고일 | `PAN_DT` | 8 | – | `20200508` | YYYYMMDD (토지·상가는 미제공) |

> 응답 JSON은 3중 배열 구조: `[{"dsSch":[요청파라미터 echo]}, {"resHeader":[{SS_CODE, RS_DTTM}], "dsList":[데이터 행…]}]`. 실제 결과 행은 두 번째 객체의 `dsList` 안에 있음.

### 인증
`serviceKey` (Query Parameter, URL Encode). 활용가이드 docx 표기는 **소문자 `serviceKey`** (이전 본 문서에서 대문자 `ServiceKey`로 잘못 기재됐던 부분 정정 — 2026-05-28). 본 알리미는 다른 마이홈/청약홈 API와 동일하게 `MYHOME_API_KEY` 환경변수에서 주입.

### 호출 예시 (활용가이드 d) 요청/응답 예제 기반, 마스킹)
```
GET http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1?
    serviceKey=YOUR_SERVICE_KEY_HERE
    &PG_SZ=10
    &PAGE=1
    &PAN_ST_DT=20260301
    &PAN_ED_DT=20260528
    &CNP_CD=11
    &UPP_AIS_TP_CD=06
```

### 비고
- 현재 알리미는 본 API 키 전파 대기 중이며, 403 응답을 graceful하게 처리하고 LH 청약플러스 웹 스크래핑(`scrape_lh_rental`, `scrape_lh_sale`)으로 폴백 중.
- HTTP 스키마: `http://` (HTTPS 미지원, 다른 마이홈 API는 HTTPS)
- 신청가능 트래픽: 개발계정 10,000 / 운영계정은 활용사례 등록 시 증가 가능.
- 결과 정렬: 응답 샘플 기준 `PAN_NT_ST_DT` 내림차순(최신 공고 우선)으로 추정.

---

## 5. 한국부동산원_청약홈 분양정보 조회 서비스 (15098547)

**Base URL**: `https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1`
**제공기관**: 한국부동산원
**관리부서**: AX전략부 데이터인프라관리팀 (☎ 053-663-8466)
**등록일**: 2022-01-24 | **수정일**: 2024-03-19 | **업데이트 주기**: 실시간
**API 유형**: REST | **데이터포맷**: JSON + XML
**공식 명세 (포털)**: <https://www.data.go.kr/data/15098547/openapi.do>
**Swagger 명세 (직접)**: <https://infuser.odcloud.kr/api/stages/37000/api-docs>
**참고문서**: `기술문서_청약홈 분양정보 조회 서비스_260129.docx` ✅ **분석 완료** → [부록 A-6](#a-6-청약홈-15098547-코드-사전) 참조 (10개 엔드포인트 전체 + 코드 사전)
**코드 사용 위치**: `부동산_알리미_v2.py` L1181 (base 정의), L1215 (`scrape_cheongyanghome`), L1156 (`fetch_cheong_mdl_layers`)

### 개요
한국부동산원 청약홈에서 제공하는 APT(민영/공공)/오피스텔/도시형/공공지원민간임대 등의 분양정보를 조회. 알리미는 그중 **APT 분양정보 상세** + **APT 주택형별 상세** 2개 엔드포인트만 사용.

### 전체 엔드포인트 목록 (10개, Swagger 기준)

| Method | Path | 설명 | 본 알리미 사용 |
|--------|------|------|----------------|
| GET | `/getAPTLttotPblancDetail` | APT 분양정보 상세조회 | ✅ |
| GET | `/getAPTLttotPblancMdl` | APT 분양정보 주택형별 상세조회 | ✅ |
| GET | `/getUrbtyOfctlLttotPblancDetail` | 오피스텔/도시형 분양 상세 | – |
| GET | `/getUrbtyOfctlLttotPblancMdl` | 오피스텔/도시형 주택형별 | – |
| GET | `/getRemndrLttotPblancDetail` | 무순위/잔여세대 상세 | – |
| GET | `/getRemndrLttotPblancMdl` | 무순위/잔여 주택형별 | – |
| GET | `/getPblPvtRentLttotPblancDetail` | 공공지원민간임대 상세 | – |
| GET | `/getPblPvtRentLttotPblancMdl` | 공공지원민간임대 주택형별 | – |
| GET | `/getOPTLttotPblancDetail` | (분양 임의공급) 상세 | – |
| GET | `/getOPTLttotPblancMdl` | (분양 임의공급) 주택형별 | – |

### 5-A. `getAPTLttotPblancDetail` — APT 분양정보 상세조회

#### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|------|------|
| `page` | query | integer | – | page index |
| `perPage` | query | integer | – | page size |
| `returnType` | query | string | – | 기본 JSON, `XML`로 설정 시 XML |
| `serviceKey` | query | string | ✅ | 공공데이터포털 인증키 |
| `cond[HOUSE_MANAGE_NO::EQ]` | query | string | – | 주택관리번호 |
| `cond[PBLANC_NO::EQ]` | query | string | – | 공고번호 |
| `cond[HOUSE_NM::LIKE]` | query | string | – | 주택명 |
| `cond[HOUSE_SECD::EQ]` | query | string | – | 주택구분코드 (`01`=APT, `09`=민간사전청약, `10`=신혼희망타운) |
| `cond[HOUSE_DTL_SECD::EQ]` | query | string | – | 주택상세구분코드 (`01`=민영, `03`=국민) |
| `cond[SUBSCRPT_AREA_CODE::EQ]` | query | string | – | 공급지역코드 |
| `cond[SUBSCRPT_AREA_CODE_NM::EQ]` | query | string | – | 공급지역명 (예: `서울`, `경기`, `인천`) |
| `cond[HSSPLY_ADRES::LIKE]` | query | string | – | 공급위치 |
| `cond[RCRIT_PBLANC_DE::LT]` | query | string | – | 모집공고일 < |
| `cond[RCRIT_PBLANC_DE::LTE]` | query | string | – | 모집공고일 ≤ |
| `cond[RCRIT_PBLANC_DE::GT]` | query | string | – | 모집공고일 > |
| `cond[RCRIT_PBLANC_DE::GTE]` | query | string | – | 모집공고일 ≥ |

#### 응답 schema (`getAPTLttotPblancDetail_model`, 49 필드 발췌)

| 필드 | 타입 | 설명 |
|------|------|------|
| `HOUSE_MANAGE_NO` | string | 주택관리번호 |
| `PBLANC_NO` | string | 공고번호 |
| `HOUSE_NM` | string | 주택명 |
| `HOUSE_SECD` | string | 주택구분코드 (`01`=APT, `09`=민간사전청약, `10`=신혼희망타운) |
| `HOUSE_SECD_NM` | string | 주택구분코드명 |
| `HOUSE_DTL_SECD` | string | 주택상세구분코드 (`01`=민영, `03`=국민) |
| `HOUSE_DTL_SECD_NM` | string | 주택상세구분코드명 |
| `RENT_SECD` | string | 분양구분코드 (`0`=분양주택, `1`=분양전환 가능임대) |
| `RENT_SECD_NM` | string | 분양구분코드명 |
| `SUBSCRPT_AREA_CODE` | string | 공급지역코드 |
| `SUBSCRPT_AREA_CODE_NM` | string | 공급지역명 |
| `HSSPLY_ZIP` | string | 공급위치 우편번호 |
| `HSSPLY_ADRES` | string | 공급위치 |
| `TOT_SUPLY_HSHLDCO` | integer | 공급규모 |
| `RCRIT_PBLANC_DE` | string | 모집공고일 |
| `NSPRC_NM` | string | 신문사 |
| `RCEPT_BGNDE` / `RCEPT_ENDDE` | string | 청약접수 시작·종료일 |
| `SPSPLY_RCEPT_BGNDE` / `SPSPLY_RCEPT_ENDDE` | string | 특별공급 접수 시작·종료일 |
| `GNRL_RNK1_CRSPAREA_RCPTDE` / `_ENDDE` | string | 1순위 해당지역 접수 시작·종료일 |
| `GNRL_RNK1_ETC_GG_RCPTDE` / `_ENDDE` | string | 1순위 경기지역 접수 시작·종료일 |
| `GNRL_RNK1_ETC_AREA_RCPTDE` / `_ENDDE` | string | 1순위 기타지역 접수 시작·종료일 |
| `GNRL_RNK2_CRSPAREA_RCPTDE` / `_ENDDE` | string | 2순위 해당지역 |
| `GNRL_RNK2_ETC_GG_RCPTDE` / `_ENDDE` | string | 2순위 경기지역 |
| `GNRL_RNK2_ETC_AREA_RCPTDE` / `_ENDDE` | string | 2순위 기타지역 |
| `PRZWNER_PRESNATN_DE` | string | 당첨자 발표일 |
| `CNTRCT_CNCLS_BGNDE` / `_ENDDE` | string | 계약 시작·종료일 |
| `HMPG_ADRES` | string | 홈페이지주소 |
| `CNSTRCT_ENTRPS_NM` | string | 건설업체명 (시공사) |
| `MDHS_TELNO` | string | 문의처 |
| `BSNS_MBY_NM` | string | 사업주체명 (시행사) |
| `MVN_PREARNGE_YM` | string | 입주예정월 |
| `SPECLT_RDN_EARTH_AT` | string | 투기과열지구 여부 |
| `MDAT_TRGET_AREA_SECD` | string | 조정대상지역 (`Y`=과열, `N`=미대상) |
| `PARCPRC_ULS_AT` | string | 분양가상한제 |
| `IMPRMN_BSNS_AT` | string | 정비사업 |
| `PUBLIC_HOUSE_EARTH_AT` | string | 공공주택지구 |
| `LRSCL_BLDLND_AT` | string | 대규모 택지개발지구 |
| `NPLN_PRVOPR_PUBLIC_HOUSE_AT` | string | 수도권 내 민영 공공주택지구 |
| `PUBLIC_HOUSE_SPCLW_APPLC_AT` | string | 공공주택 특별법 적용 여부 |
| `PBLANC_URL` | string | 분양정보 URL |

### 5-B. `getAPTLttotPblancMdl` — APT 분양정보 주택형별 상세조회

#### 요청 파라미터

| 이름 | 위치 | 타입 | 필수 | 설명 |
|------|------|------|------|------|
| `page` | query | integer | – | page index |
| `perPage` | query | integer | – | page size |
| `returnType` | query | string | – | 기본 JSON |
| `serviceKey` | query | string | ✅ | 인증키 |
| `cond[HOUSE_MANAGE_NO::EQ]` | query | string | – | 주택관리번호 |
| `cond[PBLANC_NO::EQ]` | query | string | – | 공고번호 |

#### 응답 schema (`getAPTLttotPblancMdl_model`, 17 필드)

| 필드 | 타입 | 설명 |
|------|------|------|
| `HOUSE_MANAGE_NO` | string | 주택관리번호 |
| `PBLANC_NO` | string | 공고번호 |
| `MODEL_NO` | string | 모델번호 |
| `HOUSE_TY` | string | 주택형 |
| `SUPLY_AR` | string | 공급면적 |
| `SUPLY_HSHLDCO` | integer | 일반공급 세대수 |
| `SPSPLY_HSHLDCO` | integer | 특별공급 세대수 (전체) |
| `MNYCH_HSHLDCO` | integer | **특별공급-다자녀가구 세대수** 👪 |
| `NWWDS_HSHLDCO` | integer | **특별공급-신혼부부 세대수** 💑 |
| `LFE_FRST_HSHLDCO` | integer | **특별공급-생애최초 세대수** 🌱 |
| `OLD_PARNTS_SUPORT_HSHLDCO` | integer | **특별공급-노부모부양 세대수** 👵 |
| `INSTT_RECOMEND_HSHLDCO` | integer | 특별공급-기관추천 세대수 |
| `ETC_HSHLDCO` | integer | 특별공급-기타 세대수 |
| `TRANSR_INSTT_ENFSN_HSHLDCO` | integer | 특별공급-이전기관 세대수 |
| `YGMN_HSHLDCO` | integer | **특별공급-청년 세대수** 🧑 |
| `NWBB_HSHLDCO` | integer | **특별공급-신생아 세대수** 👶 |
| `LTTOT_TOP_AMOUNT` | string | 공급금액 (분양최고금액, 단위: 만원) |

#### 알리미에서의 활용
- 본 응답의 `*_HSHLDCO` 필드(굵게 표시)는 알리미 `TARGET_LAYERS` 6종(신생아·청년·신혼부부·생애최초·다자녀·노부모) **대상계층 자동 추출**의 정확한 근거.
- 값 > 0인 특공 필드만 합집합 → 공고별 `대상계층` 배지 생성 (`대상계층_확인=True` 플래그).
- `LTTOT_TOP_AMOUNT` 범위로 슬랙 가격 태그(예: `💰3.9~6.7억`) 산출.

### 인증
`serviceKey` (Query Parameter). 다른 마이홈 API와 동일한 `MYHOME_API_KEY` 사용.

### 호출 예시 (마스킹)
```
GET https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?
    page=1
    &perPage=100
    &serviceKey=YOUR_SERVICE_KEY_HERE
    &cond[SUBSCRPT_AREA_CODE_NM::EQ]=서울
```

### 비고
- 비용: 무료
- 신청가능 트래픽: 개발계정 40,000 / 운영계정 활용사례 등록 시 증가
- 심의: 개발단계 자동승인 / **운영단계 심의승인** (운영 전환 시 심의 필요)

---

## 📚 부록 A — 코드값 사전 (공식 활용가이드 추출)

> 본 부록은 data.go.kr 각 API의 "참고문서" (활용가이드 docx / 요청 파라미터 코드 xlsx)에서 직접 추출한 **코드값 → 의미** 매핑이다. Swagger description만으로는 알 수 없는 코드값 의미를 확보.

---

### A-1. 광역시도 코드 (마이홈 API 공통 — `brtcCode`)

xlsx 출처: `붙임1. 요청 파라미터 코드(공공주택 모집공고)_260331.xlsx` 등 3종 공통

| 코드 | 광역시도 |
|------|---------|
| `11` | 서울특별시 |
| `26` | 부산광역시 |
| `27` | 대구광역시 |
| `28` | 인천광역시 |
| `29` | 광주광역시 |
| `30` | 대전광역시 |
| `31` | 울산광역시 |
| `36` | 세종특별자치시 |
| `41` | 경기도 |
| `43` | 충청북도 |
| `44` | 충청남도 |
| `45` | 전라북도 |
| `46` | 전라남도 |
| `47` | 경상북도 |
| `48` | 경상남도 |
| `50` | 제주특별자치도 |
| `51` | 강원특별자치도 |

> 본 알리미는 `11`(서울) / `41`(경기) / `28`(인천)만 사용. 시군구 코드는 xlsx 파일 전체(257행)에 수록 — 코드와 함께 코드 사전이 필요한 경우 원본 xlsx 참조.

### A-2. 주택유형 코드 (`houseTy`)

마이홈 모집공고·대기현황 공통

| 코드 | 주택유형 |
|------|---------|
| `11` | 아파트 |
| `12` | 연립주택 |
| `13` | 다세대주택 |
| `14` | 단독주택 |
| `15` | 오피스텔 |
| `16` | 다가구주택 |

### A-3. 공급유형 코드 (`suplyTy`) — **API마다 코드 의미가 다르므로 주의 ⚠️**

#### 15108420 (공공주택 모집공고)
| 코드 | 공급유형 |
|------|---------|
| `01` | 영구임대 |
| `02` | 국민임대 |
| `03` | 50년임대 |
| `04` | 매입임대 |
| `05` | 10년임대 |
| `06` | 5년임대 |
| `07` | 장기전세 |
| `08` | 전세임대 |
| `09` | 매입임대 |
| `10` | 행복주택 |
| `11` | 공공지원민간임대 |
| `12` | 통합공공임대 |
| `13` | 6년임대 |

#### 15108378 (대기현황) — 약간 다름
| 코드 | 공급유형 |
|------|---------|
| `01` | 영구임대 |
| `02` | 국민임대 |
| `03` | 50년임대 |
| `04` | 매입임대 |
| `05` | 10년임대 |
| `06` | 5년임대 |
| `07` | 장기전세 |
| `09` | 행복주택 |
| `10` | 공공기숙사 |
| `11` | 통합공공임대 |
| `12` | **6년임대** ← (15108420은 `12`가 통합공공임대) |

### A-4. 전세형 여부 (`lfstsTyAt`) / 월임대료 구분 (`bassMtRntchrgSe`)

| 파라미터 | 코드 | 의미 |
|----------|------|------|
| 전세형 여부 | `Y` / `N` | 전세형 모집 여부 |
| 월임대료 구분 | `01` | 5만원 미만 |
| 월임대료 구분 | `02` | 5~10만원 미만 |
| 월임대료 구분 | `03` | 10~20만원 미만 |
| 월임대료 구분 | `04` | 20~30만원 미만 |
| 월임대료 구분 | `05` | 30만원 이상 |

---

### A-5. LH 분양임대공고문 (15058530) 코드 사전

docx 출처: `OpenAPI활용가이드_한국토지주택공사_분양임대공고조회_20260316.docx`

#### 공고유형코드 (`UPP_AIS_TP_CD`)
| 코드 | 설명 |
|------|------|
| `01` | 토지 |
| `05` | 분양주택 |
| `06` | 임대주택 |
| `13` | 주거복지 |
| `22` | 상가 |
| `39` | 신혼희망타운 |

#### 지역코드 (`CNP_CD`) — 마이홈 brtcCode와 동일하나 일부 차이
| 코드 | 지역 |
|------|------|
| `11` | 서울특별시 |
| `26` | 부산광역시 |
| `27` | 대구광역시 |
| `28` | 인천광역시 |
| `29` | 광주광역시 |
| `30` | 대전광역시 |
| `31` | 울산광역시 |
| `36110` | 세종특별자치시 (5자리!) |
| `41` | 경기도 |
| `42` | 강원도 |
| `43` | 충청북도 |
| `44` | 충청남도 |
| `52` | 전북특별자치도 |
| `46` | 전라남도 |
| `47` | 경상북도 |
| `48` | 경상남도 |
| `50` | 제주특별자치도 |

#### 공고상태코드 (`PAN_SS`)
- `공고중` / `접수중` / `접수마감` / `상담요청` / `정정공고중` (한글 그대로 사용)

#### ⚠️ Swagger ↔ 활용가이드 파라미터명 차이 (활용가이드가 정식)

| Swagger UI | 활용가이드 (정식) | 의미 | 필수 |
|------------|-------------------|------|------|
| `PAN_NT_ST_DT` | `PAN_ST_DT` | 게시일 시작 (YYYYMMDD) | ✅ |
| – (없음) | `PAN_ED_DT` | 게시일 종료 (YYYYMMDD) | ✅ |
| `CLSG_DT` | `CLSG_ST_DT` | 마감일 시작 | – |
| – (없음) | `CLSG_ED_DT` | 마감일 종료 | – |

본 알리미 코드는 Swagger 명세를 기반으로 작성됐으나, 실제 API는 **활용가이드 파라미터명을 사용**해야 정상 동작 (현재 403 대기 상태와 별개로, 향후 호출 시 확인 필요).

#### 응답 필드 추가 (Swagger 누락 항목)
| 영문 | 한글 | 설명 |
|------|------|------|
| `DTL_URL_MOB` | 공고상세 모바일 URL | LH 모바일 공고상세 URL |
| `SPL_INF_TP_CD` | 공급정보구분코드 | 후속 API(공급정보) 호출용 키 |
| `CCR_CNNT_SYS_DS_CD` | 고객센터연계시스템구분코드 | 후속 API 호출용 키 |
| `PAN_ID` | 공고아이디 | (예: `0000061060`) 후속 API 핵심 키 |
| `UPP_AIS_TP_CD` | 상위매물유형코드 | – |
| `AIS_TP_CD` | 매물유형코드 | – |
| `PAN_DT` | 모집공고일 (8자리, YYYYMMDD) | 토지·상가는 미제공 |

#### 에러코드 (`SS_CODE` ↔ 메시지)
| 코드 | 메시지 | 의미 |
|------|--------|------|
| `0` | NORMAL_CODE | 정상 |
| `1` | APPLICATION_ERROR | 어플리케이션 에러 |
| `2` | DB_ERROR | DB 에러 |
| `3` | NODATA_ERROR | 데이터 없음 |
| `4` | HTTP_ERROR | HTTP 에러 |
| `5` | SERVICETIMEOUT_ERROR | 서비스 연결실패 |
| `10` | INVALID_REQUEST_PARAMETER_ERROR | 잘못된 파라미터 |
| `11` | NO_MANDATORY_REQUEST_PARAMETERS_ERROR | 필수 파라미터 누락 |
| `12` | NO_OPENAPI_SERVICE_ERROR | API 없음/폐기 |
| `20` | SERVICE_ACCESS_DENIED_ERROR | 접근 거부 |
| `21` | TEMPORARILY_DISABLE_THE_SERVICEKEY_ERROR | 일시적 키 사용불가 |
| `22` | LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR | 요청제한 초과 |
| `30` | SERVICE_KEY_IS_NOT_REGISTERED_ERROR | 미등록 키 |
| `31` | DEADLINE_HAS_EXPIRED_ERROR | 기한만료 키 |
| `32` | UNREGISTERED_IP_ERROR | 미등록 IP |
| `33` | UNSIGNED_CALL_ERROR | 서명 없음 |
| `99` | UNKNOWN_ERROR | 기타 |

#### 기타 메타데이터 (활용가이드에서 확인)
- 서비스 URL (WSDL/WADL): `http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1?_wadl&type=json`
- 서비스 버전: 1.0
- 서비스 시작일: 2019-08-01
- 평균 응답 시간: 500 ms
- **초당 최대 트랜잭션: 30 tps**
- 최대 메시지 사이즈: 4000 byte

---

### A-6. 청약홈 (15098547) 코드 사전

docx 출처: `기술문서_청약홈 분양정보 조회 서비스_260129.docx`

#### 공급지역코드 (`SUBSCRPT_AREA_CODE`) — **마이홈/LH와 완전히 다른 체계 ⚠️**

| 코드 | 지역 |
|------|------|
| `100` | 서울 |
| `200` | 강원 |
| `300` | 대전 |
| `312` | 충남 |
| `338` | 세종 |
| `360` | 충북 |
| `400` | 인천 |
| `410` | 경기 |
| `500` | 광주 |
| `513` | 전남 |
| `560` | 전북 |
| `600` | 부산 |
| `621` | 경남 |
| `680` | 울산 |
| `690` | 제주 |
| `700` | 대구 |
| `712` | 경북 |

> 본 알리미는 코드 대신 `cond[SUBSCRPT_AREA_CODE_NM::EQ]=서울` 처럼 **한글명**으로 조회 (코드 매핑 회피).

#### 주택구분코드 (`HOUSE_SECD`)
| 코드 | 의미 |
|------|------|
| `01` | APT |
| `09` | 민간사전청약 |
| `10` | 신혼희망타운 |

#### 주택상세구분코드 (`HOUSE_DTL_SECD`)
| 코드 | 의미 |
|------|------|
| `01` | 민영 |
| `03` | 국민 |

#### 분양구분코드 (`RENT_SECD`)
| 코드 | 의미 |
|------|------|
| `0` | 분양주택 |
| `1` | 분양전환 가능임대 |

#### 조정대상지역 (`MDAT_TRGET_AREA_SECD`)
| 코드 | 의미 |
|------|------|
| `Y` | 과열지역 |
| `N` | 미대상주택 |

#### 오피스텔/도시형 주택구분 코드 (다른 엔드포인트 사용 시 참고)
| 코드 | 의미 |
|------|------|
| `0201` | 도시형생활주택 |
| `0202` | 오피스텔 |
| `0203` | 민간임대 |
| `0204` | 생활형숙박시설 |

#### 무순위/잔여 주택구분
| 코드 | 의미 |
|------|------|
| `04` | 무순위 |
| `06` | 불법행위 재공급 |

> 청약홈 활용가이드(docx)에는 본 알리미가 사용하지 않는 8개 추가 엔드포인트(오피스텔/도시형, 무순위, 공공지원민간임대 등)의 모든 응답 schema·요청 파라미터도 포함되어 있다. 향후 알리미 기능 확장 시 docx 직접 참조 권장.

---

## 부록 B — 비-OpenAPI 스크래핑 출처

본 알리미는 OpenAPI가 없거나 보완이 필요한 영역에서 다음 사이트의 HTML/AJAX를 스크래핑한다. 이들은 공식 OpenAPI가 아니므로 명세 아카이브 대상에서는 제외되었으나, 코드 의존도가 있어 참고용으로 기록.

| 사이트 | 함수 | URL | 메서드 | 용도 |
|--------|------|-----|--------|------|
| LH 청약플러스 (임대) | `scrape_lh_rental` | `https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026` | GET HTML | LH 임대공고 전체 페이지 |
| LH 청약플러스 (분양) | `scrape_lh_sale` | `https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1027` | GET HTML | LH 분양공고 전체 페이지 |
| 마이홈 포털 (백업) | `scrape_myhome_sale` | `https://www.myhome.go.kr/hws/portal/sch/selectRsdtRcritNtcView.do` | GET HTML | 분양 공고 백업 소스 |
| SH 서울주택도시공사 (임대) | `scrape_sh` | `https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/list.do?multi_itm_seq=2` | GET HTML | SH 임대 공고 |
| SH 서울주택도시공사 (분양) | `scrape_sh` | `https://www.i-sh.co.kr/app/lay2/program/S48T1581C1617/www/brd/m_244/list.do?multi_itm_seq=1` | GET HTML | SH 분양 공고 |
| GH 경기주택도시공사 (임대) | `scrape_gh` | `https://apply.gh.or.kr/sb/sr/sr7150/selectPbancRentHouseList.do` | GET HTML | GH 임대 공고 |
| GH 경기주택도시공사 (매입) | `scrape_gh` | `https://apply.gh.or.kr/sb/sr/sr7155/selectPbancRentHouseList.do` | GET HTML | GH 매입 공고 |
| 서울 청년안심주택 목록 | `scrape_seoul_youth` | `https://soco.seoul.go.kr/youth/pgm/home/yohome/bbsListJson.json` | POST JSON | 게시판 AJAX (bbsId=BMSR00015) |
| 서울 청년안심 단지비교 | `fetch_soco_price_map` | `https://soco.seoul.go.kr/youth/pgm/home/yohome/maplist.json` | POST JSON | 단지별 가격·자치구 매칭 |

---

## 🔐 인증키 관리 원칙

1. **절대 코드/문서/커밋에 평문 노출 금지**. 본 문서는 모든 키를 `YOUR_SERVICE_KEY_HERE`로 마스킹.
2. **저장 위치**: GitHub Secrets `MYHOME_API_KEY` (운영) / 로컬 환경변수 (개발).
3. **로딩 방식**: `os.environ.get("MYHOME_API_KEY", "")` — `부동산_알리미_v2.py` L52.
4. **노출 시 즉시 회전**: data.go.kr 마이페이지에서 재발급 → Secrets 값 교체. (HANDOFF.md 참조)

---

> 📌 본 문서는 2026-05-28 기준 공공데이터포털·odcloud.kr Swagger UI 직접 추출 + **각 API의 공식 활용가이드(docx/xlsx) 5종 분석**으로 작성됨. 원본 참고문서는 `./공식문서/` 폴더에 함께 보관:
>
> - `15108420_요청파라미터코드_공공주택모집공고.xlsx`
> - `15108378_요청파라미터코드_예비입주자대기현황.xlsx`
> - `15110581_요청파라미터코드_단지정보.xlsx`
> - `15058530_LH_분양임대공고문_활용가이드.docx`
> - `15098547_청약홈_기술문서.docx`
