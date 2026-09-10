"""사업 여건 계약. 사용자 입력은 관측 사실/공용 RAG와 분리해 보관합니다."""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Literal
from zipfile import ZipFile, BadZipFile

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader
from pydantic import BaseModel, ConfigDict, Field, model_validator


PLANNING_CONTEXT_MAX_CHARS = 6000
PLANNING_TEXT_FIELDS = ('resources_confirmed', 'resources_possible', 'hard_constraints', 'preferences', 'field_context')


def planning_context_char_count(brief: 'PlanningBrief | dict | None') -> int:
    """LLM에 전달되는 사용자 자유 입력과 첨부 본문의 전체 문자 수입니다."""
    if brief is None:
        return 0
    value = brief if isinstance(brief, dict) else brief.model_dump()
    field_chars = sum(len(str(value.get(field) or '')) for field in PLANNING_TEXT_FIELDS)
    reference_chars = sum(len(str(row.get('text') or '')) for row in value.get('references') or [])
    return field_chars + reference_chars


class BriefReference(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    text: str = Field(min_length=1, max_length=6000)


class PlanningBrief(BaseModel):
    """정해지지 않은 값은 null/unknown으로 유지합니다. 0원이나 확정으로 바꾸지 않습니다."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: Literal[1] = 1
    input_profile: Literal['legacy', 'guided_v1'] = 'legacy'
    business_direction: Literal['auto', 'spend_conversion', 'stay_conversion', 'night_time_experience', 'return_visit'] = 'auto'
    excluded_operations: list[Literal['night_time_experience', 'spend_conversion']] = Field(default_factory=list, max_length=2)
    region_code: str = Field(pattern=r'^\d{2,5}$')
    budget_status: Literal['unknown', 'indicative', 'confirmed'] = 'unknown'
    budget_min_krw: int | None = Field(default=None, ge=1, le=1_000_000_000_000, strict=True)
    budget_max_krw: int | None = Field(default=None, ge=1, le=1_000_000_000_000, strict=True)
    budget_hard_limit: bool = False
    visitor_target_pct: float | None = Field(default=None, ge=0, le=20, allow_inf_nan=False)
    spending_target_pct: float | None = Field(default=None, ge=0, le=30, allow_inf_nan=False)
    schedule_status: Literal['unknown', 'flexible', 'fixed'] = 'unknown'
    start_date: date | None = None
    end_date: date | None = None
    # 빈 입력과 ‘알 수 없음’을 구분해 AI가 시설·인력이 없다고 단정하지 않게 합니다.
    resources_status: Literal['unknown', 'known'] = 'unknown'
    resources_confirmed: str = Field(default='', max_length=1500)
    resources_possible: str = Field(default='', max_length=1500)
    constraints_status: Literal['unknown', 'known'] = 'unknown'
    hard_constraints: str = Field(default='', max_length=2000)
    preferences: str = Field(default='', max_length=1000)
    field_context: str = Field(default='', max_length=2500)
    references: list[BriefReference] = Field(default_factory=list, max_length=3)

    @model_validator(mode='before')
    @classmethod
    def infer_legacy_input_status(cls, value):
        """상태 필드가 없던 기존 브라우저 초안도 내용을 잃지 않고 읽습니다."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if 'resources_status' not in data:
            data['resources_status'] = 'known' if data.get('resources_confirmed') or data.get('resources_possible') else 'unknown'
        if 'constraints_status' not in data:
            data['constraints_status'] = 'known' if data.get('hard_constraints') else 'unknown'
        return data

    @model_validator(mode='after')
    def check_conditions(self):
        if self.input_profile == 'guided_v1':
            import calendar
            if self.schedule_status == 'unknown':
                today = date.today()
                self.start_date = today.replace(day=1)
                end_index = today.year * 12 + today.month - 1 + 2
                end_year, end_month = divmod(end_index, 12)
                self.end_date = date(end_year, end_month + 1, calendar.monthrange(end_year, end_month + 1)[1])
                self.schedule_status = 'fixed'
            if self.business_direction in self.excluded_operations:
                raise ValueError('사업 방향과 제외 조건이 충돌합니다.')
            if self.budget_hard_limit or self.budget_min_krw is not None or self.budget_status == 'confirmed':
                raise ValueError('간편 기획은 참고 예산 총액만 지원합니다.')
            if self.visitor_target_pct is not None or self.spending_target_pct is not None or self.references:
                raise ValueError('간편 기획의 목표는 생성 후 조정하며 첨부자료는 지원하지 않습니다.')
            if self.preferences or self.resources_possible or self.hard_constraints:
                raise ValueError('간편 기획은 선택형 제외 조건과 현장 메모만 지원합니다.')
            if len(self.resources_confirmed) > 300 or len(self.field_context) > 500:
                raise ValueError('활용 자원은 300자, 현장 메모는 500자 이하로 입력하세요.')
            if self.start_date and self.end_date:
                index = self.start_date.year * 12 + self.start_date.month - 1 + 2
                year, month = divmod(index, 12)
                expected = date(year, month + 1, calendar.monthrange(year, month + 1)[1])
                if self.start_date.day != 1 or self.end_date != expected or self.start_date.strftime('%Y%m') < date.today().strftime('%Y%m'):
                    raise ValueError('이번 달 이후 시작 월부터 3개월만 지원합니다.')
        if (self.visitor_target_pct is None) != (self.spending_target_pct is None):
            raise ValueError('방문자와 관광소비 목표율은 둘 다 입력하거나 모두 미정으로 두세요.')
        if self.budget_status == 'unknown':
            if self.budget_min_krw is not None or self.budget_max_krw is not None or self.budget_hard_limit:
                raise ValueError('예산 미정 상태에서는 금액과 상한을 지정할 수 없습니다.')
        elif self.budget_max_krw is None:
            raise ValueError('예산 금액 또는 범위의 최대 금액을 입력해 주세요.')
        if self.budget_min_krw and self.budget_max_krw and self.budget_min_krw > self.budget_max_krw:
            raise ValueError('최소 예산은 최대 예산보다 클 수 없습니다.')
        if self.schedule_status == 'unknown' and (self.start_date or self.end_date):
            raise ValueError('일정 미정 상태에서는 날짜를 지정할 수 없습니다.')
        if self.schedule_status != 'unknown' and not (self.start_date and self.end_date):
            raise ValueError('사업 시작일과 종료일을 모두 입력해 주세요.')
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('사업 종료일은 시작일보다 빠를 수 없습니다.')
        if self.resources_status == 'unknown' and (self.resources_confirmed or self.resources_possible):
            raise ValueError('시설·인력 미정 상태에서는 내용을 입력할 수 없습니다.')
        if self.constraints_status == 'unknown' and self.hard_constraints:
            raise ValueError('필수 조건 미정 상태에서는 내용을 입력할 수 없습니다.')
        if planning_context_char_count(self) > PLANNING_CONTEXT_MAX_CHARS:
            raise ValueError(
                f'현장 정보·조건·선호·참고문서 본문은 합계 {PLANNING_CONTEXT_MAX_CHARS:,}자 이하로 줄여 주세요.'
            )
        return self


def brief_fingerprint(brief: dict | None) -> str:
    if not brief:
        return ''
    return sha256(json.dumps(brief, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def without_reference_text(brief: PlanningBrief | None) -> PlanningBrief | None:
    """생성 뒤 보관·응답되는 조건에서는 첨부 본문을 제거합니다."""
    return brief.model_copy(update={'references': []}) if brief else None


def brief_summary(brief: dict | None) -> str:
    """화면/다운로드용 짧은 조건 요약. 출처 수치가 아닌 사용자 설정임을 명시합니다."""
    if not brief:
        return ''
    amount = brief.get('budget_max_krw')
    budget = f"{amount:,}원" if amount else '미정'
    budget += ' (상한)' if brief.get('budget_hard_limit') else ''
    period = f"{brief['start_date']} ~ {brief['end_date']}" if brief.get('start_date') and brief.get('end_date') else '미정'
    return f"사용자 입력 조건 | 예산 {budget} · 일정 {period}"


def extract_brief_reference(filename: str, content: bytes) -> dict:
    """첨부 문서의 필요한 텍스트만 메모리에서 읽고, 원본은 저장하지 않습니다."""
    if not content or len(content) > 2_000_000:
        raise ValueError('파일은 2MB 이하로 첨부해 주세요.')
    name = Path(filename.replace('\\', '/')).name[:150]
    suffix = Path(name).suffix.lower()
    if suffix in ('.txt', '.md'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = content.decode('cp949')
    elif suffix in ('.docx', '.hwpx', '.xlsx'):
        try:
            with ZipFile(BytesIO(content)) as archive:
                files = archive.infolist()
                if len(files) > 500 or sum(item.file_size for item in files) > 12_000_000:
                    raise ValueError('압축 해제 크기가 너무 큰 문서는 첨부할 수 없습니다.')
            if suffix == '.docx':
                document = Document(BytesIO(content))
                text = '\n'.join([p.text for p in document.paragraphs] + [
                    ' | '.join(c.text for c in row.cells) for t in document.tables for row in t.rows
                ])
            elif suffix == '.hwpx':
                text = _extract_hwpx_text(BytesIO(content))
            else:
                text = _extract_xlsx_text(BytesIO(content))
        except (BadZipFile, KeyError) as exc:
            raise ValueError('올바른 Word·한글(HWPX)·Excel 파일을 첨부해 주세요.') from exc
    elif suffix == '.pdf':
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError('암호가 설정된 PDF는 텍스트를 읽을 수 없습니다.')
            text = '\n'.join(page.extract_text() or '' for page in reader.pages[:40])
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('텍스트를 읽을 수 있는 PDF를 첨부해 주세요.') from exc
    else:
        raise ValueError('한글(HWPX), Word(DOCX), PDF, TXT, Excel(XLSX) 파일을 첨부해 주세요. HWP는 HWPX 또는 PDF로 저장해 주세요.')
    text = text.replace('\x00', '').strip()
    if not text:
        raise ValueError('문서에서 텍스트를 찾지 못했습니다.')
    if len(text) > 6000:
        raise ValueError('문서 내용이 6,000자를 넘습니다. 필요한 부분만 별도 문서로 첨부해 주세요.')
    return BriefReference(name=name, text=text).model_dump()


def _extract_hwpx_text(buffer: BytesIO) -> str:
    """HWPX는 ZIP 안 XML 문서라 외부 변환기 없이 본문 텍스트만 읽을 수 있습니다."""
    import xml.etree.ElementTree as etree

    with ZipFile(buffer) as archive:
        sections = sorted(name for name in archive.namelist() if name.startswith('Contents/section') and name.endswith('.xml'))
        if not sections:
            raise ValueError('본문이 없는 HWPX 파일입니다.')
        return '\n'.join(''.join(element.itertext()) for name in sections for element in [etree.fromstring(archive.read(name))])


def _extract_xlsx_text(buffer: BytesIO) -> str:
    """Excel은 첫 10개 시트·각 500행만 읽어, 참고자료 처리 시간을 제한합니다."""
    workbook = load_workbook(buffer, read_only=True, data_only=True)
    rows: list[str] = []
    try:
        for worksheet in workbook.worksheets[:10]:
            rows.append(f'[{worksheet.title}]')
            for row in worksheet.iter_rows(max_row=500, values_only=True):
                values = [str(value).strip() for value in row[:50] if value is not None and str(value).strip()]
                if values:
                    rows.append(' | '.join(values))
    finally:
        workbook.close()
    return '\n'.join(rows)
