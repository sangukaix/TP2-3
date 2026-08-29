"""OpenAI·React 학습 페이지가 현재 소스 구조를 자동 탐색하는지 확인합니다."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from ai_server.app import main
from ai_server.app.project_learning_catalog import build_project_learning_catalog


class ProjectLearningCatalogTest(unittest.TestCase):
    def test_openai_catalog_discovers_five_core_agents(self) -> None:
        catalog = build_project_learning_catalog('openai')
        pipeline_ids = {node.id for node in catalog.pipeline}
        self.assertTrue({'EvidenceAgent', 'CaseStudyAgent', 'TransferabilityAgent', 'PlannerAgent', 'ReviewerAgent'} <= pipeline_ids)
        self.assertTrue(any(route['path'].endswith('/assistant') for route in catalog.routes))
        self.assertTrue(all('OPENAI_API_KEY=' not in item['name'] for item in catalog.dependencies))

    def test_react_catalog_discovers_routes_and_source_files(self) -> None:
        catalog = build_project_learning_catalog('react')
        route_paths = {route['path'] for route in catalog.routes if route['method'] == 'PAGE'}
        self.assertTrue({'/dashboard', '/ml-test', '/openai-test', '/react-test'} <= route_paths)
        self.assertTrue(any(file.path == 'frontend/src/App.jsx' for file in catalog.files))
        self.assertTrue(any(item['name'] == 'react' for item in catalog.dependencies))
        self.assertEqual(catalog.architecture['current']['services'][0]['port'], '5176')
        self.assertEqual(catalog.architecture['deployment']['status'], 'planned')
        self.assertTrue(any(item['path'] == 'src/pages/' for item in catalog.folder_tree))

    def test_catalog_endpoint_returns_current_structure(self) -> None:
        with TestClient(main.app) as client:
            response = client.get('/ai/v1/learning/react')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['topic'], 'react')

    def test_chat_endpoint_uses_server_key_and_structured_answer(self) -> None:
        answer = {'answer': '설명', 'key_points': [], 'related_files': ['frontend/src/App.jsx'], 'caution': ''}
        with (
            patch.dict(main.ENV_VALUES, {'OPENAI_API_KEY': 'test'}, clear=False),
            patch('ai_server.app.main.ProjectLearningAssistantAgent.answer', AsyncMock(return_value=answer)),
            TestClient(main.app) as client,
        ):
            response = client.post('/ai/v1/learning/react/assistant', json={'question': '라우팅은 어떻게 해?'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['related_files'], ['frontend/src/App.jsx'])


if __name__ == '__main__':
    unittest.main()
