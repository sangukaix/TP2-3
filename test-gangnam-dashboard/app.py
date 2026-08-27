"""강남구 관광 진단 시연용 Streamlit 대시보드.

원본 ZIP은 수정하지 않고 실행 시 읽기만 한다. 이 화면의 ML 결과는 12개월
표본으로 만든 시연용 결과이므로, 정책 판단이나 실제 성과 예측에 사용하면 안 된다.
"""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error


APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")
DATA_SOURCE_DIR = Path(os.getenv("DATA_SOURCE_DIR", ""))
GANGNAM_LAT, GANGNAM_LON = 37.5172, 127.0473


def decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 읽지 못했습니다.")


@st.cache_data(show_spinner=False)
def zip_csvs(folder: str) -> dict[str, pd.DataFrame]:
    """지정 폴더의 ZIP 내부 CSV를 파일명 기준으로 읽는다."""
    result: dict[str, pd.DataFrame] = {}
    for path in Path(folder).glob("강남구*.zip"):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                rows = list(csv.reader(io.StringIO(decode_csv(archive.read(name)))))
                if len(rows) < 2:
                    continue
                header = [cell.strip() or f"unnamed_{i}" for i, cell in enumerate(rows[0])]
                result[name] = pd.DataFrame(rows[1:], columns=header)
    return result


