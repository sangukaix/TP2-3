"""ML 학습 챗봇이 실제 카탈로그만 전달하고 API 키를 노출하지 않는지 확인합니다."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from ai_server.app import main
from ai_server.app.agents.ml_learning_assistant_agent import MlLearningAssistantAgent


class MlLearningAssistantTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_receives_catalog_and_explicit_rag_boundary(self) -> None:
        """Agent 입력에 모델 정보와 현재 RAG 미사용 사실이 함께 들어갑니다."""
        expected = {'answer': '답변', 'key_points': [], 'related_modules': [], 'caution': ''}
        with patch(
            'ai_server.app.agents.ml_learning_assistant_agent.create_structured_response',
            AsyncMock(return_value=expected),
        ) as request:
            result = await MlLearningAssistantAgent(env_values={
                'OPENAI_API_KEY': 'test', 'OPENAI_ML_CHAT_MODEL': 'test-model',
            }).answer(
                learning_region={'region_code': '11680', 'modules': [{'id': 'visitors'}]},
                question='어떤 모델을 사용했어?', history=[],
            )
        payload = request.call_args.kwargs['input_payload']
        self.assertEqual(result['answer'], '답변')
        self.assertEqual(payload['learning_region']['region_code'], '11680')
        self.assertIn('사용하지 않음', payload['implementation_map']['runtime']['rag_role'])
        self.assertEqual(request.call_args.kwargs['model'], 'test-model')
        self.assertEqual(request.call_args.kwargs['reasoning_effort'], 'low')
        self.assertEqual(request.call_args.kwargs['max_output_tokens'], 800)
        self.assertEqual(request.call_args.kwargs['verbosity'], 'low')


class MlLearningAssistantApiTest(unittest.TestCase):
    def test_api_requires_server_side_openai_key(self) -> None:
        """브라우저가 키를 보내지 않으며 서버 키가 없으면 명확한 오류를 반환합니다."""
        with patch.dict(main.ENV_VALUES, {'OPENAI_API_KEY': ''}, clear=False), TestClient(main.app) as client:
            response = client.post('/ai/v1/ml/learning/11680/assistant', json={'question': 'MAE가 뭐야?'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail']['code'], 'OPENAI_KEY_MISSING')

    def test_api_returns_structured_ml_answer(self) -> None:
        """선택 지역의 등록 모델이 있을 때 구조화된 학습 답변을 반환합니다."""
        answer = {'answer': '평균 절대 오차입니다.', 'key_points': ['낮을수록 좋음'],
                  'related_modules': ['evaluation.py'], 'caution': '지표 단위를 함께 봅니다.'}
        with (
            patch.dict(main.ENV_VALUES, {'OPENAI_API_KEY': 'test'}, clear=False),
            patch('ai_server.app.main.MlLearningAssistantAgent.answer', AsyncMock(return_value=answer)),
            TestClient(main.app) as client,
        ):
            response = client.post('/ai/v1/ml/learning/11680/assistant', json={'question': 'MAE가 뭐야?'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['generation_mode'], 'openai')
        self.assertEqual(response.json()['related_modules'], ['evaluation.py'])

    def test_status_endpoint_marks_missing_key_inactive_without_openai_call(self) -> None:
        """키가 없으면 외부 호출 없이 즉시 빨간 Inactive 상태를 돌려줍니다."""
        with patch.dict(main.ENV_VALUES, {'OPENAI_API_KEY': ''}, clear=False), TestClient(main.app) as client:
            response = client.get('/ai/v1/learning/assistant-status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'inactive')


if __name__ == '__main__':
    unittest.main()
