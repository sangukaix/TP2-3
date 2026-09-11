"""저장 기획안과 Word/PPT 캐시가 같은 내용·출력 버전을 가리키는지 검증합니다."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_server.app import main, strategy_store


class _FakeCursor:
    """문서 캐시 테스트에 필요한 MySQL SELECT·UPDATE만 흉내 냅니다."""

    def __init__(self, state: dict) -> None:
        self.state = state
        self.fetchone_value = None
        self.queries: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.queries.append((sql, params))
        normalized = ' '.join(sql.split())
        if normalized.startswith('SELECT report_json FROM strategy_reports'):
            self.fetchone_value = {'report_json': self.state['report_json']}
        elif normalized.startswith('SELECT word_path, report_json'):
            self.fetchone_value = {
                'word_path': self.state.get('word_path'),
                'report_json': self.state['report_json'],
            }
        elif normalized.startswith('SELECT ppt_path, report_json'):
            self.fetchone_value = {
                'ppt_path': self.state.get('ppt_path'),
                'report_json': self.state['report_json'],
            }
        elif normalized.startswith('UPDATE strategy_reports SET word_path='):
            self.state['word_path'] = params[0]
        elif normalized.startswith('UPDATE strategy_reports SET ppt_path='):
            self.state['ppt_path'] = params[0]

    def fetchone(self):
        return self.fetchone_value


class _FakeConnection:
    """같은 상태를 여러 저장소 호출에서 공유하는 테스트 연결입니다."""

    def __init__(self, state: dict) -> None:
        self.test_cursor = _FakeCursor(state)

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.test_cursor


class StrategyDocumentCacheStoreTests(unittest.TestCase):
    """저장소가 수정 원문과 낡은 렌더 파일을 섞지 않는지 확인합니다."""

    def test_direct_server_connection_reads_project_env(self):
        values = {
            'MYSQL_HOST': 'db.internal', 'MYSQL_PORT': '3307',
            'MYSQL_USER': 'tourism_writer', 'MYSQL_PASSWORD': 'secret-for-test',
            'MYSQL_DATABASE': 'tourism_test',
        }
        with patch('ai_server.app.strategy_store.load_project_env', return_value=values) as load_env, \
                patch('pymysql.connect') as connect:
            strategy_store._connect()
        load_env.assert_called_once_with(strategy_store.PROJECT_ROOT)
        connect.assert_called_once()
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs['host'], 'db.internal')
        self.assertEqual(kwargs['port'], 3307)
        self.assertEqual(kwargs['user'], 'tourism_writer')
        self.assertEqual(kwargs['database'], 'tourism_test')

    def test_report_update_clears_both_cached_document_paths(self):
        state = {'report_json': {}}
        connection = _FakeConnection(state)
        report = {'region_name': '서울특별시 강남구', 'summary': '수정본', 'strategies': []}

        with patch('ai_server.app.strategy_store._connect', return_value=connection):
            strategy_store.save_strategy_report('report-1', '11680', report)

        sql = connection.test_cursor.queries[0][0]
        self.assertIn('word_path=NULL', sql)
        self.assertIn('ppt_path=NULL', sql)

    def test_cache_requires_matching_report_fingerprint_and_render_version(self):
        state = {'report_json': {'summary': '원본'}}
        connection = _FakeConnection(state)
        with TemporaryDirectory() as directory, \
            patch.object(strategy_store, 'DOCUMENT_DIRECTORY', Path(directory)), \
            patch('ai_server.app.strategy_store._connect', return_value=connection):
            strategy_store.write_document(
                'report-1', 'pptx', b'current-ppt', render_version='strategy-pptx-12-slide-v1'
            )

            self.assertEqual(
                strategy_store.read_document(
                    'report-1', 'pptx', render_version='strategy-pptx-12-slide-v1'
                ),
                b'current-ppt',
            )
            self.assertIsNone(
                strategy_store.read_document('report-1', 'pptx', render_version='next-template')
            )
            state['report_json'] = {'summary': '챗봇 수정본'}
            self.assertIsNone(
                strategy_store.read_document(
                    'report-1', 'pptx', render_version='strategy-pptx-12-slide-v1'
                )
            )

    def test_old_file_without_metadata_is_regenerated_for_versioned_calls(self):
        state = {'report_json': {'summary': '원본'}}
        connection = _FakeConnection(state)
        with TemporaryDirectory() as directory, \
            patch.object(strategy_store, 'DOCUMENT_DIRECTORY', Path(directory)), \
            patch('ai_server.app.strategy_store._connect', return_value=connection):
            path = Path(directory) / 'report-1.docx'
            path.write_bytes(b'legacy-doc')
            state['word_path'] = str(path)

            self.assertEqual(strategy_store.read_document('report-1', 'docx'), b'legacy-doc')
            self.assertIsNone(
                strategy_store.read_document('report-1', 'docx', render_version='strategy-docx-v2')
            )

    def test_old_render_cannot_be_cached_under_a_new_report_fingerprint(self):
        state = {'report_json': {'summary': '수정된 새 기획안'}}
        with TemporaryDirectory() as directory, \
            patch.object(strategy_store, 'DOCUMENT_DIRECTORY', Path(directory)), \
            patch.object(strategy_store, '_connect', return_value=_FakeConnection(state)):
            with self.assertRaisesRegex(ValueError, '변경'):
                strategy_store.write_document('report-1', 'pptx', b'old-ppt',
                                              report_payload={'summary':'이전 기획안'})
            self.assertFalse((Path(directory) / 'report-1.pptx').exists())


class _ReportStub:
    """문서 영속화 함수에 필요한 Pydantic model_dump 계약만 제공합니다."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def model_dump(self, **_: object) -> dict:
        return self.payload


