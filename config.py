import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports" / "output"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Ollama (로컬 LLM) - llama3.1:8b (Meta, Ollama tool calling 지원)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = "ollama"
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")

# 선박 기본 정보 (ho_data 기반 실제 선박: h2521)
VESSEL = {
    "name": "H2521",
    "imo": "H2521",
    "mmsi": "Unknown",
    "type": "Container Ship",
    "flag": "Unknown",
    "gt": 0,
    "dwt": 0,
    "loa_m": 0.0,
    "beam_m": 0.0,
    "draft_design_m": 0.0,
    "me_model": "Unknown",
    "me_mcr_kw": 10_703,   # ho_data 실측 최대값 기반
    "me_mcr_rpm": 0,
    "service_speed_kts": 18.0,
    "service_rpm": 0,
    "foc_service_mt_day": 0.0,
    "displacement_laden_mt": 0,
    "displacement_ballast_mt": 0,
    "cargo_capacity_teu": 0,
}

# CII 계산 파라미터 (IMO MEPC.354(78), Container Ship)
CII_PARAMS = {
    "a": 1984.79,
    "c": -0.489,
    "d_factors": {"d1": 0.84, "d2": 0.95, "d3": 1.06, "d4": 1.14},
    "reduction": {2023: 0.05, 2024: 0.07, 2025: 0.09, 2026: 0.11},
}

# 연료별 CO2 배출계수 (t CO2 / t fuel)
EMISSION_FACTORS = {
    "HFO":  3.114,
    "VLSFO": 3.114,
    "MGO":  3.206,
    "LSMGO": 3.206,
    "LNG":  2.750,
    "CH4_slip_factor": 0.036,   # LNG slip (GWP 21)
}

# 현재 기준 날짜 및 항차 (ho_data / sensor_log 마지막 데이터 기준)
CURRENT_DATE = "2026-06-28"
CURRENT_VOYAGE_ID = "H2521_V21_Ballast"
