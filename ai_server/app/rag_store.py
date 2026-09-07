"""공식 관광 문서만 저장하는 영속형 ChromaDB RAG 저장소입니다."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from .case_scope import CASE_DOCUMENT_TYPES


def _in_search_scope(metadata: dict, region_code: str, region_name: str, nationwide_cases: bool) -> bool:
    return (str(metadata.get('region_code') or 'ALL') in ('ALL', region_code)
            or str(metadata.get('region_name') or '') == region_name
            or (nationwide_cases and metadata.get('document_type') in CASE_DOCUMENT_TYPES))


def _host_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == domain or host.endswith(f'.{domain}') for domain in allowed_domains)


class OfficialTourismRagStore:
    """월별 수치가 아닌 공식 정책·관광자원·행사 문서만 검색합니다."""

    def __init__(
        self,
        *,
        persist_directory: Path,
        api_key: str,
        embedding_model: str,
        allowed_domains: list[str],
        local_reference_path: Path | None = None,
    ) -> None:
        self.persist_directory = persist_directory
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.allowed_domains = allowed_domains
        # OpenAI 임베딩을 쓰지 않는 local_first에서도, 사람이 검수한 공식 PDF 요약은
        # 검색할 수 있게 JSONL 레지스트리를 별도로 둡니다. 기본 경로는 data/chroma의
        # 형제인 data/rag이며, 테스트나 다른 저장소에서는 명시 경로를 전달할 수 있습니다.
        self.local_reference_path = local_reference_path or (
            self.persist_directory.parent / 'rag' / 'official_reference_documents.jsonl'
        )
        # 긴 공식 PDF는 원본을 Git에 넣지 않고, 페이지·출처를 유지한 청크 레지스트리로
        # 별도 관리합니다. local_first에서는 이 파일도 유료 임베딩 없이 키워드로 검색합니다.
        self.local_chunk_path = self.local_reference_path.with_name('official_reference_chunks.jsonl')

    def _collection(self):
        import chromadb

        self.persist_directory.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.persist_directory))
        return client.get_or_create_collection(
            'tourism_official_docs',
            metadata={'hnsw:space': 'cosine'},
        )

    async def _embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise ValueError('OPENAI_API_KEY가 없어 RAG 임베딩을 만들 수 없습니다.')
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                'https://api.openai.com/v1/embeddings',
                headers={'Authorization': f'Bearer {self.api_key}'},
                json={'model': self.embedding_model, 'input': texts},
            )
        response.raise_for_status()
        return [item['embedding'] for item in response.json()['data']]

    async def search(self, *, query: str, region_code: str, region_name: str, top_k: int = 5,
                     local_only: bool = False, nationwide_cases: bool = False) -> list[dict[str, Any]]:
        """지역 문서와 ALL 공통 문서를 검색하고 출처 메타데이터를 보존합니다."""
        # 이 레지스트리는 원문 PDF의 무결성·쪽수·공식 URL을 함께 기록한 짧은 검수 요약입니다.
        # 숫자 원자료 표를 넣지 않으며, 문서 내부의 지시문을 실행하지 않는 읽기 전용 근거입니다.
        # 짧은 사람 검수 요약과 PDF 페이지 청크를 함께 조회합니다. 청크를 먼저 두어
        # 기획 Agent가 실제 인용 쪽수와 원문 문맥을 확인할 수 있게 합니다.
        local_chunks = self._search_local_references(
            query, region_code, region_name, top_k,
            registry_path=self.local_chunk_path,
            retrieval_method='local_curated_chunk',
            nationwide_cases=nationwide_cases,
        )
        local_summaries = self._search_local_references(
            query, region_code, region_name, top_k,
            registry_path=self.local_reference_path,
            retrieval_method='local_curated_reference',
            nationwide_cases=nationwide_cases,
        )
        local_references = self._merge_sources(local_chunks, local_summaries, top_k=top_k)
        try:
            collection = self._collection()
            collection_count = collection.count()
        except Exception:
            # ChromaDB가 아직 준비되지 않은 개발 PC에서도 검수된 PDF 참고 근거는 계속 조회합니다.
            return local_references[:top_k]
        if collection_count == 0:
            return local_references[:top_k]
        if local_only:
            # 임베딩 API를 몰래 호출하지 않습니다. 키워드 검색임을 명시하고 의미 유사도 점수로 표시하지 않습니다.
            chroma_sources = self._search_local(collection, query, region_code, region_name, top_k, nationwide_cases=nationwide_cases)
            return self._merge_sources(local_references, chroma_sources, top_k=top_k)
        query_embedding = (await self._embeddings([query]))[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(collection.count(), max(top_k * 4, top_k)),
            include=['documents', 'metadatas', 'distances'],
            # 타시도 사례를 검색 전에 포함한다. 현지 시설·정책은 다른 지역 것을 섞지 않는다.
            **({'where': {'$or': [
                {'region_code': {'$in': ['ALL', region_code]}}, {'region_name': region_name},
                {'document_type': {'$in': list(CASE_DOCUMENT_TYPES)}},
            ]}} if nationwide_cases else {}),
        )
        sources: list[dict[str, Any]] = []
        documents = (result.get('documents') or [[]])[0]
        metadatas = (result.get('metadatas') or [[]])[0]
        distances = (result.get('distances') or [[]])[0]
        for document, metadata, distance in zip(documents, metadatas, distances):
            metadata = metadata or {}
            document_region = str(metadata.get('region_code') or 'ALL')
            if not _in_search_scope(metadata, region_code, region_name, nationwide_cases):
                continue
            source_url = str(metadata.get('source_url') or '')
            if not source_url.startswith('https://') or not _host_allowed(source_url, self.allowed_domains):
                continue
            sources.append({
                'source_id': str(metadata.get('source_id') or ''),
                'chunk_id': str(metadata.get('chunk_id') or ''),
                'parent_source_id': str(metadata.get('parent_source_id') or metadata.get('source_id') or ''),
                'page_references': str(metadata.get('page_references') or ''),
                'source_type': 'rag',
                'title': str(metadata.get('title') or '공식 관광 문서'),
                'source_url': source_url,
                'published_or_updated_at': str(metadata.get('published_or_updated_at') or ''),
                'document_type': str(metadata.get('document_type') or ''),
                'region_code': document_region,
                'region_name': str(metadata.get('region_name') or ''),
                'case_region': str(metadata.get('case_region') or ''),
                'intervention': str(metadata.get('intervention') or ''),
                'evidence_strength': str(metadata.get('evidence_strength') or ''),
                'summary': str(document),
                'retrieval_method': 'embedding_similarity',
                'relevance_score': round(max(0.0, 1.0 - float(distance)), 4),
            })
            if len(sources) >= top_k:
                break
        return self._merge_sources(local_references, sources, top_k=top_k)

    @staticmethod
    def _merge_sources(*groups: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        """같은 source_id가 여러 경로에서 나와도 하나로만 전달합니다."""
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            for source in group:
                source_id = str(source.get('source_id') or '')
                # 같은 PDF라도 서로 다른 페이지 청크는 각각 다른 근거입니다. 반면 짧은
                # 검수 요약은 문서당 한 번만 전달해 모델 입력을 불필요하게 늘리지 않습니다.
                dedupe_key = (source_id or f"{source.get('title', '')}|{source.get('source_url', '')}",
                              str(source.get('chunk_id') or ''))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                unique.append(source)
                if len(unique) >= top_k:
                    return unique
        return unique

    def _search_local_references(self, query: str, region_code: str,
                                 region_name: str, top_k: int, *, registry_path: Path,
                                 retrieval_method: str, nationwide_cases: bool = False) -> list[dict[str, Any]]:
        """검수된 공식 PDF 요약·페이지 청크를 무료 키워드 방식으로 검색합니다.

        ChromaDB의 의미 검색과 같은 점수로 해석하지 않습니다. 이 경로는 API 키·임베딩·외부
        네트워크를 사용하지 않아 local_first에서도 근거 문서의 출처를 함께 전달할 수 있습니다.
        """
        if not registry_path.exists():
            return []
        words = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', query.lower()))
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        try:
            lines = registry_path.read_text(encoding='utf-8-sig').splitlines()
        except OSError:
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # 한 행이 훼손돼도 나머지 검수 문서 검색을 멈추지 않습니다.
                continue
            document_region = str(record.get('region_code') or 'ALL')
            if not _in_search_scope(record, region_code, region_name, nationwide_cases):
                continue
            source_url = str(record.get('source_url') or '')
            source_id = str(record.get('source_id') or '')
            content = str(record.get('content') or '').strip()
            # 자동 추출 중 제외된 페이지나 사람이 아직 검수하지 않은 레코드는 전략 근거로
            # 쓰지 않습니다. 기존 검수 요약은 이 필드가 없어도 그대로 호환됩니다.
            if record.get('approved_for_rag') is False:
                continue
            if not source_id or not content or not source_url.startswith('https://'):
                continue
            if not _host_allowed(source_url, self.allowed_domains):
                continue
            keywords = ' '.join(str(item) for item in record.get('keywords') or [])
            searchable = f"{record.get('title', '')} {keywords} {content}".lower()
            matched_terms = sorted(word for word in words if word in searchable)
            if not matched_terms:
                continue
            ranked.append((len(matched_terms), source_id, {
                'source_id': source_id,
                'source_type': 'rag',
                'title': str(record.get('title') or '공식 관광 참고문서'),
                'source_url': source_url,
                'published_or_updated_at': str(record.get('published_or_updated_at') or ''),
                'document_type': str(record.get('document_type') or 'policy'),
                'region_code': document_region,
                'region_name': str(record.get('region_name') or ''),
                'case_region': str(record.get('case_region') or ''),
                'intervention': str(record.get('intervention') or ''),
                'evidence_strength': str(record.get('evidence_strength') or 'medium'),
                'summary': content[:1200],
                'retrieval_method': retrieval_method,
                'matched_terms': matched_terms,
                'page_references': str(record.get('page_references') or ''),
                'source_note': str(record.get('source_note') or ''),
            }))
            if record.get('chunk_id'):
                ranked[-1][2]['chunk_id'] = str(record['chunk_id'])
            if record.get('parent_source_id'):
                ranked[-1][2]['parent_source_id'] = str(record['parent_source_id'])
        ranked.sort(key=lambda row: (-row[0], row[1]))
        return [row[2] for row in ranked[:top_k]]

    def _search_local(self, collection: Any, query: str, region_code: str,
                      region_name: str, top_k: int, *, nationwide_cases: bool = False) -> list[dict[str, Any]]:
        words = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', query.lower()))
        ranked: list[tuple[int, str, dict]] = []
        for offset in range(0, collection.count(), 256):
            page = collection.get(limit=256, offset=offset, include=['documents', 'metadatas'])
            for document, metadata in zip(page.get('documents') or [], page.get('metadatas') or []):
                metadata = metadata or {}
                if not _in_search_scope(metadata, region_code, region_name, nationwide_cases):
                    continue
                url = str(metadata.get('source_url') or '')
                if not url.startswith('https://') or not _host_allowed(url, self.allowed_domains):
                    continue
                text = str(document or '')
                score = sum(word in (str(metadata.get('title', '')) + ' ' + text).lower() for word in words)
                if not score or not metadata.get('source_id'):
                    continue
                source = {**metadata, 'source_type': 'rag', 'summary': text,
                          'retrieval_method': 'local_keyword', 'matched_terms': score}
                ranked.append((score, str(metadata['source_id']), source))
            ranked = sorted(ranked, key=lambda row: (-row[0], row[1]))[:top_k]
        return [row[2] for row in ranked]

    async def index_documents(self, documents: list[dict[str, Any]]) -> int:
        """검증된 문서 레코드를 문단 단위로 나누어 영속 저장합니다."""
        chunks: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []
        for record in documents:
            source_url = str(record.get('source_url') or '')
            content = str(record.get('content') or '').strip()
            if not content or not _host_allowed(source_url, self.allowed_domains):
                continue
            source_id = str(record.get('source_id') or hashlib.sha256(source_url.encode()).hexdigest()[:16])
            # PDF 전처리기가 이미 페이지 문맥을 보존해 만든 청크는 다시 자르지 않습니다.
            # 그래야 검색 결과의 쪽수와 인용 원문 범위가 어긋나지 않습니다.
            prepared_chunks = [(0, content)] if record.get('chunk_id') else [
                (index, content[max(0, start - 120):start + 850].strip())
                for index, start in enumerate(range(0, len(content), 850))
            ]
            for index, chunk in prepared_chunks:
                if len(chunk) < 80:
                    continue
                chunks.append(chunk)
                chunk_id = str(record.get('chunk_id') or f'{source_id}:{index}')
                ids.append(chunk_id)
                metadatas.append({
                    'source_id': source_id,
                    'chunk_id': chunk_id,
                    'parent_source_id': str(record.get('parent_source_id') or source_id),
                    'region_code': str(record.get('region_code') or 'ALL'),
                    'region_name': str(record.get('region_name') or 'ALL'),
                    'document_type': str(record.get('document_type') or 'policy'),
                    'case_region': str(record.get('case_region') or ''),
                    'intervention': str(record.get('intervention') or ''),
                    'evidence_strength': str(record.get('evidence_strength') or ''),
                    'title': str(record.get('title') or '공식 관광 문서'),
                    'source_url': source_url,
                    'published_or_updated_at': str(record.get('published_or_updated_at') or ''),
                    'page_references': str(record.get('page_references') or ''),
                })
        if not chunks:
            return 0
        embeddings = await self._embeddings(chunks)
        self._collection().upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
        return len(chunks)
