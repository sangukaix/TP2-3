"""공식 관광 문서만 저장하는 영속형 ChromaDB RAG 저장소입니다."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


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
    ) -> None:
        self.persist_directory = persist_directory
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.allowed_domains = allowed_domains

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

    async def search(self, *, query: str, region_code: str, region_name: str, top_k: int = 5) -> list[dict[str, Any]]:
        """지역 문서와 ALL 공통 문서를 검색하고 출처 메타데이터를 보존합니다."""
        collection = self._collection()
        if collection.count() == 0:
            return []
        query_embedding = (await self._embeddings([query]))[0]
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(collection.count(), max(top_k * 4, top_k)),
            include=['documents', 'metadatas', 'distances'],
        )
        sources: list[dict[str, Any]] = []
        documents = (result.get('documents') or [[]])[0]
        metadatas = (result.get('metadatas') or [[]])[0]
        distances = (result.get('distances') or [[]])[0]
        for document, metadata, distance in zip(documents, metadatas, distances):
            metadata = metadata or {}
            document_region = str(metadata.get('region_code') or 'ALL')
            if document_region not in ('ALL', region_code) and str(metadata.get('region_name') or '') != region_name:
                continue
            source_url = str(metadata.get('source_url') or '')
            if source_url and not _host_allowed(source_url, self.allowed_domains):
                continue
            sources.append({
                'source_id': str(metadata.get('source_id') or ''),
                'source_type': 'rag',
                'title': str(metadata.get('title') or '공식 관광 문서'),
                'source_url': source_url,
                'published_or_updated_at': str(metadata.get('published_or_updated_at') or ''),
                'document_type': str(metadata.get('document_type') or ''),
                'case_region': str(metadata.get('case_region') or ''),
                'intervention': str(metadata.get('intervention') or ''),
                'evidence_strength': str(metadata.get('evidence_strength') or ''),
                'summary': str(document)[:1200],
                'relevance_score': round(max(0.0, 1.0 - float(distance)), 4),
            })
            if len(sources) >= top_k:
                break
        return sources

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
            for index, start in enumerate(range(0, len(content), 850)):
                chunk = content[max(0, start - 120):start + 850].strip()
                if len(chunk) < 80:
                    continue
                chunks.append(chunk)
                ids.append(f'{source_id}:{index}')
                metadatas.append({
                    'source_id': source_id,
                    'region_code': str(record.get('region_code') or 'ALL'),
                    'region_name': str(record.get('region_name') or 'ALL'),
                    'document_type': str(record.get('document_type') or 'policy'),
                    'case_region': str(record.get('case_region') or ''),
                    'intervention': str(record.get('intervention') or ''),
                    'evidence_strength': str(record.get('evidence_strength') or ''),
                    'title': str(record.get('title') or '공식 관광 문서'),
                    'source_url': source_url,
                    'published_or_updated_at': str(record.get('published_or_updated_at') or ''),
                })
        if not chunks:
            return 0
        embeddings = await self._embeddings(chunks)
        self._collection().upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
        return len(chunks)
