"""프로젝트 소스를 읽어 OpenAI·React 학습 페이지용 구조 정보를 자동 생성합니다.

비밀값과 소스 전문은 반환하지 않고, 파일명·문서화 문자열·라우트·의존성만 보여 줍니다.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / 'frontend'
AI_APP_ROOT = PROJECT_ROOT / 'ai_server' / 'app'


class LearningNode(BaseModel):
    """다이어그램의 단계 한 개입니다."""
    id: str
    title: str
    role: str
    file: str = ''
    kind: str = 'process'


class LearningFile(BaseModel):
    """학생에게 노출할 안전한 상대경로와 역할입니다."""
    path: str
    role: str
    group: str


class ProjectLearningCatalog(BaseModel):
    """OpenAI/React 페이지가 공유하는 자동 탐색 응답입니다."""
    topic: Literal['openai', 'react']
    title: str
    subtitle: str
    generated_from: list[str]
    summary: list[dict[str, str]] = Field(default_factory=list)
    pipeline: list[LearningNode] = Field(default_factory=list)
    agents: list[dict[str, Any]] = Field(default_factory=list)
    routes: list[dict[str, str]] = Field(default_factory=list)
    files: list[LearningFile] = Field(default_factory=list)
    dependencies: list[dict[str, str]] = Field(default_factory=list)
    principles: list[dict[str, str]] = Field(default_factory=list)
    chatbot_flow: list[LearningNode] = Field(default_factory=list)
    architecture: dict[str, Any] = Field(default_factory=dict)
    folder_tree: list[dict[str, Any]] = Field(default_factory=list)
    update_note: str


def _relative(path: Path) -> str:
    """Windows 절대경로 대신 팀원이 공유 가능한 프로젝트 상대경로를 반환합니다."""
    return path.relative_to(PROJECT_ROOT).as_posix()


def _short_doc(value: str | None, fallback: str) -> str:
    """긴 모듈 설명에서 첫 문장만 뽑아 카드용 역할로 사용합니다."""
    text = re.sub(r'\s+', ' ', value or '').strip()
    return (text.split('。')[0].split('. ')[0] or fallback)[:180]


def _python_classes(path: Path, suffix: str = 'Agent') -> list[dict[str, str]]:
    """AST로 Agent 클래스를 찾아 이름·역할을 자동 추출합니다."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    module_doc = ast.get_docstring(tree)
    result = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith(suffix):
            result.append({
                'id': node.name,
                'name': node.name,
                'role': _short_doc(ast.get_docstring(node), _short_doc(module_doc, 'AI 처리 Agent')),
                'file': _relative(path),
            })
    return result


