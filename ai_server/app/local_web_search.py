"""무료 검색 API를 통해 공식 도메인 후보만 수집하는 읽기 전용 어댑터입니다.

Qwen·Gemma는 인터넷·파일·쉘에 직접 접근하지 않습니다. 모델이 만든 짧은
검색 질문을 이 모듈이 제한된 외부 API에 전달하고, 허용된 공식 도메인의
제목·URL·검색 요약만 다시 모델에 제공합니다. 원문을 크롤링하거나
검색 요약을 검증 완료 사실로 바꾸지 않는 것이 핵심입니다.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

import httpx


class OfficialWebSearchClient:
    """Tavily 중심의 무료 할당량 검색 API 체인입니다.

    다음 공급자는 앞선 공급자가 공식 도메인 결과를 충분히 찾지 못했거나
    일시 실패했을 때만 호출합니다. 따라서 키를 모두 넣어도 한 검색마다
    모든 할당량을 소진하지 않습니다. 실제 키·응답 원문은 trace에 남기지
    않습니다.
    """

    # Naver 검색 API는 공식 약관상 검색 결과를 독립적으로 노출해야 하는 조건이 있어,
    # LLM의 비가시적 입력 도구에는 넣지 않습니다. 향후 UI 전용 검색 기능으로 별도 검토합니다.
    PROVIDERS = ('tavily', 'brave')

    def __init__(self, *, env_values: dict[str, Any], allowed_domains: list[str]) -> None:
        self.env_values = env_values
        self.allowed_domains = tuple(sorted({str(item).strip().lower() for item in allowed_domains if item}))
        configured = str(env_values.get('LOCAL_WEB_SEARCH_PROVIDERS') or 'tavily')
        self.provider_order = tuple(
            item.strip().lower() for item in configured.split(',') if item.strip().lower() in self.PROVIDERS
        ) or self.PROVIDERS
        self.enabled = str(env_values.get('ENABLE_LOCAL_OFFICIAL_WEB_SEARCH') or 'true').lower() == 'true'
        self.timeout_seconds = max(5.0, float(env_values.get('LOCAL_WEB_SEARCH_TIMEOUT_SECONDS') or 18))
        self.max_queries = max(1, min(3, int(env_values.get('LOCAL_WEB_SEARCH_MAX_QUERIES_PER_REPORT') or 2)))
        self.max_results = max(1, min(6, int(env_values.get('LOCAL_WEB_SEARCH_MAX_RESULTS_PER_QUERY') or 4)))

    def provider_status(self) -> dict[str, Any]:
        """관리자 API에 노출해도 되는 설정 유무만 반환합니다. 키 값은 절대 반환하지 않습니다."""
        providers = {
            'tavily': bool(str(self.env_values.get('TAVILY_API_KEY') or '').strip()),
            'brave': bool(str(self.env_values.get('BRAVE_SEARCH_API_KEY') or '').strip()),
        }
        return {
            'enabled': self.enabled,
            'configured_providers': [name for name in self.provider_order if providers[name]],
            'available': self.enabled and any(providers[name] for name in self.provider_order),
            'max_queries_per_report': self.max_queries,
            'max_results_per_query': self.max_results,
            # 검색 API의 제목·요약은 후보 탐색용이며, 원문 검수 전 RAG 영구 저장을 금지합니다.
            'result_policy': 'official_domain_snippet_only',
        }

    @staticmethod
    def _clean_text(value: Any, *, limit: int = 650) -> str:
        text = re.sub(r'\s+', ' ', html.unescape(str(value or '')).replace('<b>', '').replace('</b>', '')).strip()
        return text[:limit]

    def _is_allowed_url(self, value: Any) -> bool:
        parsed = urlparse(str(value or ''))
        if parsed.scheme != 'https':
            return False
        host = (parsed.hostname or '').lower()
        return any(host == domain or host.endswith(f'.{domain}') for domain in self.allowed_domains)

    @staticmethod
    def _clean_query(value: Any) -> str:
        """모델 출력은 검색 문자열로만 쓰고 제어문자·과도한 길이는 제거합니다."""
        return re.sub(r'\s+', ' ', str(value or '')).strip()[:240]

    def _source(self, *, provider: str, query: str, title: Any, url: Any, snippet: Any,
                published_at: Any = '') -> dict[str, Any] | None:
        source_url = str(url or '').strip()
        if not self._is_allowed_url(source_url):
            return None
        source_title = self._clean_text(title, limit=180) or '공식 웹 검색 결과'
        summary = self._clean_text(snippet)
        if not summary:
            return None
        digest = hashlib.sha256(f'{provider}|{source_url}'.encode('utf-8')).hexdigest()[:16]
        return {
            'source_id': f'free-web:{provider}:{digest}',
            'source_type': 'official_web_search_candidate',
            'title': source_title,
            'source_url': source_url,
            'summary': summary,
            'published_or_updated_at': self._clean_text(published_at, limit=40) or '발행일 미확인',
            'retrieved_at': date.today().isoformat(),
            'search_provider': provider,
            'search_query': query,
            # 검색 API의 짧은 요약을 원문·공식 통계와 같은 강도로 취급하지 않습니다.
            'source_verification': 'search_snippet_only',
        }

    async def _tavily(self, client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
        key = str(self.env_values.get('TAVILY_API_KEY') or '').strip()
        if not key:
            return []
        response = await client.post('https://api.tavily.com/search', json={
            'api_key': key, 'query': query, 'search_depth': 'basic', 'topic': 'general',
            'max_results': self.max_results, 'include_domains': list(self.allowed_domains),
            # 원문 전체를 받아 별도 크롤링하는 대신 검색 API가 제공한 요약만 사용합니다.
            'include_answer': False, 'include_raw_content': False,
        })
        response.raise_for_status()
        return [source for item in (response.json().get('results') or []) if isinstance(item, dict)
                if (source := self._source(provider='tavily', query=query, title=item.get('title'),
                                           url=item.get('url'), snippet=item.get('content'),
                                           published_at=item.get('published_date')))]

    async def _brave(self, client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
        key = str(self.env_values.get('BRAVE_SEARCH_API_KEY') or '').strip()
        if not key:
            return []
        response = await client.get('https://api.search.brave.com/res/v1/web/search', params={
            'q': query, 'count': self.max_results, 'safesearch': 'strict',
        }, headers={'Accept': 'application/json', 'X-Subscription-Token': key})
        response.raise_for_status()
        return [source for item in ((response.json().get('web') or {}).get('results') or []) if isinstance(item, dict)
                if (source := self._source(provider='brave', query=query, title=item.get('title'),
                                           url=item.get('url'), snippet=item.get('description'),
                                           published_at=item.get('age')))]

    async def search_many(self, queries: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """최대 세 개의 Qwen 검색 질문만 수행하고, 안전한 결과와 비밀 없는 실행 trace를 반환합니다."""
        status = self.provider_status()
        if not status['available']:
            return [], [{'agent': 'local_web_search', 'stage': 'official_search', 'status': 'skipped',
                         'reason': 'no_free_search_api_key_configured', 'items': 0}]
        safe_queries = list(dict.fromkeys(filter(None, (self._clean_query(item) for item in queries))))[:self.max_queries]
        results: dict[str, dict[str, Any]] = {}
        trace: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
            for query in safe_queries:
                collected: list[dict[str, Any]] = []
                for provider in status['configured_providers']:
                    try:
                        collector = getattr(self, f'_{provider}')
                        provider_results = await collector(client, query)
                        collected.extend(provider_results)
                        trace.append({'agent': 'local_web_search', 'stage': 'official_search', 'status': 'completed',
                                      'provider': provider, 'items': len(provider_results), 'query_length': len(query)})
                    except httpx.HTTPStatusError as exc:
                        # 401/429 등은 다음 무료 공급자로만 넘기며 키·서버 응답은 기록하지 않습니다.
                        trace.append({'agent': 'local_web_search', 'stage': 'official_search', 'status': 'failed',
                                      'provider': provider, 'items': 0, 'error_code': f'HTTP_{exc.response.status_code}'})
                    except httpx.HTTPError:
                        trace.append({'agent': 'local_web_search', 'stage': 'official_search', 'status': 'failed',
                                      'provider': provider, 'items': 0, 'error_code': 'NETWORK_ERROR'})
                    if len({item['source_url'] for item in collected}) >= 2:
                        break
                for item in collected:
                    results[item['source_url']] = item
        return list(results.values()), trace
