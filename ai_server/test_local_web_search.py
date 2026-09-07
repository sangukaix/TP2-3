"""무료 공식 검색 도구가 키·도메인·결과 경계를 지키는지 네트워크 없이 검증합니다."""

from __future__ import annotations

import unittest

from ai_server.app.local_web_search import OfficialWebSearchClient


class OfficialWebSearchClientTests(unittest.IsolatedAsyncioTestCase):
    def client(self, env_values=None):
        return OfficialWebSearchClient(
            env_values=env_values or {},
            allowed_domains=['gangnam.go.kr', 'visitkorea.or.kr'],
        )

    def test_status_never_returns_api_keys(self):
        client = self.client({
            'TAVILY_API_KEY': 'secret-value', 'BRAVE_SEARCH_API_KEY': 'also-secret',
            'LOCAL_WEB_SEARCH_PROVIDERS': 'tavily,brave',
        })
        status = client.provider_status()
        self.assertTrue(status['available'])
        self.assertEqual(status['configured_providers'], ['tavily', 'brave'])
        self.assertNotIn('secret-value', str(status))
        self.assertEqual(status['max_queries_per_report'], 2)

    def test_only_https_allowed_domains_become_sources(self):
        client = self.client()
        accepted = client._source(
            provider='tavily', query='강남구 관광 공식', title='강남구 관광정책',
            url='https://www.gangnam.go.kr/tourism', snippet='공식 사업 운영 내용', published_at='2026-09-01',
        )
        self.assertEqual(accepted['source_type'], 'official_web_search_candidate')
        self.assertEqual(accepted['source_verification'], 'search_snippet_only')
        self.assertIsNone(client._source(provider='tavily', query='x', title='광고',
                                          url='https://untrusted.example/policy', snippet='내용'))
        self.assertIsNone(client._source(provider='tavily', query='x', title='http',
                                          url='http://gangnam.go.kr/policy', snippet='내용'))

    async def test_missing_keys_never_attempt_network(self):
        client = self.client({'ENABLE_LOCAL_OFFICIAL_WEB_SEARCH': 'true'})
        results, trace = await client.search_many(['강남구 관광 공식', '두 번째 질문', '세 번째 질문'])
        self.assertEqual(results, [])
        self.assertEqual(trace[0]['reason'], 'no_free_search_api_key_configured')

    async def test_query_limit_and_control_characters_are_bounded_before_request(self):
        client = self.client({'TAVILY_API_KEY': 'configured', 'LOCAL_WEB_SEARCH_MAX_QUERIES_PER_REPORT': '1'})
        # 실제 네트워크 호출 없이 입력 정규화와 정책 상한만 확인합니다.
        self.assertEqual(client._clean_query('  강남\n관광\t공식  '), '강남 관광 공식')
        self.assertEqual(len(client._clean_query('가' * 400)), 240)
        self.assertEqual(client.max_queries, 1)


if __name__ == '__main__':
    unittest.main()