def _fastapi_routes(path: Path) -> list[dict[str, str]]:
    """FastAPI decorator를 읽어 메서드·경로·함수명을 자동 수집합니다."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    routes = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH'} or not decorator.args:
                continue
            route = decorator.args[0]
            if isinstance(route, ast.Constant) and isinstance(route.value, str):
                routes.append({'method': method, 'path': route.value, 'handler': node.name})
    return routes


def _source_files(root: Path, extensions: set[str]) -> list[Path]:
    """생성물·의존성 폴더는 제외하고 실제 소스만 안정적으로 정렬합니다."""
    ignored = {'node_modules', 'dist', '.git', '__pycache__'}
    return sorted(
        path for path in root.rglob('*')
        if path.is_file() and path.suffix.lower() in extensions and not ignored.intersection(path.parts)
    )


def _ordered_report_agents(agent_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """오케스트레이터의 실제 호출 순서에 맞춰 5개 핵심 Agent를 정렬합니다."""
    source = (AI_APP_ROOT / 'agents' / 'report_orchestrator.py').read_text(encoding='utf-8')
    # import 문이 아니라 실제 생성자 호출 위치를 찾아 병렬 조사 → 검토 흐름과 같은 실행 순서를 반영합니다.
    positions = {row['name']: source.find(f"{row['name']}(") for row in agent_rows}
    core = {'EvidenceAgent', 'CaseStudyAgent', 'TransferabilityAgent', 'PlannerAgent', 'ReviewerAgent'}
    return sorted(
        (row for row in agent_rows if row['name'] in core),
        key=lambda row: positions.get(row['name'], 10**9),
    )


def _build_openai_catalog() -> ProjectLearningCatalog:
    """Agent 파일·FastAPI 경로·환경변수 이름에서 AI 시스템 지도를 만듭니다."""
    agent_files = _source_files(AI_APP_ROOT / 'agents', {'.py'})
    discovered = [row for path in agent_files for row in _python_classes(path)]
    core_agents = _ordered_report_agents(discovered)
    all_routes = _fastapi_routes(AI_APP_ROOT / 'main.py')
    relevant_routes = [route for route in all_routes if any(key in route['path'] for key in ('strategy', 'assistant', 'learning'))]
    env_names = []
    env_example = PROJECT_ROOT / '.env.example'
    if env_example.exists():
        env_names = [
            line.split('=', 1)[0].strip() for line in env_example.read_text(encoding='utf-8').splitlines()
            if line.strip().startswith('OPENAI_') and '=' in line
        ]
    pipeline = [
        LearningNode(id='input', title='사용자 조건', role='선택 지역·예산·기간·시설·필수 조건', file='frontend/src/pages/TourismPlanningPage.jsx', kind='input'),
        LearningNode(id='snapshot', title='공식 데이터 Snapshot', role='관측값과 사용자 조건을 분리해 고정', file='ai_server/app/main.py', kind='data'),
        LearningNode(id='ml', title='ML 전망 근거', role='저장 모델의 기간별 전망·오차·조사 질문 생성', file='ai_server/ml/planning_evidence.py', kind='ml'),
        *[LearningNode(id=row['name'], title=row['name'], role=row['role'], file=row['file'], kind='agent') for row in core_agents],
        LearningNode(id='output', title='구조화 기획안', role='화면 미리보기·MySQL 저장·Word/PPT 출력', file='ai_server/app/main.py', kind='output'),
    ]
    chatbot_flow = [
        LearningNode(id='question', title='사용자 질문', role='설명·공식 사례 조사·기획안 수정 요청', kind='input'),
        LearningNode(id='context', title='현재 업무 Context', role='지역 Snapshot·현재 기획안·최근 대화·사업 조건', file='ai_server/app/agents/chat_assistant_agent.py', kind='data'),
        LearningNode(id='tool', title='선택적 공식 웹 검색', role='허용된 정부·공공기관 도메인만 검색', file='ai_server/app/agents/evidence_agent.py', kind='tool'),
        LearningNode(id='chat', title='TourismChatAssistantAgent', role='explain·research·revise 중 응답 유형 선택', file='ai_server/app/agents/chat_assistant_agent.py', kind='agent'),
        LearningNode(id='response', title='구조화 응답', role='답변·핵심 포인트·출처·적용 전 수정안', kind='output'),
    ]
    files = [
        LearningFile(path=row['file'], role=row['role'], group='Agent') for row in discovered
    ] + [
        LearningFile(path='ai_server/app/agents/report_orchestrator.py', role='5-Agent 호출 순서·캐시·재검수 제어', group='Orchestration'),
        LearningFile(path='ai_server/app/agents/prompts.py', role='Agent 페르소나·근거 규칙·환각 방지 프롬프트', group='Prompt'),
        LearningFile(path='ai_server/app/openai_responses.py', role='Responses API·Structured Outputs·오류 처리 공통 함수', group='OpenAI API'),
        LearningFile(path='ai_server/ml/planning_evidence.py', role='ML 결과를 Agent 공통 근거로 변환', group='ML bridge'),
    ]
    return ProjectLearningCatalog(
        topic='openai', title='OpenAI · Agent AI 구조',
        subtitle='기획안 생성과 챗봇이 어떤 근거·모델·Agent 순서로 작동하는지 실제 코드에서 읽어 보여줍니다.',
        generated_from=['ai_server/app/agents/*.py', 'ai_server/app/main.py', '.env.example'],
        summary=[
            {'label': '기획 Agent', 'value': f'{len(core_agents)}개'},
            {'label': '발견한 AI 클래스', 'value': f'{len(discovered)}개'},
            {'label': '관련 API', 'value': f'{len(relevant_routes)}개'},
            {'label': '모델 설정 키', 'value': f'{len(env_names)}개'},
        ],
        pipeline=pipeline, agents=discovered, routes=relevant_routes, files=files,
        dependencies=[{'name': name, 'role': '서버 환경변수 이름 · 실제 키/값은 표시하지 않음'} for name in env_names],
        principles=[
            {'title': '사실 분리', 'description': '공식 관측값·ML 전망·사용자 조건·AI 제안을 서로 다른 필드로 전달합니다.'},
            {'title': '구조화 출력', 'description': 'JSON Schema로 화면·저장·Word·PPT가 같은 결과 구조를 사용합니다.'},
            {'title': '품질 재검수', 'description': 'Reviewer가 기준 미달로 판단하면 Planner가 피드백을 반영해 한 번 다시 작성합니다.'},
            {'title': '서버 키 보호', 'description': 'OpenAI 키와 프롬프트는 AI Server에만 있고 React로 내려가지 않습니다.'},
        ], chatbot_flow=chatbot_flow,
        update_note='페이지를 열 때 Agent 클래스·FastAPI route·환경변수 이름을 다시 읽습니다. 새 Agent나 API가 같은 구조로 추가되면 목록과 파일 지도가 갱신됩니다.',
    )


def _react_file_role(path: Path) -> tuple[str, str]:
    """폴더와 파일 이름으로 React 소스의 역할을 짧게 분류합니다."""
    relative = _relative(path)
    if '/pages/' in f'/{relative}': group, role = 'Page', 'URL 단위 화면과 화면 상태 관리'
    elif '/components/' in f'/{relative}': group, role = 'Component', '여러 화면에서 재사용하는 UI 컴포넌트'
    elif '/api/' in f'/{relative}': group, role = 'API', 'FastAPI 요청과 응답 오류 처리'
    elif '/features/' in f'/{relative}': group, role = 'Feature', '업무 기능별 상태·검증·전용 UI'
    elif '/assets/' in f'/{relative}': group, role = 'Asset', '화면 이미지·정적 자원'
    else: group, role = 'Core', 'React 앱 시작·라우팅·전역 스타일'
    return group, role


def _react_routes(app_source: str) -> list[dict[str, str]]:
    """App.jsx의 lazy import와 path 분기를 연결해 페이지 라우트를 자동 추출합니다."""
    imports = dict(re.findall(r"const\s+(\w+)\s*=\s*lazy\(\(\)\s*=>\s*import\('([^']+)'\)\)", app_source))
    routes = []
    # 현재 App은 /dashboard를 별도 if가 아니라 기본 Page로 사용하므로 기본 할당도 route로 기록합니다.
    default_page = re.search(r'let\s+Page\s*=\s*(\w+)', app_source)
    if default_page:
        page = default_page.group(1)
        routes.append({'method': 'PAGE', 'path': '/dashboard', 'handler': page, 'file': imports.get(page, '')})
    for match in re.finditer(r"if\s*\(path\s*===\s*'([^']+)'\)\s*Page\s*=\s*([^\r\n]+)", app_source):
        path, assignment = match.group(1), match.group(2).strip()
        direct_page = re.fullmatch(r'(\w+)', assignment)
        component = direct_page.group(1) if direct_page else (
            'LearningArchitecturePage' if 'LearningArchitecturePage' in assignment else 'InlinePage'
        )
        routes.append({'method': 'PAGE', 'path': path, 'handler': component, 'file': imports.get(component, '')})
    return routes


def _development_ports() -> dict[str, str]:
    """start-dev.ps1에서 현재 로컬 실행 포트를 읽어 구조도와 실제 실행값을 맞춥니다."""
    defaults = {'frontend': '5176', 'backend': '8100', 'ai': '8111', 'mysql': '3306'}
    script_path = PROJECT_ROOT / 'start-dev.ps1'
    if not script_path.exists():
        return defaults
    try:
        source = script_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return defaults
    variables = {'frontendPort': 'frontend', 'backendPort': 'backend', 'aiPort': 'ai'}
    for variable, key in variables.items():
        match = re.search(rf'\${variable}\s*=\s*(\d+)', source)
        if match:
            defaults[key] = match.group(1)
    return defaults


def _react_folder_tree(files: list[LearningFile]) -> list[dict[str, Any]]:
    """React 폴더별 파일 수와 대표 파일을 묶어 긴 파일 목록 대신 학습용 트리를 만듭니다."""
    folder_meta = {
        'Page': ('src/pages/', 'URL별 화면·상태·업무 흐름'),
        'Component': ('src/components/', '여러 페이지가 함께 쓰는 UI'),
        'API': ('src/api/', 'FastAPI 요청·응답·오류 처리'),
        'Feature': ('src/features/', '업무 기능별 로직·검증·전용 UI'),
        'Asset': ('src/assets/', '이미지와 정적 자원'),
        'Core': ('src 핵심 파일', '앱 시작·라우팅·전역 스타일'),
    }
    result: list[dict[str, Any]] = []
    for group, (path, role) in folder_meta.items():
        rows = [row for row in files if row.group == group]
        if not rows:
            continue
        result.append({
            'group': group,
            'path': path,
            'role': role,
            'count': len(rows),
            'examples': [row.path.replace('frontend/', '', 1) for row in rows[:4]],
        })
    result.extend([
        {'group': 'Config', 'path': 'package.json', 'role': '라이브러리·개발 명령 관리', 'count': 1, 'examples': ['package.json']},
        {'group': 'Config', 'path': 'vite.config.js', 'role': 'Vite 실행·빌드·/api·/ai 프록시', 'count': 1, 'examples': ['vite.config.js']},
        {'group': 'Build', 'path': 'dist/', 'role': 'npm run build가 만드는 배포용 정적 파일', 'count': 0, 'examples': []},
    ])
    return result


def _build_react_catalog() -> ProjectLearningCatalog:
    """React src와 package.json을 스캔해 폴더·라우트·API·Hook 사용을 보여 줍니다."""
    source_files = _source_files(FRONTEND_ROOT / 'src', {'.jsx', '.js', '.css'})
    files = []
    source_text: dict[Path, str] = {}
    for path in source_files:
        try:
            source_text[path] = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            source_text[path] = ''
        group, role = _react_file_role(path)
        files.append(LearningFile(path=_relative(path), role=role, group=group))
    app_source = source_text.get(FRONTEND_ROOT / 'src' / 'App.jsx', '')
    routes = _react_routes(app_source)
    api_calls = []
    for path, source in source_text.items():
        if '/api/' not in f'/{_relative(path)}':
            continue
        for endpoint in re.findall(r"fetch\(`?([^'`]+)", source):
            api_calls.append({'method': 'FETCH', 'path': endpoint[:120], 'handler': _relative(path)})
    package = json.loads((FRONTEND_ROOT / 'package.json').read_text(encoding='utf-8'))
    dependencies = [
        {'name': name, 'role': version}
        for name, version in {**package.get('dependencies', {}), **package.get('devDependencies', {})}.items()
    ]
    hook_counts = {
        hook: sum(source.count(f'{hook}(') for source in source_text.values())
        for hook in ('useState', 'useEffect', 'useMemo', 'useRef')
    }
    ports = _development_ports()
    pipeline = [
        LearningNode(id='browser', title='브라우저 URL', role='사용자가 페이지 경로로 진입', kind='input'),
        LearningNode(id='vite', title='Vite 개발 서버', role='React 모듈 변환·HMR·/api·/ai proxy', file='frontend/vite.config.js', kind='runtime'),
        LearningNode(id='app', title='App.jsx', role='경로별 페이지를 lazy import하고 Suspense로 로딩', file='frontend/src/App.jsx', kind='router'),
        LearningNode(id='page', title='pages', role='URL 화면·상태·업무 흐름 조합', file='frontend/src/pages', kind='page'),
        LearningNode(id='component', title='components / features', role='공통 UI와 기능별 로직 재사용', file='frontend/src/components', kind='component'),
        LearningNode(id='api', title='api modules', role='Backend·AI Server 호출과 오류 처리', file='frontend/src/api', kind='api'),
        LearningNode(id='server', title='FastAPI', role='지도·원자료·ML·OpenAI·MySQL 결과 반환', kind='server'),
        LearningNode(id='render', title='React 렌더링', role='state 변경 시 필요한 UI만 다시 그림', kind='output'),
    ]
    chatbot_flow = [
        LearningNode(id='input', title='textarea / submit', role='React state에 질문과 최근 대화 보관', kind='input'),
        LearningNode(id='request', title='API module', role='JSON 요청을 /ai endpoint로 전송', file='frontend/src/api', kind='api'),
        LearningNode(id='pending', title='Loading state', role='중복 제출 방지·진행 아이콘·오류 표시', kind='state'),
        LearningNode(id='response', title='구조화 응답', role='answer·key points·관련 파일을 말풍선으로 표시', kind='data'),
        LearningNode(id='rerender', title='React re-render', role='messages state가 바뀐 부분만 갱신', kind='output'),
    ]
    return ProjectLearningCatalog(
        topic='react', title='React · Vite 구조',
        subtitle='현재 프런트엔드 폴더·라우트·컴포넌트·API 흐름을 실제 src와 package.json에서 다시 읽어 보여줍니다.',
        generated_from=['frontend/src/**/*', 'frontend/package.json', 'frontend/vite.config.js'],
        summary=[
            {'label': '소스 파일', 'value': f'{len(source_files)}개'},
            {'label': '페이지 route', 'value': f'{len(routes)}개'},
            {'label': 'API 호출 패턴', 'value': f'{len(api_calls)}개'},
            {'label': 'React Hook 사용', 'value': f'{sum(hook_counts.values())}회'},
        ], pipeline=pipeline, routes=[*routes, *api_calls], files=files, dependencies=dependencies,
        principles=[
            {'title': '페이지 단위 lazy loading', 'description': '처음부터 지도·그래프·보고서 코드를 모두 받지 않고 필요한 페이지를 불러옵니다.'},
            {'title': '컴포넌트 재사용', 'description': 'WorkspaceShell·지역 선택기·챗봇·기획 조건 요약을 공통 컴포넌트로 사용합니다.'},
            {'title': 'state와 API 분리', 'description': '페이지는 화면 상태, api 폴더는 HTTP 통신과 오류 처리를 담당합니다.'},
            {'title': '서버 비밀정보', 'description': 'React에는 OpenAI·공공 API 키를 넣지 않고 /api와 /ai만 호출합니다.'},
            {'title': '검증', 'description': '변경 후 oxlint와 Vite production build를 실행합니다.'},
        ], chatbot_flow=chatbot_flow,
        agents=[{'name': hook, 'role': f'{count}회 사용', 'file': 'frontend/src'} for hook, count in hook_counts.items()],
        architecture={
            'current': {
                'label': '현재 · 로컬 개발',
                'status': 'connected',
                'services': [
                    {'id': 'frontend', 'title': 'React Frontend', 'tech': 'React + Vite', 'path': '/', 'port': ports['frontend'], 'role': 'SPA 화면·지도·차트·입력 폼'},
                    {'id': 'backend', 'title': 'Backend Server', 'tech': 'FastAPI + Uvicorn', 'path': '/api/*', 'port': ports['backend'], 'role': '일반 API·MySQL CRUD·지도 경계'},
                    {'id': 'ai', 'title': 'AI Server', 'tech': 'FastAPI + Uvicorn', 'path': '/ai/*', 'port': ports['ai'], 'role': 'ML 추론·RAG·Agent·OpenAI'},
                ],
                'resources': [
                    {'id': 'mysql', 'title': 'MySQL', 'tech': f":{ports['mysql']}", 'owner': 'backend', 'role': '정확한 지표·기획서 저장'},
                    {'id': 'joblib', 'title': 'ML Model', 'tech': 'Joblib', 'owner': 'ai', 'role': '학습 완료 모델 추론'},
                    {'id': 'chroma', 'title': 'Vector DB', 'tech': 'ChromaDB', 'owner': 'ai', 'role': '공식 문서 의미 검색'},
                    {'id': 'openai', 'title': 'OpenAI API', 'tech': 'Responses API', 'owner': 'ai', 'role': '설명·전략·구조화 JSON'},
                ],
            },
            'deployment': {
                'label': '추후 · AWS 배포 예정',
                'status': 'planned',
                'host': 'AWS EC2 Ubuntu',
                'gateway': 'Nginx :80 / :443',
                'routes': [
                    {'path': '/', 'target': 'React dist/'},
                    {'path': '/api/*', 'target': 'Backend :8000'},
                    {'path': '/ai/*', 'target': 'AI Server :8001'},
                ],
                'note': '현재 AWS와 Nginx는 연결 전이며, 배포 단계에서 적용합니다.',
            },
        },
        folder_tree=_react_folder_tree(files),
        update_note='페이지를 열 때 frontend/src, App.jsx, API fetch 패턴과 package.json을 다시 읽습니다. 새 페이지·파일·의존성이 추가되면 새로고침 후 목록과 수가 갱신됩니다.',
    )


def build_project_learning_catalog(topic: str) -> ProjectLearningCatalog:
    """허용된 두 학습 주제만 선택해 프로젝트 구조를 반환합니다."""
    if topic == 'openai':
        return _build_openai_catalog()
    if topic == 'react':
        return _build_react_catalog()
    raise ValueError('LEARNING_TOPIC_UNSUPPORTED')
