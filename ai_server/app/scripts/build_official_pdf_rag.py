"""사용자가 제공한 공식 PDF를 페이지 근거가 남는 RAG 청크로 준비합니다.

원본 PDF는 ``data/rag/source_documents``에 그대로 보관합니다. 이 스크립트는 월별
수치표를 데이터베이스처럼 쓰지 않고, 이미 검수된 페이지 범위에서 정책·운영·지표 해석
문단만 뽑아 ``official_reference_chunks.jsonl``에 저장합니다. 결과는 local_first에서
무료 키워드 RAG로 곧바로 검색되고, 필요할 때만 별도 Chroma 색인 명령으로 의미 검색을
추가할 수 있습니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


# 폰트 경고를 일괄 숨기지 않는다. 실제 한글 추출 실패가 있으므로 페이지별 누락을 보고한다.
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfRagSpec:
    """원문 파일과 사전 검수한 인용 범위를 연결하는 고정 계약입니다."""

    filename: str
    source_id: str
    title: str
    source_url: str
    published_or_updated_at: str
    document_type: str
    page_start: int
    page_end: int
    keywords: tuple[str, ...]
    source_note: str


# 기존 official_reference_documents.jsonl의 사람이 검수한 인용 범위만 확장합니다.
# PDF 전체를 무차별 투입하면 목차·가상 화면·월별 표가 전략 근거로 섞일 위험이 있습니다.
PDF_RAG_SPECS = (
    PdfRagSpec(
        filename='2026_요즘_한국관광_2호_지방공항.pdf',
        source_id='reference:kto:2026:local-airport',
        title='요즘, 한국관광 2호 - 지방공항 연계 지역관광 활성화 방안',
        source_url='https://datalab.visitkorea.or.kr/site/portal/ex/bbs/View.do?bcIdx=311068&cbIdx=1135&pageIndex=1',
        published_or_updated_at='2026-08',
        document_type='policy',
        page_start=34,
        page_end=44,
        keywords=('지방공항', '관문', '체류', '소비', '교통', '관광상품', 'KPI', '시범사업'),
        source_note='지방공항·연계 지역에 관한 자료입니다. 다른 시군구의 사업 효과·예산을 보장하는 근거로 사용하지 않습니다.',
    ),
    PdfRagSpec(
        filename='2026_요즘_한국관광_데이터세미나_2차.pdf',
        source_id='reference:kto:2026:data-seminar',
        title='2026 요즘, 한국관광 데이터 세미나(2차) 자료집',
        source_url='https://datalab.visitkorea.or.kr/site/portal/ex/bbs/View.do?bcIdx=311068&cbIdx=1135&pageIndex=1',
        published_or_updated_at='2026-08-27',
        document_type='data_definition',
        page_start=75,
        page_end=99,
        keywords=('관광데이터', '지표 해석', '기준시점', '이동통신', '신용카드', '숙박', '표본'),
        source_note='향후 공개 예정 기능·가상 예시 화면은 현재 사실이나 예측 근거로 사용하지 않습니다.',
    ),
)

# 발표용 가상 화면·향후 공개 기능을 전략 근거로 잘못 쓰지 않도록 제외합니다. 다만
# "해석 유의사항"처럼 같은 낱말을 경고하는 문장은 문맥이 필요하므로 줄 단위로만 걸러냅니다.
EXCLUDED_LINE_PATTERNS = (
    re.compile(r'^(?:향후\s*)?공개\s*예정'),
    re.compile(r'^(?:가상\s*)?(?:예시\s*)?(?:화면|서비스)'),
    re.compile(r'^(?:목차|CONTENTS?)$', re.IGNORECASE),
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalise_page_text(text: str) -> str:
    """PDF 추출의 불규칙한 공백을 정리하되 문단·쪽수 문맥은 보존합니다."""

    cleaned_lines: list[str] = []
    for raw_line in text.replace('\u00a0', ' ').splitlines():
        line = re.sub(r'\s+', ' ', raw_line).strip()
        if not line or any(pattern.search(line) for pattern in EXCLUDED_LINE_PATTERNS):
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()


def _split_with_overlap(text: str, *, target_chars: int = 900, overlap_chars: int = 140) -> list[str]:
    """문장 경계를 우선해 700~1,000자 정도의 재검색 가능한 청크를 만듭니다."""

    if len(text) <= target_chars:
        return [text]
    pieces = [piece.strip() for piece in re.split(r'(?<=[.!?。])\s+|\n+', text) if piece.strip()]
    chunks: list[str] = []
    current = ''
    for piece in pieces:
        separator = ' ' if current else ''
        if current and len(current) + len(separator) + len(piece) > target_chars:
            chunks.append(current)
            current = (current[-overlap_chars:] + ' ' + piece).strip()
        else:
            current = (current + separator + piece).strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 120]


def _is_usable_page(text: str) -> bool:
    """이미지뿐인 슬라이드·목차·너무 짧은 조각은 RAG 근거에서 제외합니다."""

    hangul_or_latin = sum(character.isalpha() for character in text)
    return len(text) >= 180 and hangul_or_latin >= 80


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build_records(project_root: Path, *, coverage: list[dict] | None = None) -> list[dict[str, object]]:
    """두 PDF의 사전 검수 범위에서만 출처·페이지가 있는 RAG 레코드를 만듭니다."""

    source_dir = project_root / 'data' / 'rag' / 'source_documents'
    records: list[dict[str, object]] = []
    for spec in PDF_RAG_SPECS:
        pdf_path = source_dir / spec.filename
        if not pdf_path.exists():
            raise FileNotFoundError(f'공식 PDF 원문을 찾을 수 없습니다: {pdf_path}')
        pages = PdfReader(str(pdf_path)).pages
        if len(pages) < spec.page_end:
            raise ValueError(f'{spec.filename}: 예상 쪽수({spec.page_end})보다 PDF가 짧습니다.')
        pdf_hash = _sha256(pdf_path)
        accepted_pages, unread_pages, reviewed_summary_pages = [], [], []
        for page_number in range(spec.page_start, spec.page_end + 1):
            text = _normalise_page_text(pages[page_number - 1].extract_text() or '')
            extraction_method = 'pypdf_page_text_curated_range_v1'
            # 2026-09-07: 렌더링한 PDF 76쪽과 직접 대조한 지표 정의 요약.
            # 원문 추출 성공으로 가장하지 않는다. 미래 개방 예정 데이터는 현재 수집 사실이 아니다.
            if spec.source_id == 'reference:kto:2026:data-seminar' and page_number == 76:
                text = (
                    'PDF 76쪽 지표 정의의 시각 검수 요약: 이동통신 내국인 자료는 KT 외지인 기준에 '
                    '시장점유율 모수를 추정하고, 외국인 자료는 SKT 시군구 자료에 법무부 입국자 통계 '
                    '모수를 추정한다. 신용카드 자료는 신한카드의 해외발행 카드 숙박업 결제 자료다. '
                    '따라서 방문 추정과 카드 결제는 대상·표본이 달라 같은 사람 수나 전체 소비로 '
                    '곧바로 연결할 수 없다. 온다의 내·외국인 숙박 예약 자료는 발표 당시 연내 개방 '
                    '예정으로 표시돼 있으며, 현재 프로젝트가 보유한 자료라고 해석하면 안 된다. '
                    '숙박업소 인허가 현황의 자료 기준은 2026년 7월이다. 발표의 비교기간은 '
                    '2023.06~2024.05, 2024.06~2025.05, 2025.06~2026.05로 구분한다. '
                    '이 정의를 프로젝트의 모든 지표에 일괄 적용하지 말고 각 다운로드 원자료의 '
                    '정의·기준기간과 대조한다. 본 요약은 추출 원문이나 사업 효과 수치가 아니다.'
                )
                extraction_method = 'visually_verified_page_summary_20260907'
                reviewed_summary_pages.append(page_number)
            if not _is_usable_page(text):
                unread_pages.append(page_number)
                continue
            accepted_pages.append(page_number)
            for chunk_number, content in enumerate(_split_with_overlap(text), start=1):
                chunk_id = f'{spec.source_id}:page:{page_number:03d}:chunk:{chunk_number:02d}'
                records.append({
                    'source_id': spec.source_id,
                    'parent_source_id': spec.source_id,
                    'chunk_id': chunk_id,
                    'region_code': 'ALL',
                    'region_name': '전국 공통',
                    'document_type': spec.document_type,
                    'case_region': '',
                    'intervention': '',
                    'evidence_strength': 'medium' if spec.document_type == 'policy' else 'high',
                    'title': spec.title,
                    'source_url': spec.source_url,
                    'published_or_updated_at': spec.published_or_updated_at,
                    'page_references': f'PDF {page_number}쪽',
                    'source_file': spec.filename,
                    'source_sha256': pdf_hash,
                    'keywords': list(spec.keywords),
                    'source_note': spec.source_note,
                    'content': content,
                    # 추출 범위·제외 규칙을 코드와 문서에서 검수한 뒤 생성하므로, AI가 바로
                    # 인용 가능한 공식 보조 근거로 표시합니다. 수치 사실·성과 보장은 금지됩니다.
                    'approved_for_rag': True,
                    'extraction_method': extraction_method,
                })
        result = {'source_id': spec.source_id, 'total_pdf_pages': len(pages),
                  'curated_page_range': [spec.page_start, spec.page_end],
                  'accepted_pages': accepted_pages, 'visually_reviewed_summary_pages': reviewed_summary_pages,
                  'unread_or_short_pages': unread_pages,
                  'coverage_complete': not unread_pages}
        if coverage is not None:
            coverage.append(result)
        if unread_pages:
            LOGGER.warning('%s: 검수 범위 중 %s쪽은 텍스트 부족/추출 실패. 전체 문서 색인 완료가 아닙니다.',
                           spec.filename, ','.join(map(str, unread_pages)))
    return records


def write_records(records: Iterable[dict[str, object]], output_path: Path) -> int:
    """항상 같은 순서·UTF-8 JSONL로 저장해 변경과 재생성을 비교할 수 있게 합니다."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialised = [json.dumps(record, ensure_ascii=False, separators=(',', ':')) for record in records]
    output_path.write_text('\n'.join(serialised) + ('\n' if serialised else ''), encoding='utf-8')
    return len(serialised)


def main() -> None:
    project_root = _project_root()
    parser = argparse.ArgumentParser(description='공식 PDF의 검수 범위를 페이지 RAG 청크 JSONL로 준비합니다.')
    parser.add_argument('--audit-only', action='store_true', help='페이지 추출 누락을 점검하고 파일은 변경하지 않는다.')
    parser.add_argument(
        '--output', type=Path,
        default=project_root / 'data' / 'rag' / 'official_reference_chunks.jsonl',
        help='생성할 페이지 청크 JSONL 경로',
    )
    args = parser.parse_args()
    output_path = args.output if args.output.is_absolute() else project_root / args.output
    coverage: list[dict] = []
    records = build_records(project_root, coverage=coverage)
    print(json.dumps({'pdf_extraction_coverage': coverage, 'chunk_count': len(records)}, ensure_ascii=False))
    if args.audit_only:
        return
    count = write_records(records, output_path)
    print(f'공식 PDF RAG 청크 준비 완료: {count}개 ({output_path})')


if __name__ == '__main__':
    main()
