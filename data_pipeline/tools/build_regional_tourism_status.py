"""지역별 관광 현황 ZIP을 기획 근거용 정규화 결과로 변환한다.

이 자료는 기존 7개 월별 수요 target을 대체하지 않는다. 유입·유출과 인기장소는
지역 맞춤 사업 후보를 비교하는 관측 근거로, 향후 30일 집중률은 혼잡·분산 운영을
검토하는 단기 신호로만 저장한다. 원본 ZIP은 열어 읽기만 하며 추출본을 남기지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from .data_inventory import decode_csv, normalize_month, sha256_file
except ModuleNotFoundError:  # pragma: no cover - tools 폴더 직접 실행
    from data_inventory import decode_csv, normalize_month, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGION_CODES = (
    PROJECT_ROOT / "data" / "processed" / "nationwide" / "materialized_region_reference" / "official_municipality_codes.csv"
)
ARCHIVE_NAME_RE = re.compile(
    r"^(?P<region>.+?)(?:_(?P<period>20\d{4}-20\d{4}))?_(?P<category>유입유출|인기관광지|지역집중률)\.zip$"
)


def _normalized_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source_id(inner_hash: str, member_name: str) -> str:
    """바깥 ZIP 안의 같은 이름·다른 내용도 구분되는 안정적인 source ID다."""

    path_hash = hashlib.sha256(member_name.encode("utf-8")).hexdigest()[:12]
    return f"regional-status:{path_hash}:{inner_hash[:12]}"


def _outer_source_id(outer_hash: str) -> str:
    return f"regional-status-bundle:{outer_hash[:16]}"


def _read_csv_rows(raw: bytes) -> list[dict[str, str]]:
    text, _ = decode_csv(raw)
    return list(csv.DictReader(io.StringIO(text)))


def _number(value: Any) -> str:
    """원본의 쉼표·과학표기 숫자를 정확한 10진 문자열로 정규화한다."""

    cleaned = str(value or "").strip().replace(",", "")
    if not cleaned:
        return ""
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return ""
    if not parsed.is_finite():
        return ""
    rendered = format(parsed, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _int_or_empty(value: Any) -> str:
    numeric = _number(value)
    if not numeric:
        return ""
    try:
        return str(int(Decimal(numeric)))
    except (InvalidOperation, ValueError):
        return ""


def _period_label(value: str) -> str:
    if not re.fullmatch(r"20\d{4}-20\d{4}", value or ""):
        return ""
    return f"{value[:4]}-{value[4:6]} ~ {value[7:11]}-{value[11:]}"


def _load_region_codes(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "official_full_name" not in rows[0] or "region_code" not in rows[0]:
        raise ValueError("OFFICIAL_REGION_CODE_SCHEMA_INVALID")
    return {
        _normalized_name(row["official_full_name"]): row
        for row in rows
        if row.get("official_full_name") and row.get("region_code")
    }


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _flow_direction(value: str) -> str:
    return "inbound" if str(value).strip() == "1" else "outbound" if str(value).strip() == "2" else ""


def _append_flow_records(
    records: list[dict[str, str]], *, region_code: str, source_period: str, source_id: str, rows: list[dict[str, str]]
) -> None:
    for row in rows:
        direction = _flow_direction(row.get("유입/유출 구분 코드 (1:유입 / 2:유출)", ""))
        related = row.get("유입지역명") if direction == "inbound" else row.get("유출지역명")
        ratio = _number(row.get("유입유출 비율"))
        if not direction or not related or not ratio:
            continue
        records.append({
            "region_code": region_code,
            "source_period": source_period,
            "direction": direction,
            "related_region_name": _normalized_name(related),
            "ratio_pct": ratio,
            "rank_no": "",
            "source_id": source_id,
        })


def _append_destination_type_records(
    records: list[dict[str, str]], *, region_code: str, source_period: str, source_id: str, filename: str, rows: list[dict[str, str]]
) -> None:
    if "유입 목적지 유형" in filename:
        direction, dataset = "inbound", "destination_type"
    elif "유출 목적지 유형" in filename:
        direction, dataset = "outbound", "destination_type"
    elif "유입도시 유형 분류-유형별 방문 관광자원" in filename:
        direction, dataset = "inbound", "origin_resource_type"
    elif "유입도시 유형 분류-유형별 소비 업종" in filename:
        direction, dataset = "inbound", "origin_spending_type"
    else:
        return
    for row in rows:
        if dataset == "destination_type":
            group, detail = row.get("유형 중분류명", ""), row.get("유형 소분류명", "")
            share = _number(row.get("소분류 검색건수 비율"))
            group_share = _number(row.get("중분류 검색건수 비율"))
        elif dataset == "origin_resource_type":
            group, detail = row.get("KTO카테고리중분류명", ""), ""
            share = _number(row.get("비율"))
            group_share = ""
        else:
            group, detail = row.get("업종대분류", ""), ""
            share = _number(row.get("비율"))
            group_share = ""
        if not group or not share:
            continue
        records.append({
            "region_code": region_code,
            "source_period": source_period,
            "direction": direction,
            "dataset_type": dataset,
            "category_group": _normalized_name(group),
            "category_detail": _normalized_name(detail),
            "share_pct": share,
            "group_share_pct": group_share,
            "source_id": source_id,
        })


def _append_route_yoy_records(
    records: list[dict[str, str]], *, region_code: str, source_period: str, source_id: str, filename: str, rows: list[dict[str, str]]
) -> None:
    if "전년 동기 대비" not in filename or "▶" not in filename:
        return
    direction = "inbound" if "유입" in filename else "outbound" if "유출" in filename else ""
    if not direction:
        return
    route = filename.split(" 전년 동기 대비", 1)[0].split("_", 1)[-1].strip()
    for row in rows:
        category = _normalized_name(row.get("업종중분류명", ""))
        if not category:
            continue
        records.append({
            "region_code": region_code,
            "source_period": source_period,
            "direction": direction,
            "route_label": route,
            "industry_middle": category,
            "search_count": _number(row.get("검색건수")),
            "previous_year_search_count": _number(row.get("전년동기 검색건수")),
            "search_yoy_pct": _number(row.get("전년동기 대비 검색율")),
            "total_search_count": _number(row.get("총검색건수")),
            "previous_year_total_search_count": _number(row.get("전년동기 총검색건수")),
            "total_search_yoy_pct": _number(row.get("전년동기 대비 총검색율")),
            "source_id": source_id,
        })


def _place_kind(filename: str) -> tuple[str, str, str]:
    """파일명에서 데이터셋·대상·언어를 명시적으로 보존한다."""

    if "주요 유료관광지점" in filename:
        audience = "all" if "전체" in filename else "domestic" if "내국인" in filename else "foreign"
        return "paid_attraction_admissions", audience, ""
    if "인기관광지" in filename:
        audience = "all" if "전체" in filename else "local" if "현지인" in filename else "nonlocal"
        return "popular_attraction", audience, ""
    if "맛집" in filename:
        audience = "all" if "전체" in filename else "local" if "현지인" in filename else "nonlocal"
        return "popular_restaurant", audience, ""
    if "중심 관광지" in filename:
        return "central_attraction", "all", ""
    if "내국인 관심 관광지" in filename:
        return "interest_attraction", "domestic", ""
    if "외국인 관심 관광지" in filename:
        language = "english" if "영어" in filename else "japanese" if "일본어" in filename else "chinese_simplified" if "중간" in filename else "chinese_traditional" if "중번" in filename else "foreign"
        return "interest_attraction", "foreign", language
    return "", "", ""


def _append_place_records(
    records: list[dict[str, str]], *, region_code: str, source_period: str, source_id: str, filename: str, rows: list[dict[str, str]]
) -> None:
    dataset_type, audience, language = _place_kind(filename)
    if not dataset_type:
        return
    for row in rows:
        place_name = row.get("관광지명") or row.get("업소명") or ""
        if not place_name:
            continue
        admission = _number(row.get("입장객수")) if dataset_type == "paid_attraction_admissions" else ""
        records.append({
            "region_code": region_code,
            "source_period": source_period,
            "dataset_type": dataset_type,
            "audience": audience,
            "language": language or _normalized_name(row.get("언어명", "")),
            "place_id": _normalized_name(row.get("관광지ID", "")),
            "place_name": _normalized_name(place_name),
            "classification": _normalized_name(row.get("분류") or row.get("구분") or ""),
            "rank_no": _int_or_empty(row.get("순위")),
            "observation_month": normalize_month(str(row.get("기준연월", ""))),
            "metric_name": "admissions" if admission else "rank",
            "metric_value": admission,
            "metric_unit": "visitors" if admission else "rank_only",
            "source_id": source_id,
        })


def _append_concentration_records(
    records: list[dict[str, str]], *, region_code: str, source_id: str, rows: list[dict[str, str]]
) -> None:
    for row in rows:
        raw_date = str(row.get("기준연월", "")).strip()
        if not re.fullmatch(r"20\d{6}", raw_date):
            continue
        ratio = _number(row.get("방문비율(%)"))
        if not ratio:
            continue
        records.append({
            "region_code": region_code,
            "signal_date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}",
            "visit_ratio_pct": ratio,
            "source_id": source_id,
        })


def _rank_flow_records(records: list[dict[str, str]]) -> None:
    """원본 순위가 없는 유입·유출 비율은 동일 기간·방향 안에서만 정렬한다."""

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for record in records:
        groups[(record["region_code"], record["source_period"], record["direction"])].append(record)
    for rows in groups.values():
        rows.sort(key=lambda row: (-float(row["ratio_pct"]), row["related_region_name"]))
        for index, row in enumerate(rows, start=1):
            row["rank_no"] = str(index)


def _top(
    rows: Iterable[dict[str, str]], *, count: int = 5, key: str = "rank_no", descending: bool = False
) -> list[dict[str, Any]]:
    """순위는 작은 값 우선, 비율은 큰 값 우선으로 안전하게 상위 항목을 고른다."""

    def sort_value(row: dict[str, str]) -> Decimal:
        try:
            return Decimal(str(row.get(key) or "0"))
        except InvalidOperation:
            return Decimal("0") if descending else Decimal("999999")

    ordered = sorted(
        rows,
        key=lambda row: (
            -sort_value(row) if descending else sort_value(row),
            row.get("place_name") or row.get("related_region_name") or row.get("category_group") or "",
        ),
    )
    return [dict(row) for row in ordered[:count]]


def _build_context(
    *, region_names: dict[str, str], flow: list[dict[str, str]], destination_types: list[dict[str, str]], places: list[dict[str, str]], concentration: list[dict[str, str]], source_records: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Agent에 전달할 지역당 작은 사실표를 만든다. 전체 raw 행은 이 JSON에 넣지 않는다."""

    by_region_flow: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_region_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_region_place: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_region_concentration: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in flow:
        by_region_flow[item["region_code"]].append(item)
    for item in destination_types:
        by_region_type[item["region_code"]].append(item)
    for item in places:
        by_region_place[item["region_code"]].append(item)
    for item in concentration:
        by_region_concentration[item["region_code"]].append(item)

    regions: dict[str, dict[str, Any]] = {}
    for region_code, region_name in sorted(region_names.items()):
        region_flow = by_region_flow.get(region_code, [])
        region_types = by_region_type.get(region_code, [])
        region_places = by_region_place.get(region_code, [])
        region_concentration = sorted(by_region_concentration.get(region_code, []), key=lambda row: row["signal_date"])
        if not (region_flow or region_places or region_concentration):
            continue
        latest_period = max((item["source_period"] for item in region_flow + region_places if item.get("source_period")), default="")
        latest_flow = [item for item in region_flow if item["source_period"] == latest_period]
        latest_types = [item for item in region_types if item["source_period"] == latest_period]
        latest_places = [item for item in region_places if item["source_period"] == latest_period]
        source_ids = sorted({item["source_id"] for item in latest_flow + latest_types + latest_places + region_concentration})

        def place_rows(dataset_type: str, audience: str = "all") -> list[dict[str, str]]:
            return [item for item in latest_places if item["dataset_type"] == dataset_type and item["audience"] == audience]

        paid = place_rows("paid_attraction_admissions")
        paid_totals: dict[str, dict[str, Any]] = {}
        for item in paid:
            name = item["place_name"]
            bucket = paid_totals.setdefault(name, {"place_name": name, "classification": item["classification"], "admissions": Decimal("0"), "source_id": item["source_id"]})
            bucket["admissions"] += Decimal(item["metric_value"] or "0")
        paid_top = [
            {**item, "admissions": str(item["admissions"])}
            for item in sorted(paid_totals.values(), key=lambda item: (-item["admissions"], item["place_name"]))[:5]
        ]
        concentration_summary: dict[str, Any] = {"available": False}
        if region_concentration:
            ratios = [Decimal(item["visit_ratio_pct"]) for item in region_concentration]
            concentration_summary = {
                "available": True,
                "signal_window_start": region_concentration[0]["signal_date"],
                "signal_window_end": region_concentration[-1]["signal_date"],
                "minimum_visit_ratio_pct": str(min(ratios)),
                "maximum_visit_ratio_pct": str(max(ratios)),
                "source_id": region_concentration[-1]["source_id"],
                "usage": "향후 30일 운영 참고 신호이며, ML 예측값·정책 효과·확정 방문자 수가 아니다.",
            }
        regions[region_code] = {
            "available": True,
            "region_code": region_code,
            "region_name": region_name,
            "latest_historical_period": _period_label(latest_period),
            "inflow_outflow": {
                "top_inflow_origins": _top([item for item in latest_flow if item["direction"] == "inbound"]),
                "top_outflow_destinations": _top([item for item in latest_flow if item["direction"] == "outbound"]),
                "inbound_destination_types": _top([item for item in latest_types if item["direction"] == "inbound" and item["dataset_type"] == "destination_type"], key="share_pct", descending=True),
                "outbound_destination_types": _top([item for item in latest_types if item["direction"] == "outbound" and item["dataset_type"] == "destination_type"], key="share_pct", descending=True),
            },
            "popular_places": {
                "total_hotspots": _top(place_rows("popular_attraction")),
                "nonlocal_hotspots": _top(place_rows("popular_attraction", "nonlocal")),
                "restaurants": _top(place_rows("popular_restaurant")),
                "central_attractions": _top(place_rows("central_attraction")),
                "paid_attractions_by_admissions": paid_top,
            },
            "concentration_30_day_signal": concentration_summary,
            "source_records": [
                {key: source_records[source_id].get(key, "") for key in ("source_id", "source_name", "source_page_url", "date_range", "review_status")}
                for source_id in source_ids if source_id in source_records
            ],
            "limitations": [
                "유입·유출 비율과 인기 순위는 관측된 기간의 분포다. 실제 방문자 수·관광소비액 또는 사업 인과효과로 바꾸지 않는다.",
                "향후 30일 집중률은 운영 참고 신호이며 ML 학습 target이나 확정 수요 예측에 사용하지 않는다.",
            ],
        }
    return {
        "schema_version": "regional-tourism-status-v1",
        "source_url": "https://datalab.visitkorea.or.kr/",
        "usage_boundary": "ML은 기존 월별 7개 target만 사용한다. 이 context는 비교·현장 검증·운영 설계 보조 근거다.",
        "regions": regions,
    }