class StrategyDocumentCacheMainTests(unittest.IsolatedAsyncioTestCase):
    """저장·다운로드 흐름이 형식별 렌더 버전을 저장소에 전달하는지 확인합니다."""

    def test_completed_report_writes_versioned_word_and_ppt(self):
        report = _ReportStub({'region_name': '서울특별시 강남구', 'strategies': []})
        with (
            patch('ai_server.app.main.save_strategy_report'),
            patch('ai_server.app.main.create_strategy_proposal_document', return_value=BytesIO(b'docx')),
            patch('ai_server.app.main.create_strategy_proposal_presentation', return_value=BytesIO(b'pptx')),
            patch('ai_server.app.main.write_document') as write_document,
        ):
            main._persist_completed_strategy_report('report-1', '11680', report)

        self.assertEqual(write_document.call_count, 2)
        self.assertEqual(
            write_document.call_args_list[0].kwargs['render_version'],
            main.DOCUMENT_RENDER_VERSIONS['docx'],
        )
        self.assertEqual(
            write_document.call_args_list[1].kwargs['render_version'],
            main.DOCUMENT_RENDER_VERSIONS['pptx'],
        )

    async def test_download_regenerates_when_cache_version_is_stale(self):
        report = {'region_name': '서울특별시 강남구', 'strategies': []}
        with (
            patch('ai_server.app.main.read_document', return_value=None) as read_document,
            patch('ai_server.app.main.read_strategy_report', return_value=report),
            patch('ai_server.app.main.create_strategy_proposal_presentation', return_value=BytesIO(b'new-ppt')),
            patch('ai_server.app.main.write_document') as write_document,
        ):
            response = await main.download_saved_strategy_document('report-1', 'pptx')
            content = b''.join([chunk async for chunk in response.body_iterator])

        self.assertEqual(content, b'new-ppt')
        read_document.assert_called_once_with(
            'report-1', 'pptx', render_version=main.DOCUMENT_RENDER_VERSIONS['pptx']
        )
        write_document.assert_called_once_with(
            'report-1',
            'pptx',
            b'new-ppt',
            render_version=main.DOCUMENT_RENDER_VERSIONS['pptx'],
            report_payload=report,
        )


if __name__ == '__main__':
    unittest.main()
