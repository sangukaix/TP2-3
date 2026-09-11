"""TP2-3 프로젝트 트리 탐색기에서 공유하는 읽기 전용 유틸리티."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IGNORED_DIRS = {
    '.git',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '__pycache__',
    'node_modules',
    '.venv',
    'venv',
    'dist',
}
SAFE_TEXT_EXTENSIONS = {
    '.css', '.csv', '.html', '.js', '.jsx', '.json', '.md', '.ps1', '.py',
    '.toml', '.ts', '.tsx', '.txt', '.yml', '.yaml',
}

FILE_ROLE_OVERRIDES: dict[str, tuple[str, str]] = {
    'frontend/src/main.jsx': ('화면 시작', 'React 루트 DOM에 App을 mount하고 전역 CSS를 불러옵니다.'),
    'frontend/src/App.jsx': ('화면 라우팅', '`routes.js`가 판정한 공개 경로에 맞춰 lazy-loaded 페이지를 렌더링합니다.'),
    'frontend/src/routes.js': ('라우트 계약', '공개 경로·과거 주소 별칭·404 판정을 한 곳에서 관리합니다.'),
    'frontend/src/components/WorkspaceShell.jsx': ('공통 화면 틀', '상단바·사이드바·모바일 메뉴를 모든 업무 페이지에 씌웁니다.'),
    'frontend/src/components/TourismAssistant.jsx': ('관광 챗봇 UI', '사용자 질문을 받고 AI Server 응답·출처·수정안을 화면에 표시합니다.'),
    'frontend/src/components/WorkspaceAssistantPanel.jsx': ('업무 챗봇 패널', '기획안 화면 오른쪽에서 현재 지역과 보고서에 대한 대화를 제공합니다.'),
    'frontend/src/pages/TourismDashboardPage.jsx': ('대시보드 페이지', '지역 선택, 지도, 지표 카드, 월별 추세 차트와 상세 팝업을 조합합니다.'),
    'frontend/src/pages/TourismPlanningPage.jsx': ('기획 조건 입력', '예산·기간·자원·제약을 입력받아 AI 전략 생성 작업을 등록합니다.'),
    'frontend/src/pages/TourismStrategyPage.jsx': ('전략 결과 페이지', '생성된 구조화 기획안을 미리 보고 저장·Word·PowerPoint 출력을 요청합니다.'),
    'frontend/src/pages/MlTest/LearningSectionNav.jsx': ('관리자 학습 탭', 'ML·OpenAI·React·AI Router·전체 구조 페이지를 같은 탭으로 연결합니다.'),
    'frontend/src/api/dashboardApi.js': ('업무 API 연결', '브라우저의 fetch 요청을 Backend·AI Server endpoint로 연결하고 오류를 정리합니다.'),
    'frontend/src/api/projectLearningApi.js': ('학습 API 연결', '관리자 학습 카탈로그와 학습 챗봇 endpoint를 호출합니다.'),
    'backend/app/main.py': ('일반 Backend 진입점', 'FastAPI로 지도 경계 등 일반 REST API를 제공하고 외부 키를 서버에 숨깁니다.'),
    'ai_server/app/main.py': ('AI Server 진입점', '대시보드·예측·전략 생성·챗봇·문서 출력 API를 오케스트레이션합니다.'),
    'ai_server/app/agents/report_orchestrator.py': ('Agent 오케스트레이터', 'Evidence·Case Scout·Transferability·Planner·Reviewer의 고정 순서와 재검수를 제어합니다.'),
    'ai_server/app/agents/evidence_agent.py': ('Evidence Agent', '선택 지역의 공식 관측·Open API·허용 문서 근거를 수집합니다.'),
    'ai_server/app/agents/case_study_agent.py': ('Case Scout Agent', '공식 관광사업의 운영 방식·예산·관측 결과·적용 조건을 조사합니다.'),
    'ai_server/app/agents/transferability_agent.py': ('Transferability Agent', '선택 지역 조건과 공식 사례를 비교해 적용·제외 조건을 판단합니다.'),
    'ai_server/app/agents/planner_agent.py': ('Planner Agent', '근거와 사업 조건을 하나의 3~6개월 실행 기획안 JSON으로 작성합니다.'),
    'ai_server/app/agents/reviewer_agent.py': ('Reviewer Agent', '출처·수치·기간·실행 가능성·환각 여부를 독립적으로 검수합니다.'),
    'ai_server/app/llm/router.py': ('LLM Router', '작업 유형과 모드에 따라 OpenAI·Qwen·Gemma 사용 경로를 결정합니다.'),
    'ai_server/app/llm/evidence_tools.py': ('근거 도구', 'LLM이 임의 파일·DB를 읽지 못하도록 허용된 읽기 전용 근거 함수만 제공합니다.'),
    'ai_server/ml/region_service.py': ('지역 ML 서비스', '등록된 지역의 저장 모델을 불러와 온라인 예측만 수행합니다.'),
    'ai_server/ml/module_usage.py': ('ML 전략 연결 설명', '7개 Target의 계산·사례 조사·LLM 전달·출력 경로를 관리자 화면과 전체 구조 지도에 공통 제공합니다.'),
    'ai_server/ml/planning_evidence.py': ('기획용 ML 근거', '저장 모델 전망을 기간별 집계·전년 비교·모델 신뢰도·세 묶음의 조사 질문으로 변환합니다.'),
    'ai_server/ml/gangnam_forecast.py': ('공통 지역 예측 엔진', '7개 Target의 Feature 생성·시간순 평가·Joblib 저장과 온라인 재귀 예측을 수행합니다.'),
    'ai_server/ml/train_regions.py': ('지역 ML 학습 CLI', '검증된 지역별 원자료를 시간순으로 학습·평가하고 Joblib을 저장합니다.'),
    'ai_server/ml/horizon_policy.py': ('전망 기간 정책', '일정 입력 여부에 따라 3·6개월 또는 사업 종료월까지 전망 범위를 계산합니다.'),
    'data/catalog/region_data_registry.csv': ('지역 데이터 카탈로그', '원본 경로·지역 코드·출처 상태를 기록해 ML 활성화 가능 여부를 관리합니다.'),
    'data/rag/official_case_studies.jsonl': ('공식 사례 레지스트리', '검수된 관광사업 사례 카드와 원문 출처를 보관합니다.'),
    'start-dev.ps1': ('개발 서버 실행', 'Backend 8100·AI Server 8112·Frontend 5176과 설치된 구조 지도 8501을 중복 없이 시작합니다.'),
    'setup-dev.ps1': ('개발 환경 설치', '팀원 PC에 Python 가상환경·패키지·frontend 의존성을 준비합니다.'),
    'project_tree_explorer/app.py': ('구조 탐색기', '시스템 책임 경계, 기능별 입력·담당 파일·출력, 상세 함수와 전체 트리를 보여 주는 Streamlit 화면입니다.'),
    'project_tree_explorer/tree_cli.py': ('CLI 트리 출력', '프로젝트의 상대경로 폴더·파일 목록을 tree 형식으로 출력합니다.'),
}


@dataclass(frozen=True)
class TreeEntry:
    relative_path: str
    is_dir: bool
    size: int = 0


def scan_project(root: Path = PROJECT_ROOT, include_generated: bool = False) -> list[TreeEntry]:
    """프로젝트 경로를 읽기만 하여 안정적인 상대경로 목록을 반환합니다."""
    ignored = set() if include_generated else DEFAULT_IGNORED_DIRS
    entries: list[TreeEntry] = []

    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in ignored)
        current_path = Path(current)
        if current_path != root:
            entries.append(TreeEntry(current_path.relative_to(root).as_posix(), True))
        for filename in sorted(filenames, key=str.casefold):
            path = current_path / filename
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            entries.append(TreeEntry(path.relative_to(root).as_posix(), False, size))

    return sorted(entries, key=lambda item: (item.relative_path.casefold(), not item.is_dir))


def _children(entries: Iterable[TreeEntry]) -> dict[str, dict]:
    root: dict = {'dirs': {}, 'files': []}
    for entry in entries:
        parts = entry.relative_path.split('/')
        cursor = root
        for part in parts[:-1]:
            cursor = cursor['dirs'].setdefault(part, {'dirs': {}, 'files': []})
        if entry.is_dir:
            cursor['dirs'].setdefault(parts[-1], {'dirs': {}, 'files': []})
        else:
            cursor['files'].append(entry)
    return root


def build_tree_text(entries: list[TreeEntry], root_label: str = 'TP2-3') -> str:
    """CLI와 Streamlit 다운로드에서 함께 사용하는 tree 형식 문자열입니다."""
    tree = _children(entries)
    lines = [f'{root_label}/']

    def render(node: dict, prefix: str) -> None:
        directories = sorted(node['dirs'].items(), key=lambda item: item[0].casefold())
        files = sorted(node['files'], key=lambda item: item.relative_path.casefold())
        children = [(name, True, child) for name, child in directories]
        children.extend((Path(item.relative_path).name, False, item) for item in files)
        for index, (name, is_dir, child) in enumerate(children):
            branch = '└── ' if index == len(children) - 1 else '├── '
            lines.append(f'{prefix}{branch}{name}{"/" if is_dir else ""}')
            if is_dir:
                render(child, prefix + ('    ' if index == len(children) - 1 else '│   '))

    render(tree, '')
    return '\n'.join(lines)


def relative_to_root(path: str | Path, root: Path = PROJECT_ROOT) -> str:
    """사용자가 입력한 경로를 프로젝트 기준의 POSIX 경로로 정규화합니다."""
    candidate = Path(path)
    if candidate.is_absolute():
        candidate = candidate.resolve().relative_to(root.resolve())
    return candidate.as_posix().lstrip('./')


def read_excerpt(relative_path: str, max_lines: int = 32, root: Path = PROJECT_ROOT) -> tuple[int | None, str] | None:
    """비밀 파일·바이너리는 제외하고 발표용 짧은 코드 발췌만 반환합니다."""
    safe_path = relative_to_root(relative_path, root)
    if safe_path in {'.env', '.env.local'} or Path(safe_path).suffix.lower() not in SAFE_TEXT_EXTENSIONS:
        return None
    path = (root / safe_path).resolve()
    try:
        path.relative_to(root.resolve())
        # 원본 CSV·로그가 커도 전체 파일을 메모리에 올리지 않고 발표용 앞부분만 읽습니다.
        with path.open('r', encoding='utf-8') as stream:
            lines = []
            for _ in range(max_lines):
                line = stream.readline()
                if not line:
                    break
                lines.append(line.rstrip('\n\r'))
        line_count = None if path.stat().st_size > 2_000_000 else len(path.read_text(encoding='utf-8').splitlines())
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return line_count, '\n'.join(f'{index:>4} | {line}' for index, line in enumerate(lines, 1))


def path_role(relative_path: str) -> dict[str, str]:
    """폴더 위치를 기준으로 발표에서 사용할 기본 역할을 설명합니다."""
    path = relative_path.replace('\\', '/')
    name = Path(path).name
    if path in FILE_ROLE_OVERRIDES:
        layer, role = FILE_ROLE_OVERRIDES[path]
        return {'layer': layer, 'role': role}
    if path == 'frontend':
        return {'layer': '화면', 'role': 'React + Vite 사용자 인터페이스'}
    if path.startswith('frontend/src/pages/'):
        return {'layer': '화면', 'role': 'URL별 페이지와 화면 상태·업무 흐름'}
    if path.startswith('frontend/src/components/'):
        return {'layer': '화면', 'role': '여러 페이지에서 재사용하는 UI 컴포넌트'}
    if path.startswith('frontend/src/api/'):
        return {'layer': '연결', 'role': '브라우저에서 Backend·AI Server를 호출하는 함수'}
    if path.startswith('backend/'):
        return {'layer': '일반 Backend', 'role': 'FastAPI REST API와 지도·업무 데이터 처리'}
    if path.startswith('ai_server/app/agents/'):
        return {'layer': 'AI Server', 'role': '전략 생성 Agent의 조사·작성·검수 역할'}
    if path.startswith('ai_server/app/llm/'):
        return {'layer': 'AI Server', 'role': 'LLM Provider·도구·구조화 응답 제어'}
    if path.startswith('ai_server/app/'):
        return {'layer': 'AI Server', 'role': '예측·RAG·LLM·보고서 API 오케스트레이션'}
    if path.startswith('ai_server/ml/'):
        return {'layer': '분석·ML', 'role': '시간순 학습·평가·저장 모델·전망'}
    if path.startswith('data_pipeline/'):
        return {'layer': '데이터', 'role': '원본 검증·전처리·전국 비교 데이터 파이프라인'}
    if path.startswith('data/'):
        return {'layer': '데이터', 'role': '원본·처리 결과·카탈로그·공식 RAG 자료'}
    if path.startswith('database/'):
        return {'layer': '저장', 'role': 'MySQL 스키마·적재 관련 파일'}
    if path.startswith('docs/'):
        return {'layer': '문서', 'role': '기획·구조·데이터·검증·의사결정 기록'}
    if path.startswith('project_tree_explorer/'):
        return {'layer': '발표 도구', 'role': '전체 프로젝트 구조를 설명하는 Streamlit·CLI'}
    if path.startswith('storage/'):
        return {'layer': '실행 산출물', 'role': '검증 로그·렌더링 결과·저장 문서'}
    if name == 'start-dev.ps1':
        return {'layer': '실행', 'role': 'Backend·AI Server·Frontend 개발 서버를 함께 시작'}
    if name == 'setup-dev.ps1':
        return {'layer': '실행', 'role': '팀원 PC의 Python·Node 개발 환경 설치'}
    if path == 'requirements.txt':
        return {'layer': '설정', 'role': 'Python 서버 공통 의존성 목록'}
    if path.startswith('frontend/'):
        return {'layer': '화면 설정', 'role': 'Vite·React 패키지와 정적 진입점'}
    return {'layer': '프로젝트', 'role': '프로젝트 설정 또는 공통 파일'}