def build_regional_tourism_status(
    *, snapshot_zip: Path, region_codes_path: Path, output_dir: Path
) -> dict[str, Any]:
    """중첩 ZIP을 메모리에서 읽어 MySQL 적재·Agent context용 결과를 만든다."""

    if not snapshot_zip.is_file() or not zipfile.is_zipfile(snapshot_zip):
        raise FileNotFoundError(f"REGIONAL_TOURISM_STATUS_SNAPSHOT_INVALID: {snapshot_zip}")
    region_codes = _load_region_codes(region_codes_path)
    region_names: dict[str, str] = {}
    source_hash = sha256_file(snapshot_zip)
    downloaded_at = datetime.fromtimestamp(snapshot_zip.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    parent_source_id = _outer_source_id(source_hash)
    source_records: dict[str, dict[str, str]] = {
        parent_source_id: {
            "source_id": parent_source_id,
            "source_name": "한국관광 데이터랩 지역별 관광 현황 일괄 ZIP",
            "source_page_url": "https://datalab.visitkorea.or.kr/",
            "downloaded_at": downloaded_at,
            "file_name": snapshot_zip.name,
            "file_hash": source_hash,
            "date_range": "2024-01 ~ 2026-06",
            "geographic_level": "bundle",
            "filters_json": json.dumps({"source_type": "outer_bundle"}, ensure_ascii=False),
            "methodology_notes": "공유폴더 제공 공식 다운로드 묶음. 정확한 다운로드 상세 URL은 팀이 추후 보완한다.",
            "review_status": "needs_exact_download_url",
        }
    }
    lineages: list[dict[str, str]] = []
    flows: list[dict[str, str]] = []
    flow_types: list[dict[str, str]] = []
    flow_route_yoy: list[dict[str, str]] = []
    places: list[dict[str, str]] = []
    concentration: list[dict[str, str]] = []
    unmapped: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    parsed_archives = 0

    with zipfile.ZipFile(snapshot_zip) as outer:
        for member in outer.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".zip"):
                continue
            parts = member.filename.split("/")
            # 시도 자료는 별도 단위다. 시군구 기획안 근거와 섞지 않고 snapshot에는 보존만 한다.
            if not parts or parts[0] != "시군구":
                continue
            match = ARCHIVE_NAME_RE.match(Path(member.filename).name)
            if not match:
                issues.append({"member_name": member.filename, "error_code": "archive_name_unparsed", "detail": "지역·기간·분류를 파일명에서 읽지 못함"})
                continue
            official_name = _normalized_name(match["region"])
            official = region_codes.get(official_name)
            if not official:
                unmapped.append({"member_name": member.filename, "region_name": official_name, "category": match["category"], "period": match["period"] or "", "reason": "official_municipality_codes.csv에 일치 코드 없음"})
                continue
            raw_inner = outer.read(member)
            if not zipfile.is_zipfile(io.BytesIO(raw_inner)):
                issues.append({"member_name": member.filename, "error_code": "nested_archive_invalid", "detail": "내부 파일이 유효한 ZIP이 아님"})
                continue
            inner_hash = _sha256_bytes(raw_inner)
            source_id = _source_id(inner_hash, member.filename)
            source_period = match["period"] or "operational_30_day_signal"
            region_code = official["region_code"]
            region_names[region_code] = official["official_full_name"]
            source_records[source_id] = {
                "source_id": source_id,
                "source_name": f"한국관광 데이터랩 지역별 관광 현황 · {official_name} · {match['category']}",
                "source_page_url": "https://datalab.visitkorea.or.kr/",
                "downloaded_at": downloaded_at,
                "file_name": f"{snapshot_zip.name}::{member.filename}",
                "file_hash": inner_hash,
                "date_range": _period_label(match["period"] or "") or "향후 30일 운영 신호",
                "geographic_level": "municipality",
                "filters_json": json.dumps({"region_name": official_name, "category": match["category"], "period": match["period"] or "operational_30_day_signal"}, ensure_ascii=False),
                "methodology_notes": "시군구 단위 내부 ZIP. 정확한 다운로드 상세 URL은 팀이 추후 보완한다.",
                "review_status": "needs_exact_download_url",
            }
            lineages.append({"parent_source_id": parent_source_id, "child_source_id": source_id, "relation_type": "contains"})
            parsed_archives += 1
            with zipfile.ZipFile(io.BytesIO(raw_inner)) as inner:
                for csv_member in inner.infolist():
                    if csv_member.is_dir() or not csv_member.filename.lower().endswith(".csv"):
                        continue
                    try:
                        rows = _read_csv_rows(inner.read(csv_member))
                    except (UnicodeDecodeError, csv.Error) as exc:
                        issues.append({"member_name": f"{member.filename}::{csv_member.filename}", "error_code": "csv_decode_or_parse_failed", "detail": type(exc).__name__})
                        continue
                    if match["category"] == "유입유출":
                        if "유입 출발지 - 유출 목적지 분포" in csv_member.filename:
                            _append_flow_records(flows, region_code=region_code, source_period=source_period, source_id=source_id, rows=rows)
                        _append_destination_type_records(flow_types, region_code=region_code, source_period=source_period, source_id=source_id, filename=csv_member.filename, rows=rows)
                        _append_route_yoy_records(flow_route_yoy, region_code=region_code, source_period=source_period, source_id=source_id, filename=csv_member.filename, rows=rows)
                    elif match["category"] == "인기관광지":
                        _append_place_records(places, region_code=region_code, source_period=source_period, source_id=source_id, filename=csv_member.filename, rows=rows)
                    else:
                        _append_concentration_records(concentration, region_code=region_code, source_id=source_id, rows=rows)

    _rank_flow_records(flows)
    categories_by_region: dict[str, set[str]] = defaultdict(set)
    for record in flows:
        categories_by_region[record["region_code"]].add("유입유출")
    for record in places:
        categories_by_region[record["region_code"]].add("인기관광지")
    for record in concentration:
        categories_by_region[record["region_code"]].add("지역집중률")
    for region_code, name in region_names.items():
        missing = {"유입유출", "인기관광지", "지역집중률"} - categories_by_region[region_code]
        if missing:
            issues.append({"member_name": name, "error_code": "category_missing", "detail": ",".join(sorted(missing))})

    context = _build_context(
        region_names=region_names,
        flow=flows,
        destination_types=flow_types,
        places=places,
        concentration=concentration,
        source_records=source_records,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "source_records.csv", list(next(iter(source_records.values())).keys()), source_records.values())
    _write_csv(output_dir / "source_lineage.csv", ["parent_source_id", "child_source_id", "relation_type"], lineages)
    _write_csv(output_dir / "flow_distribution.csv", ["region_code", "source_period", "direction", "related_region_name", "ratio_pct", "rank_no", "source_id"], flows)
    _write_csv(output_dir / "flow_destination_types.csv", ["region_code", "source_period", "direction", "dataset_type", "category_group", "category_detail", "share_pct", "group_share_pct", "source_id"], flow_types)
    _write_csv(output_dir / "flow_route_industry_yoy.csv", ["region_code", "source_period", "direction", "route_label", "industry_middle", "search_count", "previous_year_search_count", "search_yoy_pct", "total_search_count", "previous_year_total_search_count", "total_search_yoy_pct", "source_id"], flow_route_yoy)
    _write_csv(output_dir / "place_records.csv", ["region_code", "source_period", "dataset_type", "audience", "language", "place_id", "place_name", "classification", "rank_no", "observation_month", "metric_name", "metric_value", "metric_unit", "source_id"], places)
    _write_csv(output_dir / "concentration_records.csv", ["region_code", "signal_date", "visit_ratio_pct", "source_id"], concentration)
    _write_csv(output_dir / "unmapped_region_archives.csv", ["member_name", "region_name", "category", "period", "reason"], unmapped)
    _write_csv(output_dir / "data_quality_issues.csv", ["member_name", "error_code", "detail"], issues)
    (output_dir / "context_by_region.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "status": "ready_for_regional_tourism_status_import",
        "snapshot_file": snapshot_zip.name,
        "snapshot_sha256": source_hash,
        "municipality_archives_parsed": parsed_archives,
        "mapped_region_count": len(region_names),
        "context_region_count": len(context["regions"]),
        "source_record_count": len(source_records),
        "flow_distribution_count": len(flows),
        "flow_destination_type_count": len(flow_types),
        "flow_route_industry_yoy_count": len(flow_route_yoy),
        "place_record_count": len(places),
        "concentration_record_count": len(concentration),
        "unmapped_archive_count": len(unmapped),
        "issue_count": len(issues),
        "unmapped_regions_are_not_activated": sorted({row["region_name"] for row in unmapped}),
        "ml_boundary": "향후 30일 집중률과 인기 순위는 ML target·feature로 사용하지 않으며, 기존 월별 7개 target을 변경하지 않는다.",
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지역별 관광 현황 중첩 ZIP 정규화")
    parser.add_argument("--snapshot-zip", required=True)
    parser.add_argument("--region-codes", default=str(DEFAULT_REGION_CODES))
    parser.add_argument("--output-dir", default="data/processed/regional_tourism_status")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_regional_tourism_status(
            snapshot_zip=Path(args.snapshot_zip),
            region_codes_path=Path(args.region_codes),
            output_dir=Path(args.output_dir),
        )
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
