# Maritime Ops Agent (ship-data)

동국대 ho_data 센서 Excel을 SQLite DB로 적재하고, **Ollama(Llama 3.1)** 가 7개 Python Tool을 호출해 운항 브리핑·보고서를 생성하는 프로토타입입니다.

> **인수인계용 저장소:** [github.com/yoonmojeon/ship-data](https://github.com/yoonmojeon/ship-data)

---

## 한 줄 요약

```
ho_data Excel  →  maritime.db (SQLite)  →  Python Tool 7개  →  Ollama 툴 라우팅  →  줄글 브리핑 / Word 보고서
```

LLM은 **숫자를 직접 계산하지 않습니다.** KPI·CII·배출량은 `agent/data_store.py`와 `agent/tools.py`에서 DB 집계 후, `agent/briefing.py`가 줄글로 포맷합니다.

---

## 프로젝트 구조

```
ship-data/
├── app.py                      # Gradio UI (운항 브리핑)
├── config.py                   # 선박 정보, LLM, CII 파라미터 ★
├── requirements.txt
├── ho_data/                    # 원본 Excel (로컬 배치, Git 미포함)
│   ├── 동국대_ship_*.xlsx      # 센서 시계열 (1시간 간격)
│   └── 동국대_ship_info_*.xlsx # Schedule(항차), Tag_Unit
├── data/
│   └── maritime.db             # load_hodata.py 실행 후 생성
├── agent/
│   ├── maritime_agent.py       # Ollama Agent Loop (툴 선택)
│   ├── tools.py                # 7개 Tool + CII 계산 로직 ★
│   ├── data_store.py           # DB 조회·집계·거리(SOG 적분) ★
│   ├── db_schema.py            # SQLite 스키마
│   ├── briefing.py             # Tool 결과 → 줄글 답변
│   └── reports.py              # Noon / MRV Word(.docx) 생성
└── scripts/
    ├── load_hodata.py          # Excel → DB 구축 ★
    └── export_db_to_excel.py   # DB → Excel 확인용
```

---

## 빠른 시작

### 1. 환경

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Ollama

```bash
ollama pull llama3.1:8b
ollama serve
```

### 3. 데이터 준비

`ho_data/` 폴더에 Excel 두 종류를 넣습니다.

| 파일 | 내용 |
|------|------|
| `동국대_ship_*.xlsx` | 센서 로그 (ds_timeindex, lat, lon, sog, oil_flow, gas_flow, co2 …) |
| `동국대_ship_info_*.xlsx` | `Schedule` 시트: Voyage No, Ballast/Laden, Start/End Time |

### 4. DB 구축

```bash
python scripts/load_hodata.py
```

- `data/maritime.db` 생성
- 항차 ID: `H2521_V21_Ballast` 형식 (`ship_info` Schedule 날짜 기준)
- DB 확인: `python scripts/export_db_to_excel.py` → `data/maritime_db_export.xlsx`

### 5. 앱 실행

```bash
python app.py
```

브라우저: **http://127.0.0.1:7860**

---

## LLM Tool 7개

| 유형 | Tool | 설명 |
|------|------|------|
| 조회 | `get_current_voyage_status` | 현재 항차 KPI (위치, SOG, FOC/FGC, 배출, CII YTD) |
| 조회 | `get_voyage_analysis` | `period`: current / previous / ytd |
| 계산 | `calculate_cii_rating` | 연간 CII 등급 (DWT 필요) |
| 계산 | `calculate_emissions` | CO₂ / CH₄ / CO₂e 상세 |
| 생성 | `generate_noon_report` | Noon Report `.docx` |
| 생성 | `generate_mrv_voyage_report` | MRV Voyage `.docx` |
| 생성 | `generate_mrv_annual_report` | MRV Annual `.docx` |

정의 위치: `agent/tools.py` 하단 `TOOLS_SPEC`, `TOOL_MAP`, `dispatch_tool()`

---

## CII 등급 계산 — **수정해야 할 위치** ★

책임님께 받을 **공식/계수**는 아래 파일·함수를 우선 수정하세요.

### ① 계수·상수 (가장 먼저)

**파일:** `config.py`

```python
CII_PARAMS = {
    "a": 1984.79,           # Required CII = a × DWT^c × (1 - reduction)
    "c": -0.489,
    "d_factors": {"d1": 0.84, "d2": 0.95, "d3": 1.06, "d4": 1.14},  # A~E 경계
    "reduction": {2023: 0.05, 2024: 0.07, 2025: 0.09, 2026: 0.11},
}
VESSEL["dwt"]  # IMO 등급 산출에 필수 (현재 0 → 등급 불가, kg/nm만 표시)
```

선종이 Container Ship이 아니면 `a`, `c` 값도 IMO MEPC 기준에 맞게 변경.

### ② IMO CII 등급 로직 (핵심)

**파일:** `agent/tools.py`

| 함수 | 역할 |
|------|------|
| `_calc_cii_ref(dwt, year)` | **Required CII** (요구 탄소강도, g/t·nm) |
| `_cii_rating(attained, required)` | Attained vs Required 비율 → **A~E 등급** |
| `_ytd_cii_summary(year)` | YTD CO₂·거리로 Attained 산출 + 등급 |
| `calculate_cii_rating(year)` | 위 로직을 Tool로 노출 (LLM 호출용) |

**현재 Attained CII 공식 (연간 YTD):**

```
attained = (total_CO2_mt × 10⁶) / (DWT × total_distance_nm)   # g/t·nm
required = a × DWT^c × (1 - reduction[year])
등급     = attained / required 를 d1~d4 구간과 비교
```

**센서 기반 단순 강도 (DWT 불필요):**

```
sensor_cii_kg_per_nm = (total_CO2_mt × 1000) / total_distance_nm
```

### ③ 항차 단위 CII (브리핑 KPI)

**파일:** `agent/data_store.py` → `voyage_stats()`

```python
cii_val = co2_mt * 1000 / dist_nm   # kg CO₂/nm (해당 항차)
```

거리 `dist_nm`은 `_compute_distance_range()`에서 산정 (lon=0 많으면 **SOG 적분** 우선).

### ④ 답변 문구만 (계산식 변경 없을 때)

**파일:** `agent/briefing.py` → `_cii_text()`, `format_cii()`

### ⑤ Word 보고서 표기

**파일:** `agent/reports.py` → Noon Report의 `CII (kg CO2/nm)` 행

---

## 데이터 한계 (알아둘 것)

| 항목 | 상태 |
|------|------|
| 항만명 | 원본 없음 → `Unknown` |
| Loading | `ship_info` Schedule의 Ballast/Laden 사용 |
| M/E RPM | 원본 컬럼 없음 |
| 경도 lon=0 | 다수 구간 → 지도·좌표 거리 부정확, **SOG 적분으로 거리 보정** |
| DWT / GT | 원본 없음 → **IMO CII 등급(A~E) 산출 불가** |
| H2521 | 프로젝트 내부 선박 코드 (실 IMO 아님) |

---

## 시점 기준 정의

| 질문 표현 | 코드 기준 |
|-----------|-----------|
| 현재 | `voyages` 테이블 최신 항차 (Schedule 구간) |
| 이전 | `previous_voyage()` — 직전 Schedule 구간 |
| 올해 | `ytd_summary(연도)` — 1/1 ~ `config.CURRENT_DATE` |

`CURRENT_DATE`, `CURRENT_VOYAGE_ID`는 `load_hodata.py` 실행 시 DB 최신 시각 기준으로 갱신됩니다.

---

## 환경 변수 (선택)

| 변수 | 기본값 |
|------|--------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` |
| `MODEL_NAME` | `llama3.1:8b` |

---

## 인수인계 체크리스트

- [ ] `ho_data/`에 Excel 2종 복사
- [ ] `python scripts/load_hodata.py` 로 DB 생성
- [ ] `ollama serve` 실행 후 `python app.py`
- [ ] 책임님 CII 공식 수령 → `config.py` + `agent/tools.py` 수정
- [ ] 실선 DWT/GT 확보 시 `config.py` `VESSEL` 및 DB `vessel` 테이블 반영
- [ ] 필요 시 `export_db_to_excel.py`로 DB 내용 공유

---

## 문의·이슈

버그·개선은 GitHub Issues 또는 연구실 내부 채널로 공유해 주세요.
