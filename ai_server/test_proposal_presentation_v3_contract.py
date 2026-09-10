"""승인된 12장 편집형 PowerPoint의 공개 계약을 오프라인으로 검증합니다.

OpenAI·관광 Open API·MySQL을 호출하지 않고도 템플릿 구조, 핵심 문구,
네이티브 차트와 편집 가능한 텍스트 개체가 유지되는지 확인합니다.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ai_server.app import proposal_presentation
from ai_server.app import proposal_presentation_v3
from ai_server.app import proposal_presentation_v4


def _sample_report(*, with_ml: bool = True) -> dict:
    """외부 서비스 없이 최종 12장 출력의 모든 주요 영역을 채울 보고서를 만듭니다."""
    ml_analysis = {
        'status': 'available',
        'region_code': '11680',
        'region_name': '서울특별시 강남구',
        'source_id': 'ml:11680:test-v1:202607',
        'source_period': '202401~202607',
        'latest_observed_month': '202607',
        'model_version': 'test-v1',
        'forecast_type': 'historical_trend_not_policy_counterfactual',
        'horizon_policy': {'schedule_status': 'undecided', 'decision_windows': []},
        'forecasts': [
            {
                'month': f'2026{month:02d}',
                'visitors': 18_000_000 + index * 100_000,
                'spending_krw': 470_000_000_000 + index * 4_000_000_000,
            }
            for index, month in enumerate((8, 9, 10))
        ],
        'evaluation': {
            'validation_period': '202601~202603',
            'test_period': '202604~202607',
            'metrics': {
                'visitors': {'selected_model': 'RandomForestRegressor'},
                'spending_krw': {'selected_model': 'seasonal_naive'},
            },
        },
    }
    if not with_ml:
        ml_analysis = {
            'status': 'unavailable',
            'region_code': '11680',
            'region_name': '서울특별시 강남구',
            'reason_code': 'ML_DATA_OR_MODEL_UNAVAILABLE',
            'forecasts': [],
            'evaluation': {},
        }

    return {
        'summary': '방문을 야간 소비와 숙박 완료로 연결하는 3개월 시범사업을 제안합니다.',
        'region_name': '서울특별시 강남구',
        'period': '2025-08~2026-07',
        'metrics_count': 4,
        'observed_findings': [
            {
                'metric': '월간 순 방문자 수',
                'value': '17,963,441명',
                'interpretation': '최신 월 관측값',
                'source': '한국관광 데이터랩 강남구 원자료',
            },
            {
                'metric': '월간 외지인 관광소비 총액',
                'value': '481,986,415,000원',
                'interpretation': '최신 월 관측값',
                'source': '한국관광 데이터랩 강남구 원자료',
            },
            {
                'metric': '외지인 숙박 방문 비율',
                'value': '3.12%',
                'interpretation': '비교 가능한 지역보다 낮은 편',
                'source': '한국관광 데이터랩 강남구 원자료',
            },
            {
                'metric': '식음·쇼핑 소비 비중',
                'value': '84.2%',
                'interpretation': '업종별 실제 관측 비중',
                'source': '한국관광 데이터랩 강남구 원자료',
            },
        ],
        'monthly_trend': [
            {
                'month': f'2026{month:02d}',
                'visitors': 17_000_000 + index * 120_000,
                'spending_krw': 450_000_000_000 + index * 5_000_000_000,
                'visitor_index': None,
                'spending_index': None,
                'is_forecast': False,
                'is_current_month': False,
            }
            for index, month in enumerate(range(1, 8))
        ],
        'strategies': [
            {
                'priority': 1,
                'timeframe': '3개월 시범 운영',
                'title': '강남 이브닝 스테이 패스',
                'problem_to_solve': '방문 규모에 비해 숙박과 야간 소비 전환이 낮습니다.',
                'comparison_analysis': '비교 가능한 지역보다 숙박 방문 비율이 낮은 편입니다.',
                'solution': '야간 동선·식음쇼핑 혜택·숙박 완료 인증을 하나의 패스로 연결합니다.',
                'expected_effect': '실제 이용과 결제 변화를 측정해 확대 여부를 판단할 수 있습니다.',
                'budget': '운영비 + 콘텐츠비 + 실사용자 수×혜택 단가 + 성과측정비로 산정합니다.',
                'kpi': '숙박 완료율·18시 이후 결제·쿠폰 사용률을 월별로 확인합니다.',
                'evidence': '한국관광 데이터랩 관측값과 공식 사례를 함께 검토했습니다.',
                'implementation_steps': [
                    {
                        'step': number,
                        'schedule': f'{number}단계',
                        'task': f'실행 작업 {number}',
                        'deliverable': f'확인 산출물 {number}',
                    }
                    for number in range(1, 6)
                ],
                'visual_asset_source_ids': [],
            }
        ],
        'evidence_sources': [
            {
                'source_id': 'dataset:11680:monthly',
                'source_type': 'dataset',
                'title': '한국관광 데이터랩 강남구 월간 원자료',
                'source_url': 'https://datalab.visitkorea.or.kr/',
            }
        ],
        'execution_scenario': {'visitor_target_pct': 1, 'spending_target_pct': 2},
        'ml_analysis': ml_analysis,
        'planning_brief': {
            'resources_status': 'known',
            'resources_confirmed': '구청 총괄 담당자와 참여 상점 10곳',
            'resources_possible': '예약·정산 운영사',
        },
        'planning_decision': {
            'selected_candidate_id': 'candidate:a',
            'design_candidates': [{
                'candidate_id': 'candidate:a',
                'title': '강남 이브닝 스테이 패스',
                'mechanism': '야간 프로그램 이용과 같은 날 참여점 결제를 확인한 뒤 후속 혜택을 제공합니다.',
                'target_users': '강남구 외지인 방문객',
                'pilot_scope': '한 권역·3개월 시범',
                'prerequisites': '담당 역할·참여처·안전·정산·측정 기준을 착수 전에 확정합니다.',
            }],
        },
        'agent_trace': [
            {'provider': 'qwen', 'status': 'completed'},
            {'provider': 'gemma', 'status': 'completed'},
            {'provider': 'openai', 'status': 'completed'},
        ],
    }


def _slide_text(slide) -> str:
    """한 슬라이드의 네이티브 텍스트를 순서와 무관하게 합칩니다."""
    return '\n'.join(
        shape.text
        for shape in slide.shapes
        if getattr(shape, 'has_text_frame', False) and shape.text.strip()
    )


class ProposalPresentationV4ContractTest(unittest.TestCase):
    """공개 다운로드 함수가 승인된 12장 템플릿 계약을 지키는지 확인합니다."""

    def test_public_entrypoint_uses_approved_template_renderer(self) -> None:
        """기존 API import가 새 구현을 가리키고 템플릿 파일이 실제로 존재해야 합니다."""
        self.assertIs(
            proposal_presentation.create_strategy_proposal_presentation,
            proposal_presentation_v4.create_strategy_proposal_presentation,
        )
        self.assertEqual(proposal_presentation_v4.PRESENTATION_RENDER_VERSION, 'pptx-regional-target-estimate-v17')
        template_path = Path(proposal_presentation_v4.PRESENTATION_TEMPLATE_PATH)
        self.assertEqual(template_path.name, 'tourism_strategy_12_slide_template_v6.pptx')
        self.assertTrue(template_path.is_file(), f'승인된 PPT 레이아웃 원본을 찾을 수 없습니다: {template_path}')

    def test_legacy_twelve_slide_template_is_preserved_for_v3(self) -> None:
        """새 템플릿 교체가 과거 v3 직접 호출의 레이아웃 원본을 덮어쓰지 않습니다."""
        legacy_path = Path(proposal_presentation_v3.PRESENTATION_TEMPLATE_PATH)
        self.assertEqual(legacy_path.name, 'tourism_strategy_12_slide_template_legacy_v1.pptx')
        self.assertTrue(legacy_path.is_file(), f'구형 12장 템플릿 보존본이 없습니다: {legacy_path}')
        self.assertNotEqual(legacy_path, Path(proposal_presentation_v4.PRESENTATION_TEMPLATE_PATH))

    def test_generates_twelve_editable_slides_with_native_charts(self) -> None:
        """각 장을 이미지 한 장으로 붙이지 않고 텍스트·사진·차트를 편집 가능하게 유지합니다."""
        output = proposal_presentation.create_strategy_proposal_presentation(_sample_report())
        deck = Presentation(output)

        self.assertGreaterEqual(len(deck.slides), 12)
        texts_by_slide = [_slide_text(slide) for slide in deck.slides]
        required_by_slide = {
            1: ('강남 이브닝 스테이 패스', '서울특별시 강남구'),
            2: ('목차',),
            3: ('강남 이브닝 스테이 패스', '야간 동선'),
            4: ('사업 설계', '사업내용', '사업기간', '목표 KPI'),
            5: ('지역별 참고 사례',),
            6: ('지역 적용 방법',),
            7: ('4단계 실행 가이드', '01'),
            8: ('머신러닝 예측값과 목표 KPI',),
            9: ('사례 실적과 목표 KPI 설정 근거',),
            10: ('견적 예시안', '시범 예산',),
            11: ('근거·데이터', '관측 데이터'),
        }
        for slide_number, labels in required_by_slide.items():
            for label in labels:
                self.assertIn(label, texts_by_slide[slide_number - 1], f'{slide_number}장 필수 문구 누락: {label}')
        self.assertNotRegex(texts_by_slide[3], r'\bC\d+\b', '4장에 내부 후보 ID가 노출됐습니다.')
        self.assertTrue(
            any(
                phrase in texts_by_slide[3]
                for phrase in ('사례 실적을 참고한 계획 가정',)
            ),
            '5장에 ML 자연추세와 정책효과를 구분하는 안전 문구가 없습니다.',
        )

        native_text_shapes = [
            shape
            for slide in deck.slides
            for shape in slide.shapes
            if getattr(shape, 'has_text_frame', False) and shape.text.strip()
        ]
        native_charts = [
            shape for slide in deck.slides for shape in slide.shapes if getattr(shape, 'has_chart', False)
        ]
        pictures = [
            shape
            for slide in deck.slides
            for shape in slide.shapes
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE
        ]
        self.assertGreaterEqual(len(native_text_shapes), 90, '편집 가능한 텍스트 개체가 지나치게 적습니다.')
        self.assertGreaterEqual(len(native_charts), 2, 'ML 전망 차트 2개는 네이티브 PowerPoint 차트여야 합니다.')
        self.assertGreaterEqual(len(pictures), 1, '템플릿의 지역 사진 프레임이 유지되어야 합니다.')
        self.assertIn('감사합니다', texts_by_slide[-1])
        self.assertIn('머신러닝 예측치', '\n'.join(texts_by_slide[9:]))
        self.assertNotRegex('\n'.join(texts_by_slide), r'…|\.{3}|자연추세')
        for slide_number, slide_text in enumerate(texts_by_slide, start=1):
            self.assertTrue(slide_text.strip(), f'{slide_number}장이 통이미지 또는 빈 슬라이드입니다.')

    def test_missing_optional_image_and_ml_data_keeps_twelve_slide_structure(self) -> None:
        """사진 URL이나 ML 전망이 없어도 외부 통신 없이 동일한 템플릿으로 출력합니다."""
        report = _sample_report(with_ml=False)
        report['evidence_sources'] = []
        report['monthly_trend'] = []

        # 선택 자료가 없을 때 생성기가 임의로 네트워크 조회를 시작하지 않는지 함께 확인합니다.
        with patch('httpx.Client.get', side_effect=AssertionError('오프라인 PPT 테스트에서 네트워크를 호출했습니다.')):
            output = proposal_presentation.create_strategy_proposal_presentation(report)

        deck = Presentation(output)
        self.assertGreaterEqual(len(deck.slides), 12)
        self.assertTrue(all(_slide_text(slide).strip() for slide in deck.slides))
        self.assertIn('예측치 미제공', _slide_text(deck.slides[3]))
        self.assertFalse(any(getattr(s, 'has_chart', False) for s in deck.slides[3].shapes))

    def test_approved_template_positions_and_final_decision_copy_are_preserved(self) -> None:
        """출력 때 이미 정돈한 최신 템플릿을 다시 이동하거나 축소하지 않습니다."""
        source = Presentation(str(proposal_presentation_v4.PRESENTATION_TEMPLATE_PATH))
        result = Presentation(proposal_presentation.create_strategy_proposal_presentation(_sample_report()))
        for index, result_index, names in (
            (0, 0, ('title-panel', 'center-top-vertical')),
        ):
            before = {shape.name: shape for shape in source.slides[index].shapes}
            after = {shape.name: shape for shape in result.slides[result_index].shapes}
            for name in names:
                self.assertEqual(
                    tuple(getattr(before[name], attr) for attr in ('left', 'top', 'width', 'height')),
                    tuple(getattr(after[name], attr) for attr in ('left', 'top', 'width', 'height')),
                )

    def test_comparison_uses_selected_case_and_only_plots_observed_yoy(self) -> None:
        """사례 선택을 보존하고 수치가 없을 때는 장식 막대를 사실처럼 남기지 않습니다."""
        report = _sample_report()
        report['strategies'][0]['solution']='문화시설 예약 프로그램'
        report['evidence_sources'].extend([
            {'source_id': 'case:other', 'source_type': 'benchmark_case', 'title': '다른 사례'},
            {'source_id': 'case:selected', 'source_type': 'benchmark_case', 'title': '선정된 공식 문화 프로그램 사례',
             'summary': '공식 운영 결과 요약','source_url':'https://example.go.kr/case',
             'operating_model':'문화시설 이용을 확인한 예약 참여자에게 혜택 제공'},
        ])
        report['planning_decision'] = {
            'selected_candidate_id': 'candidate:a',
            'design_candidates': [{'candidate_id': 'candidate:a', 'case_source_ids': ['case:selected'],
                                   'prerequisites': '참여시설 운영시간과 현장 인증 방식을 협약합니다.'}],
            'candidate_assessments': [{'case_source_id': 'case:selected',
                                      'adaptation': '문화시설 이용을 확인한 참여자에게 지역 상점 후속 혜택을 제공합니다.'}],
        }
        output = Presentation(proposal_presentation.create_strategy_proposal_presentation(report))
        text = _slide_text(output.slides[4])
        self.assertIn('선정된 공식 문화 프로그램 사례', text)
        self.assertIn('문화시설 이용을 확인한', text)
        self.assertIn('핵심 운영 참고', text)
        self.assertNotIn('peer-visitors-yoy-index', [shape.name for shape in output.slides[4].shapes])
        report['observed_findings'].append({'metric': '전년동월 외지인 방문자 증감률', 'value': '-8.3%'})
        output = Presentation(proposal_presentation.create_strategy_proposal_presentation(report))
        self.assertFalse(any(shape.has_chart for shape in output.slides[4].shapes))

    def test_estimate_and_provenance_do_not_invent_missing_facts(self) -> None:
        """참고 견적을 확정 견적과 구분하고 요청대로 AI 검수 블록을 제외합니다."""
        report = _sample_report()
        report['agent_trace'] = [{'provider': 'qwen', 'status': 'completed'}]
        output = Presentation(proposal_presentation.create_strategy_proposal_presentation(report))
        estimate_text = _slide_text(output.slides[9])
        provenance_text = _slide_text(output.slides[10])
        self.assertIn('실제 액수와 다를 수 있습니다', estimate_text)
        self.assertNotIn('2.40억 원', estimate_text)
        self.assertNotIn('AI 기획·검수', provenance_text)
        self.assertNotIn('이번 출력: Gemma', provenance_text)
        self.assertNotIn('이번 출력: OpenAI', provenance_text)
        self.assertIn('RandomForestRegressor', '\n'.join(_slide_text(s) for s in list(output.slides)[9:]))

    def test_missing_template_fails_instead_of_silent_legacy_fallback(self) -> None:
        """배포 누락을 구형 출력으로 숨기지 않고 즉시 명확한 오류로 드러냅니다."""
        with tempfile.TemporaryDirectory() as temp_directory:
            missing_path = Path(temp_directory) / 'missing-template.pptx'
            with patch.object(proposal_presentation_v4, 'PRESENTATION_TEMPLATE_PATH', missing_path):
                with self.assertRaises((FileNotFoundError, ValueError)):
                    proposal_presentation_v4.create_strategy_proposal_presentation(_sample_report())


if __name__ == '__main__':
    unittest.main()
