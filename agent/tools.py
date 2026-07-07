"""
Maritime Ops Agent - Tool 정의
LLM이 호출하는 7개 도구 + 지도 렌더링
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VESSEL, CII_PARAMS, CURRENT_DATE, CURRENT_VOYAGE_ID, REPORTS_DIR

from agent.data_store import get_store
from agent.reports import (
    generate_noon_report_docx,
    generate_mrv_voyage_docx,
    generate_mrv_annual_docx,
)


# ── CII 계산 헬퍼 ─────────────────────────────────────────────────────────────
def _calc_cii_ref(dwt: float, year: int) -> float:
    a = CII_PARAMS["a"]
    c = CII_PARAMS["c"]
    reduction = CII_PARAMS["reduction"].get(year, 0.07)
    return a * (dwt ** c) * (1 - reduction)


def _cii_rating(attained: float, required: float) -> str:
    d = CII_PARAMS["d_factors"]
    if attained <= required * d["d1"]:   return "A"
    elif attained <= required * d["d2"]: return "B"
    elif attained <= required * d["d3"]: return "C"
    elif attained <= required * d["d4"]: return "D"
    else:                                return "E"


def _get_vessel_dwt() -> float:
    try:
        vessel = get_store().get_vessel()
        dwt = float(vessel.get("dwt", 0) or 0)
        if dwt > 0:
            return dwt
    except Exception:
        pass
    return float(VESSEL.get("dwt", 0) or 0)


def _ytd_cii_summary(year: int) -> dict:
    store = get_store()
    ytd   = store.ytd_summary(year)
    dwt   = _get_vessel_dwt()

    base = {"based_on_period": f"{year}-01-01 ~ {CURRENT_DATE}"}

    if not ytd or ytd.get("total_distance_nm", 0) == 0:
        return {**base, "rating": None, "note": f"{year}년 운항 데이터 없음"}

    dist    = ytd["total_distance_nm"]
    co2_mt  = ytd["total_co2_mt"]
    sensor_cii = round(co2_mt * 1000 / dist, 2) if dist > 0 else 0

    result = {**base, "sensor_cii_kg_per_nm": sensor_cii}

    if dwt > 0:
        attained = (co2_mt * 1e6) / (dwt * dist)
        required = _calc_cii_ref(dwt, year)
        result.update({
            "attained_g_per_dwt_nm": round(attained, 4),
            "required_g_per_dwt_nm": round(required, 2),
            "rating": _cii_rating(attained, required),
        })
    else:
        result["note"] = "DWT 없어 IMO CII 등급 산출 불가 — 센서 기반 kg/nm 제공"

    return result


# ── Tool 1: 현재 운항 상태 ──────────────────────────────────────────────────────
def get_current_voyage_status() -> dict:
    """현재 항차 KPI 전체 (위경도·SOG·FOC·FGC·CO2·CH4·CO2e·CII)"""
    store  = get_store()
    voyage = store.current_voyage()
    vessel = store.get_vessel()

    if not voyage:
        return {"error": "운항 데이터 없음"}

    vid   = voyage.get("voyage_id", CURRENT_VOYAGE_ID)
    stats = store.voyage_stats(vid)

    year = int(str(voyage.get("end_time", CURRENT_DATE))[:4])

    return {
        "ship_name":         vessel.get("name", VESSEL["name"]),
        "ship_imo":          vessel.get("imo",  VESSEL["imo"]),
        "current_voyage_id": vid,
        "reference_period":  f"{str(voyage.get('start_time', ''))[:16]} ~ {str(voyage.get('end_time', ''))[:16]} (현재 항차)",
        "departure_port":    voyage.get("departure_port", "Unknown"),
        "arrival_port":      voyage.get("arrival_port",   "Unknown"),
        "voyage_start":      str(voyage.get("start_time", ""))[:16],
        "voyage_end":        str(voyage.get("end_time",   ""))[:16],
        "days_at_sea":       stats.get("days_at_sea", 0),
        "distance_nm":       stats.get("distance_nm", 0),
        "distance_method":   stats.get("distance_method", ""),
        "distance_note":     stats.get("distance_note", ""),
        "coord_distance_nm": stats.get("coord_distance_nm"),
        "position": {
            "latitude":  stats.get("last_lat", 0),
            "longitude": stats.get("last_lon", 0),
            "note": "경도(lon) 원본 미제공 구간 있음 — 위도·SOG는 실측",
        },
        "sog_kts":            stats.get("last_sog", 0) or stats.get("avg_sog", 0),
        "avg_sog_kts":        stats.get("avg_sog", 0),
        "me_power_kw":        stats.get("last_me_power", 0),
        "me_rpm":             None,
        "me_rpm_note":        "미측정 (원본 데이터에 RPM 컬럼 없음)",
        "loading_status":     voyage.get("condition") or "미제공 (원본 데이터에 Loading 컬럼 없음)",
        # 최신 순간 연료/배출 (kg/h → MT/h)
        "foc_oil_rate_mt_h":  round(float(stats.get("last_oil_rate", 0)) / 1000, 4),
        "fgc_gas_rate_mt_h":  round(float(stats.get("last_gas_rate", 0)) / 1000, 4),
        "co2_rate_mt_h":      round(float(stats.get("last_co2_rate", 0)) / 1000, 4),
        # 항차 누계 (질문 '현재 운항 상태'의 핵심)
        "voyage_foc_oil_mt":  stats.get("foc_oil_mt", 0),
        "voyage_fgc_gas_mt":  stats.get("fgc_gas_mt", 0),
        "voyage_co2_mt":      stats.get("co2_mt",     0),
        "voyage_ch4_mt":      stats.get("ch4_mt",     0),
        "voyage_co2e_mt":     stats.get("co2e_mt",    0),
        "voyage_cii_kg_per_nm": stats.get("cii_value", 0),
        "cii_ytd":            _ytd_cii_summary(year),
        "last_reading_time":  stats.get("last_ts", ""),
        "data_source":        "ho_data (sensor)",
        "units": {
            "sog": "knots", "foc_rate": "MT/h", "fgc_rate": "MT/h",
            "co2_rate": "MT/h", "voyage_fuel": "MT", "voyage_emission": "MT",
        },
    }


# ── Tool 2: 항차 분석 ───────────────────────────────────────────────────────────
def get_voyage_analysis(voyage_id: str = "", period: str = "current") -> dict:
    """특정 항차 또는 현재/이전/올해 기간의 운항 KPI 집계"""
    store = get_store()

    if voyage_id:
        voyage = store.get_voyage(voyage_id)
    elif period == "previous":
        voyage = store.previous_voyage()
    elif period == "ytd":
        year = int(CURRENT_DATE[:4])
        ytd  = store.ytd_summary(year)
        return {
            "period":   f"{year} YTD (1/1 ~ 현재)",
            "summary":  ytd,
            "cii":      _ytd_cii_summary(year),
        }
    else:
        voyage = store.current_voyage()

    if not voyage:
        return {"error": "항차 데이터 없음"}

    vid   = voyage.get("voyage_id", "")
    stats = store.voyage_stats(vid)
    days  = max(stats.get("days_at_sea", 1), 1)
    dist  = max(stats.get("distance_nm", 1), 1)

    return {
        "voyage_id":       vid,
        "departure_port":  voyage.get("departure_port", "Unknown"),
        "arrival_port":    voyage.get("arrival_port",   "Unknown"),
        "voyage_start":    str(voyage.get("start_time", ""))[:16],
        "voyage_end":      str(voyage.get("end_time",   ""))[:16],
        "days_at_sea":     days,
        "distance_nm":     stats.get("distance_nm", 0),
        "avg_sog_kts":     stats.get("avg_sog",     0),
        "foc_oil_mt":      stats.get("foc_oil_mt",  0),
        "fgc_gas_mt":      stats.get("fgc_gas_mt",  0),
        "foc_per_day_mt":  round((stats.get("foc_oil_mt", 0) + stats.get("fgc_gas_mt", 0)) / days, 2),
        "co2_mt":          stats.get("co2_mt",  0),
        "ch4_mt":          stats.get("ch4_mt",  0),
        "co2e_mt":         stats.get("co2e_mt", 0),
        "cii_kg_per_nm":   stats.get("cii_value", 0),
        "co2_per_nm":      round(stats.get("co2_mt", 0) / dist, 4),
        "distance_method": stats.get("distance_method", ""),
        "distance_note":   stats.get("distance_note", ""),
        "loading_status":  voyage.get("condition") or "미제공",
        "me_rpm_note":     "미측정 (원본 데이터에 RPM 컬럼 없음)",
        "data_source":     "ho_data (sensor)",
    }


# ── Tool 3: CII 등급 계산 ───────────────────────────────────────────────────────
def calculate_cii_rating(year: int = 2024) -> dict:
    """연간 CII 계산 (센서 기반 kg/nm + IMO DWT기반 등급)"""
    store = get_store()
    ytd   = store.ytd_summary(year)

    if not ytd or ytd.get("total_distance_nm", 0) == 0:
        return {"error": f"{year}년 데이터 없음"}

    dist     = ytd["total_distance_nm"]
    co2_mt   = ytd["total_co2_mt"]
    co2e_mt  = ytd["total_co2e_mt"]
    dwt      = _get_vessel_dwt()

    sensor_cii = round(co2_mt * 1000 / dist, 4) if dist > 0 else 0

    result = {
        "year":                  year,
        "total_co2_mt":          co2_mt,
        "total_co2e_mt":         co2e_mt,
        "total_distance_nm":     dist,
        "voyages_included":      ytd["voyages_count"],
        "sensor_cii_kg_per_nm":  sensor_cii,
    }

    if dwt > 0:
        attained = (co2_mt * 1e6) / (dwt * dist)
        required = _calc_cii_ref(dwt, year)
        result.update({
            "attained_cii_g_per_dwt_nm": round(attained, 4),
            "required_cii_g_per_dwt_nm": round(required, 4),
            "rating":                    _cii_rating(attained, required),
            "calculation_basis":         "IMO MEPC.354(78)",
        })
    else:
        result["note"] = "DWT 없어 IMO CII 등급 불가 — 센서 기반 kg/nm 제공"

    return result


# ── Tool 4: 배출량 계산 ─────────────────────────────────────────────────────────
def calculate_emissions(voyage_id: str = "", period: str = "current") -> dict:
    """항차 또는 기간별 배출량 (센서 실측 CO2/CH4/CO2e)"""
    store = get_store()

    if voyage_id:
        voyage = store.get_voyage(voyage_id)
    elif period == "ytd":
        year = int(CURRENT_DATE[:4])
        ytd  = store.ytd_summary(year)
        return {
            "period":         f"{year} YTD",
            "co2_mt":         ytd.get("total_co2_mt",  0),
            "ch4_mt":         ytd.get("total_ch4_mt",  0),
            "co2e_mt":        ytd.get("total_co2e_mt", 0),
            "foc_oil_mt":     ytd.get("total_foc_oil_mt", 0),
            "fgc_gas_mt":     ytd.get("total_fgc_gas_mt", 0),
            "data_source":    "sensor (ME+GE+AB+GCU)",
        }
    elif period == "previous":
        voyage = store.previous_voyage()
    else:
        voyage = store.current_voyage()

    if not voyage:
        return {"error": "데이터 없음"}

    vid   = voyage.get("voyage_id", "")
    stats = store.voyage_stats(vid)

    return {
        "voyage_id":   vid,
        "co2_mt":      stats.get("co2_mt",     0),
        "ch4_mt":      stats.get("ch4_mt",     0),
        "co2e_mt":     stats.get("co2e_mt",    0),
        "foc_oil_mt":  stats.get("foc_oil_mt", 0),
        "fgc_gas_mt":  stats.get("fgc_gas_mt", 0),
        "data_source": "sensor (ME+GE+AB+GCU 합산)",
        "note":        "실측 센서 기반 — ME, GE, 보조보일러, GCU 포함한 선박 전체 배출량",
    }


# ── Tool 5: Noon Report 생성 ────────────────────────────────────────────────────
def generate_noon_report(report_date: str = "") -> dict:
    """최신 또는 지정 날짜의 Noon Report Word 파일 생성"""
    store  = get_store()
    noon   = store.get_noon_by_date(report_date) if report_date else store.latest_noon()
    voyage = store.current_voyage()
    vessel = store.get_vessel()

    if not noon:
        return {"error": "Noon Report 데이터 없음"}

    path = generate_noon_report_docx(noon, voyage, vessel)
    return {
        "status":      "생성 완료",
        "file_path":   str(path),
        "report_date": str(noon.get("report_datetime", ""))[:10],
        "position":    f"{noon.get('lat', 0):.4f}N, {noon.get('lon', 0):.4f}E",
        "foc_oil_mt":  noon.get("foc_oil_mt", 0),
        "fgc_gas_mt":  noon.get("fgc_gas_mt", 0),
        "co2_mt":      noon.get("co2_mt",     0),
        "data_source": "sensor",
    }


# ── Tool 6: MRV Voyage Report 생성 ─────────────────────────────────────────────
def generate_mrv_voyage_report(voyage_id: str = "") -> dict:
    """항차 MRV Report Word 파일 생성"""
    store  = get_store()
    voyage = store.get_voyage(voyage_id) if voyage_id else store.previous_voyage()
    vessel = store.get_vessel()

    if not voyage:
        return {"error": "항차 데이터 없음"}

    vid   = voyage.get("voyage_id", "")
    stats = store.voyage_stats(vid)

    # reports.py 가 사용하는 키 형태로 병합
    voyage_dict = {**voyage, **stats,
                   "departure_date": str(voyage.get("start_time", ""))[:10],
                   "arrival_date":   str(voyage.get("end_time",   ""))[:10]}

    path = generate_mrv_voyage_docx(voyage_dict, vessel)
    return {
        "status":      "생성 완료",
        "file_path":   str(path),
        "voyage_id":   vid,
        "route":       f"{voyage.get('departure_port')} → {voyage.get('arrival_port')}",
        "co2_mt":      stats.get("co2_mt", 0),
        "data_source": "ho_data (sensor)",
    }


# ── Tool 7: MRV Annual Report 생성 ─────────────────────────────────────────────
def generate_mrv_annual_report(year: int = 2024) -> dict:
    """연간 MRV Report Word 파일 생성"""
    store  = get_store()
    annual = store.annual_summary(year)
    vessel = store.get_vessel()

    if not annual:
        return {"error": f"{year}년 데이터 없음"}

    voyages_df = store.annual_voyages(year)

    path = generate_mrv_annual_docx(annual, voyages_df, vessel, year)
    return {
        "status":       "생성 완료",
        "file_path":    str(path),
        "year":         year,
        "voyages":      annual.get("voyages_count", 0),
        "total_co2_mt": annual.get("total_co2_mt", 0),
        "data_source":  "ho_data (sensor)",
    }


# ── 항차 경로 지도 렌더링 ───────────────────────────────────────────────────────
def render_voyage_map(voyage_id: str = "") -> str:
    try:
        import folium
        store = get_store()
        track = store.voyage_track(voyage_id) if voyage_id else store.current_track()

        if track.empty:
            return "<p>경로 데이터 없음</p>"

        center_lat = float(track["lat"].mean())
        center_lon = float(track["lon"].mean())
        m = folium.Map(location=[center_lat, center_lon], zoom_start=4)

        coords = list(zip(track["lat"].astype(float), track["lon"].astype(float)))
        folium.PolyLine(coords, color="#1E88E5", weight=2.5, opacity=0.8).add_to(m)

        if coords:
            folium.Marker(coords[0],  popup="출발", icon=folium.Icon(color="green")).add_to(m)
            folium.Marker(coords[-1], popup="최신위치", icon=folium.Icon(color="red")).add_to(m)

        return m._repr_html_()
    except Exception as e:
        return f"<p>지도 오류: {e}</p>"


# ── Tool 스펙 (LLM 함수 스키마) ────────────────────────────────────────────────
TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_current_voyage_status",
            "description": "현재 운항 상태 조회. 위경도·SOG·FOC·FGC·CO2·CH4·CO2e·CII 등 전체 KPI 반환.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_voyage_analysis",
            "description": "특정 항차 또는 기간(current/previous/ytd) 운항 데이터 집계 분석.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voyage_id": {"type": "string", "description": "항차 ID (예: H2521_V043). 비워두면 period 사용."},
                    "period":    {"type": "string", "enum": ["current", "previous", "ytd"],
                                  "description": "current=현재항차, previous=이전항차, ytd=올해누계"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_cii_rating",
            "description": "연간 CII(탄소집약도) 계산. 센서 기반 kg CO2/nm 및 DWT 있으면 IMO 등급 산출.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "계산 연도 (예: 2024, 2025, 2026)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_emissions",
            "description": "항차 또는 기간의 배출량 조회 (CO2·CH4·CO2e). 센서 실측값 기반.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voyage_id": {"type": "string", "description": "항차 ID"},
                    "period":    {"type": "string", "enum": ["current", "previous", "ytd"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_noon_report",
            "description": "Noon Report Word 파일 생성. 최신 또는 지정 날짜 기준.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_date": {"type": "string", "description": "날짜 (YYYY-MM-DD). 비우면 최신."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_mrv_voyage_report",
            "description": "MRV Voyage Report Word 파일 생성. 지정 항차 또는 최근 완료 항차.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voyage_id": {"type": "string", "description": "항차 ID"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_mrv_annual_report",
            "description": "MRV Annual Report Word 파일 생성. 지정 연도의 전체 항차 집계.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "연도 (예: 2024, 2025)"},
                },
                "required": [],
            },
        },
    },
]

TOOL_MAP = {
    "get_current_voyage_status":  get_current_voyage_status,
    "get_voyage_analysis":        get_voyage_analysis,
    "calculate_cii_rating":       calculate_cii_rating,
    "calculate_emissions":        calculate_emissions,
    "generate_noon_report":       generate_noon_report,
    "generate_mrv_voyage_report": generate_mrv_voyage_report,
    "generate_mrv_annual_report": generate_mrv_annual_report,
}

# maritime_agent.py 호환 alias
TOOL_SCHEMAS = TOOLS_SPEC


def dispatch_tool(fn_name: str, fn_args: dict) -> str:
    import json
    fn = TOOL_MAP.get(fn_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {fn_name}"})
    try:
        result = fn(**fn_args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
