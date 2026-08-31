"""검수한 공식 관광 문서 JSONL을 영속형 ChromaDB에 색인합니다."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import dotenv_values

from ai_server.app.agents.evidence_agent import allowed_domains
from ai_server.app.rag_store import OfficialTourismRagStore


async def index_file(input_path: Path) -> int:
    project_root = Path(__file__).resolve().parents[1]
    env_values = dotenv_values(project_root / '.env')
    documents = [
        json.loads(line)
        for line in input_path.read_text(encoding='utf-8-sig').splitlines()
        if line.strip()
    ]
    rag_path = Path(str(env_values.get('CHROMA_PERSIST_DIRECTORY') or 'data/chroma'))
    if not rag_path.is_absolute():
        rag_path = project_root / rag_path
    store = OfficialTourismRagStore(
        persist_directory=rag_path,
        api_key=str(env_values.get('OPENAI_API_KEY') or ''),
        embedding_model=str(env_values.get('OPENAI_EMBEDDING_MODEL') or 'text-embedding-3-small'),
        allowed_domains=allowed_domains(env_values),
    )
    return await store.index_documents(documents)


def main() -> None:
    parser = argparse.ArgumentParser(description='공식 관광 문서를 ChromaDB에 색인합니다.')
    parser.add_argument('--input', type=Path, default=Path('data/rag/official_documents.jsonl'))
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit(f'입력 파일을 찾지 못했습니다: {args.input}')
    count = asyncio.run(index_file(args.input))
    print(f'색인 완료: {count}개 문서 청크')


if __name__ == '__main__':
    main()