def find_table(tables: dict[str, pd.DataFrame], include: str) -> pd.DataFrame:
    for name, table in tables.items():
        if include in name:
            return table.copy()
    raise KeyError(f"'{include}' 자료를 찾지 못했습니다.")


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def month_index(frame: pd.DataFrame, month_col: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["year_month"] = frame[month_col].astype(str).str.extract(r"(20\d{4})", expand=False)
    frame = frame.dropna(subset=["year_month"]).sort_values("year_month")
    frame["month_label"] = pd.to_datetime(frame["year_month"], format="%Y%m").dt.strftime("%Y-%m")
    return frame


def first_column(frame: pd.DataFrame, text: str) -> str:
    return next(column for column in frame.columns if text in column)


def month_column(frame: pd.DataFrame) -> str:
    return next(column for column in frame.columns if "기준" in column and "월" in column)


def monthly_metrics(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    visitors = find_table(tables, "방문자 수(연인원) 추이")
    visitors = month_index(visitors, month_column(visitors))
    visitors = visitors[["year_month", "month_label", "방문자수", "방문자수증감률"]]
    visitors["visitors"] = to_number(visitors["방문자수"])
    visitors["visitor_growth"] = to_number(visitors["방문자수증감률"])

    spending = find_table(tables, "관광소비 추이_내국인")
    spending = month_index(spending, month_column(spending))
    spending = spending[spending["업종대분류명"].eq("전체")].copy()
    spending["spending_thousand_krw"] = to_number(spending["소비액(천원)"])
    spending = spending[["year_month", "spending_thousand_krw"]]

    nav = find_table(tables, "내비게이션 목적지 유형별 검색량")
    nav = month_index(nav, month_column(nav))
    nav = nav[nav["목적지 유형"].eq("전체")].copy()
    nav["navigation_searches"] = to_number(nav["목적지 검색량"])
    nav = nav[["year_month", "navigation_searches"]]

    stay = find_table(tables, "순 방문자 수 및 숙박 비율")
    stay = month_index(stay, month_column(stay))
    stay["stay_rate"] = to_number(stay["숙박자 비율"])
    stay = stay[["year_month", "stay_rate"]]

    nights = find_table(tables, "평균 숙박일")
    nights = month_index(nights, month_column(nights))
    nights["average_nights"] = to_number(nights["평균 숙박일수"])
    nights = nights[["year_month", "average_nights"]]

    social = find_table(tables, "SNS 언급량")
    social = month_index(social, month_column(social))
    social["social_mentions"] = to_number(social["검색량(건)"])
    social = social[["year_month", "social_mentions"]]

    merged = visitors.merge(spending, on="year_month", how="inner")
    merged = merged.merge(nav, on="year_month", how="left")
    merged = merged.merge(stay, on="year_month", how="left")
    merged = merged.merge(nights, on="year_month", how="left")
    merged = merged.merge(social, on="year_month", how="left")
    merged["spending_per_visit_krw"] = merged["spending_thousand_krw"] * 1000 / merged["visitors"]
    return merged.sort_values("year_month").reset_index(drop=True)


def model_demo(metrics: pd.DataFrame, target_column: str) -> dict[str, float | str | None]:
    """시연용 시간순 분리: 최근 3개월을 test로 둔다."""
    work = metrics[["year_month", target_column]].rename(columns={target_column: "target"}).copy()
    work["lag_1"] = work["target"].shift(1)
    work["month"] = pd.to_datetime(work["year_month"], format="%Y%m").dt.month
    work["month_sin"] = np.sin(2 * np.pi * work["month"] / 12)
    work["month_cos"] = np.cos(2 * np.pi * work["month"] / 12)
    work = work.dropna().reset_index(drop=True)
    if len(work) < 7:
        return {"message": "학습 가능한 월 수가 부족합니다."}

    test_size = min(3, max(2, len(work) // 3))
    train, test = work.iloc[:-test_size], work.iloc[-test_size:]
    features = ["lag_1", "month_sin", "month_cos"]
    baseline = test["lag_1"].to_numpy()
    linear = LinearRegression().fit(train[features], train["target"])
    forest = RandomForestRegressor(n_estimators=100, min_samples_leaf=2, random_state=42).fit(
        train[features], train["target"]
    )
    candidates = {
        "직전 월 기준선": mean_absolute_error(test["target"], baseline),
        "선형회귀": mean_absolute_error(test["target"], linear.predict(test[features])),
        "랜덤포레스트": mean_absolute_error(test["target"], forest.predict(test[features])),
    }
    selected_name = min(candidates, key=candidates.get)
    selected = {"선형회귀": linear, "랜덤포레스트": forest}.get(selected_name)
    latest = work.iloc[-1]
    next_month = (pd.to_datetime(latest["year_month"], format="%Y%m") + pd.offsets.MonthBegin(1))
    next_features = pd.DataFrame(
        [{
            "lag_1": latest["target"],
            "month_sin": np.sin(2 * np.pi * next_month.month / 12),
            "month_cos": np.cos(2 * np.pi * next_month.month / 12),
        }]
    )
    forecast = latest["target"] if selected is None else float(selected.predict(next_features)[0])
    return {
        "message": "최근 3개월을 테스트로 둔 시연용 시간순 비교 결과입니다.",
        "selected_name": selected_name,
        "baseline_mae": candidates["직전 월 기준선"],
        "selected_mae": candidates[selected_name],
        "forecast": max(0, forecast),
        "target_month": next_month.strftime("%Y-%m"),
        "train_rows": len(train),
        "test_rows": len(test),
    }


def latest_value(metrics: pd.DataFrame, column: str) -> float:
    return float(metrics.iloc[-1][column])


def generate_report(metrics: pd.DataFrame, visitor_model: dict, spending_model: dict, business: str, goal: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 비어 있습니다. .env 파일에 키를 입력해 주세요.")
    from openai import APIConnectionError, AuthenticationError, OpenAI

    latest = metrics.iloc[-1]
    snapshot = {
        "region": "서울특별시 강남구",
        "data_period": f"{metrics.iloc[0]['month_label']} ~ {latest['month_label']}",
        "latest_visitors_person_visits": round(latest["visitors"]),
        "latest_tourism_spending_krw": round(latest["spending_thousand_krw"] * 1000),
        "latest_navigation_searches": round(latest["navigation_searches"]),
        "latest_stay_rate_percent": round(latest["stay_rate"], 2),
        "latest_average_nights": round(latest["average_nights"], 2),
        "latest_social_mentions": round(latest["social_mentions"]),
        "latest_spending_per_visit_krw_estimate": round(latest["spending_per_visit_krw"]),
        "demo_forecast": {
            "target_month": visitor_model.get("target_month"),
            "visitors_person_visits": round(visitor_model.get("forecast", 0)),
            "monthly_domestic_tourism_spending_krw": round(spending_model.get("forecast", 0) * 1000),
            "spending_per_visit_krw_estimate": round((spending_model.get("forecast", 0) * 1000) / max(visitor_model.get("forecast", 1), 1)),
            "visitor_model": visitor_model.get("selected_name"),
            "spending_model": spending_model.get("selected_name"),
            "note": "12개월 표본의 시연용 모델 결과이며 정책 판단용 예측이 아님",
        },
        "data_sources": [
            "한국관광 데이터랩 강남구 방문자 수(연인원) 추이, 2025-08~2026-07",
            "한국관광 데이터랩 강남구 관광소비 추이_내국인, 2025-08~2026-07",
            "한국관광 데이터랩 강남구 숙박체류시간·SNS·내비게이션 자료, 2025-08~2026-07",
        ],
    }
    prompt = f"""
당신은 대한민국 지자체 관광정책 보좌관이다. 아래는 공식 관광데이터랩에서 내려받은
강남구 관측 지표다. 데이터에 없는 사실이나 수치를 만들지 말고, 인과관계를 단정하지 마라.
웹 검색은 gangnam.go.kr, visitkorea.or.kr, datalab.visitkorea.or.kr 등 공식 출처만 사용한다.

관측 지표: {json.dumps(snapshot, ensure_ascii=False)}
사용자 업종: {business}
정책/사업 목표: {goal}

아래 순서의 한국어 Markdown 보고서를 작성하라. 숫자·기간·단위를 절대 생략하지 마라.
1. ## 의사결정 핵심 요약: 항목 | 최근 관측값 | 다음 달 참고 추정 | 해석·한계 | 근거 로 된 표
2. ## 데이터로 확인되는 관광 패턴: 관측 사실만 3개 이내로 요약
3. ## 우선 실행 전략: 우선순위 | 실행 항목 | 대상 | 측정 지표 | 데이터·공식 근거 로 된 표 3개
4. ## 확인이 필요한 가설과 한계: 근거가 부족한 교통·시설·관광지 문제는 가설로만 쓸 것
5. ## 근거 출처: 데이터랩 원본 자료명·기간과, 웹 검색으로 찾은 공식 출처 제목·URL을 표로 모두 제시
'데이터·공식 근거' 칸에는 반드시 데이터랩 자료명 또는 공식 URL을 넣어라. 공식 근거를 찾지 못한 전략은 그 사실을 명시하라.
'소비가 낮다', '교통이 문제다' 같은 문장은 근거가 없으면 가설이라고 명시하라.
"""
    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            tools=[{"type": "web_search", "filters": {"allowed_domains": ["gangnam.go.kr", "visitkorea.or.kr", "datalab.visitkorea.or.kr"]}}],
            input=prompt,
        )
    except AuthenticationError as exc:
        raise RuntimeError("OpenAI API 키 인증에 실패했습니다. .env의 OPENAI_API_KEY와 API 결제·권한 상태를 확인해 주세요.") from exc
    except APIConnectionError as exc:
        raise RuntimeError("OpenAI API 서버에 연결하지 못했습니다. 현재 Windows 방화벽·보안 프로그램 또는 학교/사내 네트워크가 Python의 외부 HTTPS 연결을 차단하고 있습니다. API 키 문제는 아닙니다.") from exc
    return response.output_text


def main() -> None:
    st.set_page_config(page_title="STAY-UP AI | 강남구 관광 진단", page_icon="🧭", layout="wide")
    st.markdown("""<style>
    .stApp {background: #f4f7fa; color: #26354a;}
    .block-container {padding: 0 2.3rem 2.5rem; max-width: 1460px;}
    header[data-testid="stHeader"] {background: transparent;}
    .top-nav {height: 76px; display:flex; align-items:center; justify-content:space-between;
      background:white; margin:0 -2.3rem 0; padding:0 2.3rem; border-bottom:1px solid #e6ebf2;}
    .brand {font-size:1.42rem; font-weight:800; color:#182d4d; letter-spacing:-.04em;}
    .brand span {color:#25a9cb;} .nav-label {font-size:.92rem; color:#526278; font-weight:600;}
    .hero {padding: 2.35rem 2rem 2.55rem; color: white; text-align:center;
      background: linear-gradient(110deg, #1d304f 0%, #263b61 58%, #1c3153 100%); margin:0 -2.3rem 1.45rem;}
    .hero h1 {margin: 0; font-size: 2.05rem; letter-spacing:-.05em;}
    .hero p {margin: .6rem 0 0; color:#dce7f5; font-size:1rem;}
    .panel-title {font-size:1.16rem; font-weight:800; color:#fff; padding:.83rem 1.1rem; margin:-1rem -1rem 1rem;
      background:linear-gradient(90deg,#31b8d6,#7385d9); border-radius:.68rem .68rem 0 0; text-align:center;}
    .map-title {font-size:1.12rem; font-weight:800; color:#1f3658; margin-bottom:.55rem;}
    .map-note {background:#edf8fb; color:#376177; border-radius:10px; padding:.7rem .85rem; font-size:.88rem; margin-top:.45rem;}
    .section-label {font-size:1.15rem; font-weight:800; color:#1e3659; margin:1.55rem 0 .7rem;}
    .warn {background:#fff7df; border-left:4px solid #e6a700; padding:.7rem 1rem; border-radius:8px;}
    [data-testid="stMetric"] {background:#f8fbfd; border:1px solid #e3ebf2; border-radius:10px; padding:.75rem;}
    [data-testid="stMetricLabel"] {font-size:.79rem; color:#53647b;}
    [data-testid="stMetricValue"] {font-size:1.35rem; color:#1b3456;}
    div[data-testid="stVerticalBlockBorderWrapper"] {background:#fff; border-color:#dbe5ef; box-shadow:0 3px 12px rgba(29,55,88,.06);}
    </style>""", unsafe_allow_html=True)
    st.markdown("""<div class="top-nav"><div class="brand">STAY-UP <span>AI</span> · 지역관광 진단</div>
    <div class="nav-label">관광 현황 &nbsp;&nbsp; 소비·체류 분석 &nbsp;&nbsp; AI 전략 보고서</div></div>
    <div class="hero"><h1>강남구 관광 현황 · 소비 · 체류를 한눈에</h1>
    <p>관광 담당자가 지역의 월별 변화와 실행 과제를 빠르게 확인하는 시연 대시보드입니다.</p></div>""", unsafe_allow_html=True)

    if not DATA_SOURCE_DIR.exists():
        st.error("데이터 폴더를 찾지 못했습니다. .env의 DATA_SOURCE_DIR을 확인해 주세요.")
        st.code("DATA_SOURCE_DIR=C:/Users/Admin/Desktop/새 폴더 (11)")
        return
    try:
        tables = zip_csvs(str(DATA_SOURCE_DIR))
        metrics = monthly_metrics(tables)
    except Exception as exc:
        st.exception(exc)
        return

    visitor_model = model_demo(metrics, "visitors")
    spending_model = model_demo(metrics, "spending_thousand_krw")
    latest = metrics.iloc[-1]
    dashboard_col, map_col = st.columns([1.08, 1], gap="large")
    with dashboard_col:
        with st.container(border=True):
            st.markdown('<div class="panel-title">강남구 월간 관광 핵심 현황</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.metric(
                "월간 방문자 수(연인원)", f"{latest['visitors'] / 10_000:,.0f}만 연인원", f"{latest['visitor_growth']:.1f}% 전년동월",
                help="연인원은 한 사람이 여러 번 방문하면 방문 횟수만큼 합산한 값입니다. 고유 인구 수가 아닙니다.",
            )
            c2.metric(
                "월간 내국인 관광소비 총액", f"{latest['spending_thousand_krw'] / 100_000:,.0f}억 원", latest["month_label"],
                help="해당 월에 강남구에서 발생한 내국인 관광소비의 합계입니다. 하루치나 1인당 금액이 아닙니다.",
            )
            c3, c4 = st.columns(2)
            c3.metric("월간 숙박 방문 비율", f"{latest['stay_rate']:.1f}%", help="해당 월 방문자 가운데 숙박한 방문자의 비율입니다.")
            c4.metric("월간 평균 숙박일수", f"{latest['average_nights']:.2f}일", help="해당 월 숙박 방문자의 평균 숙박일수입니다.")
            st.caption("모든 수치는 2026-07 월간 기준입니다. 연인원은 중복 방문을 포함하며, 관광소비액은 내국인 관광소비 총액입니다.")
        trend = metrics[["month_label", "visitors", "navigation_searches", "social_mentions"]].rename(
            columns={
                "month_label": "기준월",
                "visitors": "방문자 수(연인원)",
                "navigation_searches": "내비게이션 검색량",
                "social_mentions": "SNS 언급량",
            }
        )
        trend = trend.melt("기준월", var_name="지표", value_name="값")
        st.plotly_chart(
            px.line(trend, x="기준월", y="값", color="지표", markers=True, title="월별 방문·관심도 추이", labels={"값": "건수·연인원"}),
            use_container_width=True,
        )
    with map_col:
        with st.container(border=True):
            st.markdown('<div class="map-title">선택 지역 · 서울특별시 강남구</div>', unsafe_allow_html=True)
            st.selectbox("분석 지역", ["서울특별시 강남구"], label_visibility="collapsed")
            map_data = pd.DataFrame([{"lat": GANGNAM_LAT, "lon": GANGNAM_LON}])
            st.pydeck_chart(
                pdk.Deck(
                    initial_view_state=pdk.ViewState(latitude=GANGNAM_LAT, longitude=GANGNAM_LON, zoom=10.8, pitch=0),
                    layers=[pdk.Layer("ScatterplotLayer", data=map_data, get_position="[lon, lat]", get_radius=1200, get_fill_color=[40, 160, 190, 190], pickable=True)],
                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                    tooltip={"text": "강남구 관광 진단 지역"},
                ),
                height=505,
            )
            st.markdown('<div class="map-note">분석 기간 · 2025-08 ~ 2026-07<br>현재는 강남구 시연 데이터만 제공합니다.</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-label">관광소비 및 방문 패턴</div>', unsafe_allow_html=True)
    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        with st.container(border=True):
            spend = metrics[["month_label", "spending_thousand_krw", "spending_per_visit_krw"]].rename(
                columns={
                    "month_label": "기준월",
                    "spending_thousand_krw": "월간 내국인 관광소비액(천원)",
                    "spending_per_visit_krw": "방문 1회당 추정 소비액(원)",
                }
            )
            spend = spend.melt("기준월", var_name="지표", value_name="값")
            st.plotly_chart(
                px.bar(spend, x="기준월", y="값", color="지표", barmode="group", title="월별 관광소비 추이", labels={"값": "원본 단위 값"}),
                use_container_width=True,
            )
            st.caption("그래프의 두 소비 지표는 단위가 다릅니다. 총액은 천 원, 방문 1회당 추정 소비액은 원 단위입니다.")
    with chart_right:
        with st.container(border=True):
            st.markdown("#### 관광 담당자 확인 포인트")
            st.write("방문·관심도와 소비·체류가 같은 방향으로 움직이는지 확인한 뒤, AI 보고서에서 우선 대응 과제를 검토합니다.")
            st.metric("내비게이션 검색량", f"{latest['navigation_searches']:,.0f}건", latest["month_label"])
            st.metric("SNS 언급량", f"{latest['social_mentions']:,.0f}건", latest["month_label"])
            st.metric("방문 1회당 추정 소비액", f"₩{latest['spending_per_visit_krw']:,.0f}")

    st.subheader("체류·소비·관심도 진단")
    d1, d2, d3 = st.columns(3)
    d1.info(f"**체류**\n\n숙박 비율 {latest['stay_rate']:.1f}% · 평균 {latest['average_nights']:.2f}박\n\n당일형/숙박형 관광 비중을 다음 기간과 비교해 확인합니다.")
    d2.info(f"**소비**\n\n방문 1회당 내국인 관광소비 추정액 ₩{latest['spending_per_visit_krw']:,.0f}\n\n월간 내국인 관광소비액을 방문자 연인원으로 나눈 참고 지표입니다. 개인별 실제 소비액은 아닙니다.")
    d3.info(f"**관심도**\n\n내비게이션 검색 {latest['navigation_searches']:,.0f}건\nSNS 언급 {latest['social_mentions']:,.0f}건\n\n관심 신호이지 실제 방문객 수와 동일하지 않습니다.")

    st.subheader("시연용 다음 달 관광수요·소비 추정")
    st.markdown('<div class="warn">12개월 표본으로 만든 교육·시연용 ML 결과입니다. 실제 정책 판단이나 성능 주장에는 사용할 수 없습니다. 3년 이상 자료 확보 후 정식 검증이 필요합니다.</div>', unsafe_allow_html=True)
    if "forecast" in visitor_model and "forecast" in spending_model:
        forecast_per_visit = spending_model["forecast"] * 1000 / max(visitor_model["forecast"], 1)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"{visitor_model['target_month']} 방문객 참고 추정", f"{visitor_model['forecast'] / 10_000:,.0f}만 연인원")
        m2.metric(f"{spending_model['target_month']} 관광소비 참고 추정", f"{spending_model['forecast'] / 100_000:,.0f}억 원")
        m3.metric("방문 1회당 예상 소비", f"₩{forecast_per_visit:,.0f}")
        m4.metric("예측 방식", f"방문: {visitor_model['selected_name']}", f"소비: {spending_model['selected_name']}")
        st.caption(f"방문·소비를 각각 독립적으로 시간순 비교했습니다. 학습 {visitor_model['train_rows']}개월 / 테스트 {visitor_model['test_rows']}개월이며, 입력은 직전 월 값과 월 계절성입니다.")

    st.subheader("AI 관광 전략 보고서")
    if "forecast" in visitor_model and "forecast" in spending_model:
        report_summary = pd.DataFrame(
            [
                ["방문객 수", f"{latest['visitors'] / 10_000:,.0f}만 연인원", f"{visitor_model['forecast'] / 10_000:,.0f}만 연인원", "한국관광 데이터랩 · 방문자 수(연인원) 추이"],
                ["내국인 관광소비", f"{latest['spending_thousand_krw'] / 100_000:,.0f}억 원", f"{spending_model['forecast'] / 100_000:,.0f}억 원", "한국관광 데이터랩 · 관광소비 추이_내국인"],
                ["방문 1회당 추정 소비", f"₩{latest['spending_per_visit_krw']:,.0f}", f"₩{forecast_per_visit:,.0f}", "관광소비액 ÷ 방문자 연인원 계산값"],
                ["숙박 방문 비율", f"{latest['stay_rate']:.1f}%", "예측하지 않음", "한국관광 데이터랩 · 순 방문자 수 및 숙박 비율"],
            ],
            columns=["항목", "최근 관측(2026-07)", "다음 달 참고 추정", "데이터 근거"],
        )
        st.caption("AI 보고서에 전달되는 핵심 데이터·예측 근거입니다.")
        st.dataframe(report_summary, hide_index=True, use_container_width=True)
    form_left, form_right = st.columns(2)
    with form_left:
        business = st.selectbox("연계 업종", ["숙박업", "음식·카페", "체험·문화", "관광정책·마케팅"])
    with form_right:
        goal = st.selectbox("사업 목표", ["체류시간 확대", "외지인 소비 확대", "비수기 방문 유도", "관광 동선 개선"])
    if st.button("공식 근거를 찾아 AI 전략 보고서 생성", type="primary", use_container_width=True):
        try:
            with st.spinner("관광 지표와 공식 웹 근거를 검토하고 있습니다..."):
                report = generate_report(metrics, visitor_model, spending_model, business, goal)
            st.markdown(report)
        except Exception as exc:
            st.warning(str(exc))
            st.caption("키를 입력한 뒤 다시 시도해 주세요. 키는 화면이나 저장소에 표시되지 않습니다.")

    with st.expander("데이터 사용·해석 유의사항"):
        st.write("원본은 한국관광 데이터랩에서 다운로드한 강남구 ZIP이며 수정하지 않고 읽습니다. 방문자 수는 연인원, 관광소비액은 내국인 기준, 관심도는 내비게이션/SNS 검색 기반 지표입니다.")


if __name__ == "__main__":
    main()
