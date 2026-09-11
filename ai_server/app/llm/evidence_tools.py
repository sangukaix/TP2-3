"""요청별 읽기 전용 근거 도구. 네트워크·SQL·파일 경로·코드 실행 권한은 없습니다.

긴 근거를 삭제하는 대신 원본을 메모리에 보관하고 모델이 필요한 자료를 조회합니다.
새 요청마다 인스턴스를 만들며, 첨부 원문/도구 결과를 디스크나 공용 trace에 저장하지 않습니다.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .errors import LLMProviderError
from ..evidence_sources import merge_evidence_sources


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties or {},
                       'required': required or [], 'additionalProperties': False},
    }}


# 허용된 함수와 인자만 받습니다. 임의 Python·SQL·URL을 받는 범용 도구는 만들지 않습니다.
TOOL_DEFINITIONS = [
    _tool('get_region_metrics', '선택 지역의 공식 관측값·기준기간을 조회한다. ML 수치가 아니다.'),
    _tool('get_regional_tourism_status', '선택 지역의 공식 유입·유출 권역, 인기 장소·업소, 향후 30일 집중 운영 신호를 조회한다. ML 예측·정책 효과가 아니다.'),
    _tool('compare_regions', '이미 검증된 동일 기간 peer 비교를 조회한다. 격차는 선택 지역-비교 지역이다.'),
    _tool('get_nationwide_bigdata_context', '선택 지역의 기간합계·비중과 전국 월별 관광 맥락을 조회한다. 지역 월별 ML·정책효과·전국 평균이 아니다.'),
    _tool('get_planning_decision', '선정 이유·진단·선택 후보 전체와 전략을 읽는다. 다른 후보와 상세 평가는 별도 경로로 제공한다.'),
    _tool('get_ml_forecast', '저장 ML 전망·기간 정책·검증 경계를 읽는다. 재학습이나 정책효과 추정은 하지 않는다.',
          {'start_month': {'type': 'string', 'pattern': '^\\d{4}-(0[1-9]|1[0-2])$'},
           'end_month': {'type': 'string', 'pattern': '^\\d{4}-(0[1-9]|1[0-2])$'}}),
    _tool('get_case_comparison_matrix', '수집된 공식 사례를 운영 원리·조건·위험별로 한눈에 비교한다. 원문 인용 전에는 read_collected_source를 별도로 호출해야 한다.'),
    _tool('search_collected_sources', '이번 요청에 수집된 공식 사례/출처의 목록을 검색한다. 실시간 웹검색이 아니다.',
          {'query': {'type': 'string', 'maxLength': 120},
           'offset': {'type': 'integer', 'minimum': 0},
           'limit': {'type': 'integer', 'minimum': 1, 'maximum': 8}}),
    _tool('read_collected_source', 'source_id의 출처와 사례 원문을 읽는다. PDF 청크는 next_offset이 없을 때까지 순서대로 읽는다. 사례 인용 전에 반드시 호출한다.',
          {'source_id': {'type': 'string', 'minLength': 1, 'maxLength': 200},
           'offset': {'type': 'integer', 'minimum': 0},
           'limit': {'type': 'integer', 'minimum': 1, 'maximum': 4}}, ['source_id']),
    _tool('read_task_section', '요청 원문의 JSON Pointer 경로. 긴 draft_report/previous_draft는 offset 순서로 limit=1을 사용해 모든 JSON 조각을 읽는다. 파일 경로가 아니다.',
          {'path': {'type': 'string', 'maxLength': 300},
           'offset': {'type': 'integer', 'minimum': 0},
           'limit': {'type': 'integer', 'minimum': 1, 'maximum': 4}}, ['path']),
]


def _case_mechanism_family(case: dict[str, Any]) -> str:
    """사례 제목이 아닌 실제 운영 원리로 읽기 다양성을 확인합니다.

    로컬 모델이 ``숙박``이라는 한 단어만 보고 같은 유형의 사례를 반복 선택하지 않도록
    사용하는 내부 분류입니다. 이 값은 새로운 사실이나 사례 평가 점수를 만들지 않고,
    이번 요청에 이미 있는 사례 카드를 어떤 순서로 읽을지 돕는 용도입니다.
    """
    from ..case_mechanism import case_mechanism_family
    return case_mechanism_family(case)


class EvidenceTools:
    """공식 근거의 수치·기간·source_id는 그대로 두고 전달 분량만 요청 단위로 나눕니다."""

    def __init__(self, payload: dict[str, Any], *, task: str = '') -> None:
        self.payload = deepcopy(payload)
        self.task = task
        self.pack = self.payload.get('evidence_pack', self.payload)
        self.snapshot = self.pack.get('snapshot') or {}
        self.sources: dict[str, dict[str, Any]] = {}
        for kind, rows in (('source', merge_evidence_sources(self.pack.get('sources') or [])),
                           ('case', self.pack.get('benchmark_cases') or [])):
            for row in rows:
                source_id = str(row.get('source_id') or '')
                if source_id:
                    item = self.sources.setdefault(source_id, {})
                    if kind == 'source' and row.get('chunk_id'):
                        item.setdefault('chunks', []).append(row)
                    else:
                        item[kind] = row
        self.read_source_ids: set[str] = set()
        self.source_chunk_reads: dict[str, set[int]] = {}
        self.read_paths: set[str] = set()
        self.segment_reads: dict[str, set[int]] = {}
        self.events: list[dict[str, Any]] = []

    def overview(self) -> dict[str, Any]:
        """핵심 조건·관측값은 처음부터 전달하고 긴 근거는 위치와 목록을 공개합니다."""
        ml = self.snapshot.get('ml_analysis') or {}
        policy = ml.get('horizon_policy') or {}
        transfer = self.pack.get('transfer_assessment') or {}
        prefix = '/evidence_pack' if 'evidence_pack' in self.payload else ''
        result = {
            'region_code': self.pack.get('region_code'), 'region_name': self.pack.get('region_name'),
            'period': self.pack.get('period'), 'planning_brief': self.pack.get('planning_brief'),
            'research_gaps': self.pack.get('research_gaps', []),
            'case_search_policy': self.pack.get('case_search_policy', {}),
            'case_search_coverage': self.pack.get('case_search_coverage', {}),
            'quality_contract_version': self.pack.get('quality_contract_version'),
            'observations': self.snapshot.get('observations', []),
            'ml_status': ml.get('status'),
            'ml_windows': [{key: window.get(key) for key in ('start_month', 'end_month', 'reliability')}
                           for window in policy.get('decision_windows', [])],
            'selected_candidate_id': transfer.get('selected_candidate_id'),
            'selection_status': transfer.get('selection_status'),
            'case_index': [{'source_id': key, 'title': item['case'].get('title') or item['case'].get('source_title') or item['case'].get('intervention'),
                            'case_region': item['case'].get('case_region'),
                            'retrieval_context': item['case'].get('retrieval_context', {}),
                            'mechanism_family': _case_mechanism_family(item['case'])}
                           for key, item in self.sources.items() if 'case' in item],
            'source_count': len(self.sources),
            'source_chunk_count': sum(len(item.get('chunks', [])) for item in self.sources.values()),
            'sections': [f'{prefix}/{key}' for key in self.pack],
            'snapshot_sections': [f'{prefix}/snapshot/{key}' for key in self.snapshot],
            'other_sections': [f'/{key}' for key in self.payload if key != 'evidence_pack'],
            'note': '목록은 원문의 대체물이 아니다. 필요한 사례·ML·비교값·적용성 평가를 도구로 읽고 판단한다.',
        }
        if 'quality_review_feedback' in self.payload:
            # 오류 목록은 최종 JSON 작성 직전에 원문 그대로 한 번 전달한다.
            # 개요에도 전체 목록을 복제하면 실제 원주 보완 요청처럼 긴 수정 지시가
            # 문맥을 두 번 차지하므로, 여기서는 위치와 개수만 공개한다.
            feedback = self.payload.get('quality_review_feedback') or {}
            result['quality_review_feedback_reference'] = {
                'path': '/quality_review_feedback',
                'issue_count': len(feedback.get('issues') or []),
                'delivery': '최종 JSON 작성 직전에 원문 전체 제공',
            }
        if 'deterministic_precheck' in self.payload:
            result['deterministic_precheck'] = self.payload['deterministic_precheck']
        return result

    def _compare(self) -> dict[str, Any]:
        result = deepcopy(self.snapshot.get('nationwide_comparison') or {'available': False})
        result['gap_convention'] = '선택 지역 - 비교 지역. 양수: 선택 지역이 높음. 음수: 선택 지역이 낮음.'
        for peer in result.get('peer_regions', []):
            peer['gap_directions'] = {
                key: ('higher' if value > 0 else 'lower' if value < 0 else 'equal')
                for key, value in peer.items() if '_gap_' in key
                and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            }
        return result

    def _nationwide_bigdata_context(self) -> dict[str, Any]:
        result = deepcopy(self.snapshot.get('nationwide_bigdata_context') or {'available': False})
        result['read_rule'] = (
            '기간합계·비중은 같은 기간/같은 정의 안에서만 보조 비교한다. 전국 월별 추이는 지역 실적·예측·정책효과로 바꾸지 않는다.'
        )
        return result

    def _regional_tourism_status(self) -> dict[str, Any]:
        """지역 현황의 *결정용 요약*만 반환하고, 원본은 요청 범위에 그대로 보존한다.

        일부 지역은 인기장소 3개씩만 남겨도 장소 ID·원본 기간·분류 같은 반복 열 때문에
        12KB 도구 결과 한도를 넘었습니다. 그 경우 도구가 ``unavailable``로 기록되어
        필수 근거 검증까지 실패했습니다. 이 함수는 기획에 필요한 관측값·단위·순위·출처는
        유지하되 반복 식별 열만 생략한 명시적 요약을 만듭니다. 더 긴 원문은
        ``full_detail_path``로만 읽을 수 있으며, 여기서 원본 snapshot을 변경하거나
        조용히 잘라내지 않습니다.
        """

        raw_status = self.snapshot.get('regional_tourism_status') or {'available': False}
        if not raw_status.get('available'):
            return deepcopy(raw_status)

        def compact_rows(rows: Any, fields: tuple[str, ...], *, limit: int = 3) -> list[dict[str, Any]]:
            """같은 지역·기간을 반복하는 행은 제거하고, 상위 순위와 출처는 유지한다."""

            compacted: list[dict[str, Any]] = []
            for row in list(rows or [])[:limit]:
                if not isinstance(row, dict):
                    continue
                compacted.append({
                    key: deepcopy(row[key])
                    for key in fields
                    if key in row and row[key] not in (None, '')
                })
            return compacted

        inflow_outflow = raw_status.get('inflow_outflow') or {}
        popular = raw_status.get('popular_places') or {}
        prefix = '/evidence_pack' if 'evidence_pack' in self.payload else ''
        return {
            'available': True,
            'region_code': raw_status.get('region_code'),
            'region_name': raw_status.get('region_name'),
            'latest_historical_period': raw_status.get('latest_historical_period'),
            'inflow_outflow': {
                'top_inflow_origins': compact_rows(
                    inflow_outflow.get('top_inflow_origins'),
                    ('related_region_name', 'ratio_pct', 'rank_no', 'source_id'),
                ),
                'top_outflow_destinations': compact_rows(
                    inflow_outflow.get('top_outflow_destinations'),
                    ('related_region_name', 'ratio_pct', 'rank_no', 'source_id'),
                ),
                'inbound_destination_types': compact_rows(
                    inflow_outflow.get('inbound_destination_types'),
                    ('category_group', 'category_detail', 'share_pct', 'group_share_pct', 'source_id'),
                ),
                'outbound_destination_types': compact_rows(
                    inflow_outflow.get('outbound_destination_types'),
                    ('category_group', 'category_detail', 'share_pct', 'group_share_pct', 'source_id'),
                ),
            },
            'popular_places': {
                key: compact_rows(
                    rows,
                    ('place_name', 'classification', 'rank_no', 'observation_month',
                     'metric_name', 'metric_value', 'metric_unit', 'admissions', 'source_id'),
                )
                for key, rows in popular.items()
            },
            'concentration_30_day_signal': deepcopy(raw_status.get('concentration_30_day_signal') or {}),
            'source_records': deepcopy(raw_status.get('source_records') or []),
            'limitations': deepcopy(raw_status.get('limitations') or []),
            'full_detail_path': f'{prefix}/snapshot/regional_tourism_status',
            'full_detail_read_rule': (
                '이 결과는 후보 비교용 상위 관측 요약이다. 세부 순위·반복 열을 인용해야 하면 '
                'read_task_section으로 full_detail_path의 필요한 하위 목록을 읽는다.'
            ),
            'tool_usage': (
                '유입·유출 비율과 인기 순위는 관측 분포다. 향후 30일 집중률은 운영 참고 신호이며 '
                'ML 예측·확정 수요·정책 효과로 사용하면 안 된다.'
            ),
        }

    def _forecast(self, arguments: dict) -> dict:
        result = deepcopy(self.snapshot.get('ml_analysis') or {'status': 'unavailable'})
        start, end = arguments.get('start_month', ''), arguments.get('end_month', '9999-12')
        if start > end:
            raise ValueError('시작월이 종료월보다 늦습니다.')
        # 날짜 비교만 YYYY-MM으로 통일합니다. 원본 월 표기와 모든 수치는 바꾸지 않습니다.
        def normalized_month(row: dict) -> str:
            month = str(row.get('month', ''))
            return month[:4] + '-' + month[4:] if re.fullmatch(r'\d{6}', month) else month
        if 'forecasts' in result:
            result['forecasts'] = [row for row in result['forecasts'] if start <= normalized_month(row) <= end]
        # 월별 숫자·모델별 검증 성능·기준선·주의사항은 전부 유지합니다.
        # 긴 파생 해석/연구 질문은 별도 조회 위치를 명시하고 원본에서 그대로 제공합니다.
        prefix = '/evidence_pack' if 'evidence_pack' in self.payload else ''
        result['additional_sections'] = {
            key: f'{prefix}/snapshot/ml_analysis/{key}'
            for key in ('signals', 'research_questions') if key in result
        }
        for key in result['additional_sections']:
            result.pop(key)
        if self.snapshot.get('decision_facts'):
            result['window_aggregate_path'] = f'{prefix}/snapshot/decision_facts/forecast_windows'
        return result

    def _decision(self) -> dict:
        assessment = self.pack.get('transfer_assessment') or {}
        result = deepcopy({key: value for key, value in assessment.items()
                           if key not in ('design_candidates', 'candidate_assessments')})
        selected = assessment.get('selected_candidate_id')
        candidates = assessment.get('design_candidates') or []
        result['selected_candidate'] = next((deepcopy(row) for row in candidates
                                              if row.get('candidate_id') == selected), None)
        result['candidate_index'] = [{key: row.get(key) for key in ('candidate_id', 'title')} for row in candidates]
        prefix = '/evidence_pack' if 'evidence_pack' in self.payload else ''
        result['additional_sections'] = {
            key: f'{prefix}/transfer_assessment/{key}'
            for key in ('design_candidates', 'candidate_assessments') if key in assessment
        }
        if self.task == 'transferability' and (self.payload.get('quality_review_feedback') or {}).get('issues'):
            result['review_context'] = {
                'status': 'rejected_candidate_draft',
                'instruction': '이전 후보는 수정 대상이며 승인된 실행안이 아니다. 원문은 오류 대조용으로 보존한다. 사례 원문과 지역 사실로 후보를 다시 비교하고 잘못된 선정은 교체한다.',
            }
        return result

    def _case_matrix(self) -> dict:
        """Qwen이 제목이 아닌 운영 원리와 제약으로 사례를 먼저 비교하게 합니다."""
        def excerpt(value: Any, *, limit: int = 420) -> tuple[str, bool]:
            # 비교표는 사례 선택을 위한 안내일 뿐 원문을 대체하지 않습니다. 길이가 긴 경우
            # 잘렸다는 사실과 개별 원문 조회 필요를 함께 명시합니다.
            text = str(value or '')
            return (text, False) if len(text) <= limit else (text[:limit] + ' …', True)

        rows = []
        for source_id, item in self.sources.items():
            case = item.get('case')
            if not case:
                continue
            operating_model, operating_model_truncated = excerpt(case.get('operating_model'))
            observed_result, observed_result_truncated = excerpt(case.get('observed_result'), limit=280)
            rows.append({
                'source_id': source_id,
                'mechanism_family': _case_mechanism_family(case),
                'case_region': case.get('case_region'),
                'retrieval_context': case.get('retrieval_context', {}),
                'intervention': case.get('intervention') or case.get('title'),
                'problem_addressed': case.get('problem_addressed'),
                'operating_model_excerpt': operating_model,
                'operating_model_truncated': operating_model_truncated,
                'evidence_strength': case.get('evidence_strength'),
                'observed_result_excerpt': observed_result,
                'observed_result_truncated': observed_result_truncated,
                'transfer_condition_count': len(case.get('transfer_conditions') or []),
                'risk_count': len(case.get('risks') or []),
            })
        return {
            'rows': rows,
            'citation_rule': '이 표는 비교용 요약이다. source_id를 최종 인용하려면 read_collected_source로 해당 원문을 읽어야 한다.',
        }

    def _search(self, arguments: dict) -> dict:
        words = str(arguments.get('query', '')).lower().split()
        rows = []
        for source_id, item in self.sources.items():
            body = compact_json(item).lower()
            if words and not all(word in body for word in words):
                continue
            card = item.get('case') or item.get('source') or next(iter(item.get('chunks', [])), {})
            rows.append({'source_id': source_id, 'title': card.get('title') or card.get('source_title') or card.get('intervention'),
                         'case_region': card.get('case_region'), 'source_type': card.get('source_type'),
                         'source_url': card.get('source_url') or card.get('url'),
                         'chunk_count': len(item.get('chunks', []))})
        offset, limit = arguments.get('offset', 0), arguments.get('limit', 8)
        return {'total': len(rows), 'items': rows[offset:offset + limit],
                'next_offset': offset + limit if offset + limit < len(rows) else None,
                'live_web_search': False}

    def _section(self, arguments: dict) -> dict:
        path = arguments['path']
        if not path.startswith('/'):
            raise ValueError('JSON Pointer는 /로 시작해야 합니다.')
        value: Any = self.payload
        for part in path[1:].split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            value = value[int(key)] if isinstance(value, list) and key.isdecimal() else value[key]
        offset, limit = arguments.get('offset', 0), arguments.get('limit', 4)
        if path in ('/previous_draft', '/draft_report'):
            segments = self.draft_segments(path)
            if segments:
                if offset >= len(segments):
                    raise ValueError('초안 페이지 범위를 벗어났습니다.')
                # 일부 문장을 요약·삭제하지 않고 직렬화된 원본을 순서대로 나누어 제공합니다.
                return {'path': path, 'segment_index': offset, 'segment_count': len(segments),
                        'serialized_json_segment': segments[offset],
                        'next_offset': offset + 1 if offset + 1 < len(segments) else None}
        if isinstance(value, list):
            return {'path': path, 'total': len(value), 'items': value[offset:offset + limit],
                    'next_offset': offset + limit if offset + limit < len(value) else None}
        return {'path': path, 'value': value}

    def draft_segments(self, path: str) -> list[str]:
        """긴 기존 초안만 분할합니다. 원문 전체를 읽었는지는 별도 집합으로 검증합니다."""
        draft = self.payload.get(path.removeprefix('/'))
        if not draft:
            return []
        raw = compact_json(draft)
        return [raw[index:index + 2200] for index in range(0, len(raw), 2200)] if len(raw.encode('utf-8')) > 10000 else []

    def execute(self, name: str, arguments: Any) -> dict:
        """도구 인자를 엄격히 검사하고, 결과가 너무 크면 잘라내지 않고 세부 경로 조회를 안내합니다."""
        spec = next((row['function'] for row in TOOL_DEFINITIONS if row['function']['name'] == name), None)
        if spec is None:
            raise LLMProviderError('LOCAL_TOOL_NOT_ALLOWED', '허용되지 않은 로컬 도구 요청입니다.')
        try:
            Draft202012Validator(spec['parameters']).validate(arguments)
        except ValidationError as exc:
            raise LLMProviderError('LOCAL_TOOL_ARGUMENTS_INVALID', '로컬 도구 인자가 계약과 다릅니다.') from exc
        try:
            if name == 'get_region_metrics':
                # 소비 업종 구성은 월별 ML과 다른 관측 사실이다. 기획자가 "소비를 늘린다"는
                # 일반론만 반복하지 않도록, 작고 검증 가능한 표를 처음부터 전달한다.
                # 원본 snapshot은 유지하고, 없을 때도 빈 목록으로 사실을 만들지 않는다.
                result = {'period': self.pack.get('period'), 'observations': self.snapshot.get('observations', [])}
                result['dataset_sources'] = deepcopy([
                    row for row in self.pack.get('sources') or []
                    if row.get('source_type') == 'dataset'
                ])
                result['source_link_rule'] = (
                    'dataset_sources는 이번 요청에 등록된 출처 원문이다. 관측의 지표·값·기간·출처를 '
                    '대조해 일치하는 source_id만 evidence_source_ids에 사용한다. '
                    '목록 순서나 지역명만으로 연결하지 않으며 불일치하면 확인 필요로 남긴다.'
                )
                if 'consumption_by_category' in self.snapshot:
                    result['consumption_by_category'] = deepcopy(self.snapshot['consumption_by_category'])
                    result['consumption_interpretation'] = (
                        '같은 관측 기간의 업종별 관광소비 구성이다. 업종별 비중만으로 사업 효과나 '
                        '개별 방문객의 지출 원인을 단정하지 않는다.'
                    )
            elif name == 'get_regional_tourism_status':
                result = self._regional_tourism_status()
            elif name == 'compare_regions':
                result = self._compare()
            elif name == 'get_nationwide_bigdata_context':
                result = self._nationwide_bigdata_context()
            elif name == 'get_planning_decision':
                result = self._decision()
            elif name == 'get_ml_forecast':
                result = self._forecast(arguments)
            elif name == 'get_case_comparison_matrix':
                result = self._case_matrix()
            elif name == 'search_collected_sources':
                result = self._search(arguments)
            elif name == 'read_collected_source':
                item = self.sources[arguments['source_id']]
                result = {'source_id': arguments['source_id'],
                          **{key: value for key, value in item.items() if key != 'chunks'}}
                chunks = item.get('chunks', [])
                if chunks:
                    offset, limit = arguments.get('offset', 0), arguments.get('limit', 1)
                    if offset >= len(chunks):
                        raise ValueError('Source chunk offset is out of range.')
                    result.update({'chunks': chunks[offset:offset + limit], 'chunk_count': len(chunks),
                                   'offset': offset,
                                   'next_offset': offset + limit if offset + limit < len(chunks) else None})
            else:
                result = self._section(arguments)
        except (KeyError, IndexError, TypeError, ValueError):
            result = {'error': 'EVIDENCE_NOT_FOUND_OR_INVALID_RANGE', 'message': '이 요청에 없는 근거 또는 잘못된 범위입니다.'}
        if len(compact_json(result).encode('utf-8')) > 12000:
            prefix = '/evidence_pack' if 'evidence_pack' in self.payload else ''
            result = {'error': 'EVIDENCE_RESULT_TOO_LARGE',
                      'message': '원문은 보존되어 있습니다. read_task_section으로 하위 경로/목록 한 건씩 읽으세요.',
                      'root': prefix, 'keys': list(result)}
        success = 'error' not in result
        if name == 'read_collected_source' and success:
            source_id = arguments['source_id']
            if result.get('chunk_count'):
                reads = self.source_chunk_reads.setdefault(source_id, set())
                reads.update(range(result['offset'], result['offset'] + len(result['chunks'])))
                if len(reads) == result['chunk_count']:
                    self.read_source_ids.add(source_id)
            else:
                self.read_source_ids.add(source_id)
        if name == 'read_task_section' and success:
            path = arguments['path']
            if 'segment_index' in result:
                completed_segments = self.segment_reads.setdefault(path, set())
                completed_segments.add(result['segment_index'])
                if len(completed_segments) == result['segment_count']:
                    self.read_paths.add(path)
            else:
                self.read_paths.add(path)
        # 인자·본문은 기록하지 않아 첨부 정보가 영구 로그로 유출되지 않게 합니다.
        self.events.append({'tool': name, 'status': 'completed' if success else 'unavailable'})
        return result

    def missing_required_reads(self) -> list[str]:
        """지시문뿐 아니라 코드로 필수 근거 확인을 강제해 제목만 보고 기획하지 않게 합니다."""
        completed = {event['tool'] for event in self.events if event['status'] == 'completed'}
        missing = []
        feedback_issues = (self.payload.get('quality_review_feedback') or {}).get('issues') or []
        is_targeted_revision = bool(feedback_issues) and self.task in {'transferability', 'planner_revision'}
        is_report_composition = self.task in {'planner', 'planner_revision'}
        case_source_ids = [source_id for source_id, item in self.sources.items() if 'case' in item]
        for key, tool in (
            ('regional_tourism_status', 'get_regional_tourism_status'),
            ('nationwide_comparison', 'compare_regions'),
            ('nationwide_bigdata_context', 'get_nationwide_bigdata_context'),
            ('ml_analysis', 'get_ml_forecast'),
        ):
            if (is_targeted_revision or is_report_composition) and tool == 'get_nationwide_bigdata_context':
                continue
            if self.snapshot.get(key) and tool not in completed:
                missing.append(tool)
        prefix = '/evidence_pack' if 'evidence_pack' in self.payload else ''
        if self.pack.get('transfer_assessment') and 'get_planning_decision' not in completed and f'{prefix}/transfer_assessment' not in self.read_paths:
            missing.append('get_planning_decision')
        if (self.task == 'transferability' and not is_targeted_revision and case_source_ids
                and 'get_case_comparison_matrix' not in completed):
            missing.append('get_case_comparison_matrix')
        for path in ('/previous_draft', '/draft_report'):
            if self.payload.get(path[1:]) and path not in self.read_paths:
                segments = self.draft_segments(path)
                next_index = next((i for i in range(len(segments)) if i not in self.segment_reads.get(path, set())), 0)
                missing.append(f'read_task_section({path}, offset={next_index}, limit=1)' if segments else f'read_task_section({path})')
        read_case_ids = [source_id for source_id in self.read_source_ids if source_id in case_source_ids]
        if case_source_ids:
            # Qwen의 후보 비교 단계는 서로 다른 운영 원리의 공식 사례를 두 건 이상 확인해야 합니다.
            # 사례 풀이 실제로 한 유형뿐이면 억지로 두 건을 요구하지 않습니다.
            available_families = {_case_mechanism_family(self.sources[source_id]['case']) for source_id in case_source_ids}
            read_families = {_case_mechanism_family(self.sources[source_id]['case']) for source_id in read_case_ids}
            required_family_count = min(2, len(available_families)) if self.task == 'transferability' else 1
            if len(read_families) < required_family_count:
                detail = '서로 다른 운영 방식의 공식 사례 source_id' if required_family_count > 1 else '관련 사례 source_id'
                missing.append(f'read_collected_source({detail})')
        return missing

    def read_case_source_ids(self) -> list[str]:
        """현재 요청 안에서 원문 조회까지 완료된 공식 사례 ID만 반환합니다."""
        return [source_id for source_id, item in self.sources.items()
                if 'case' in item and source_id in self.read_source_ids]

    def unread_cited_case_ids(self, value: dict) -> list[str]:
        """최종 결과가 인용했지만 아직 원문을 읽지 않은 공식 사례 ID를 찾습니다."""
        text = compact_json(value)
        return [source_id for source_id, item in self.sources.items()
                if 'case' in item and re.search(r'(?<![\w:.-])' + re.escape(source_id) + r'(?![\w:.-])', text)
                and source_id not in self.read_source_ids]

    def verify_citations(self, value: dict) -> None:
        """사례를 읽지 않고 제목만 보고 인용하는 것을 차단합니다. 진실성 최종 검수는 별도로 유지합니다."""
        unread = self.unread_cited_case_ids(value)
        if unread:
            raise LLMProviderError('LOCAL_EVIDENCE_NOT_READ', '읽지 않은 공식 사례를 인용해 로컬 결과를 채택하지 않았습니다.')
