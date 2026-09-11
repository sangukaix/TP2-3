# TP2-3 프로젝트 구조 탐색기

발표와 팀 학습을 위해 TP2-3의 폴더·파일 역할과 주요 실행 흐름을 보여주는 별도 Streamlit 도구입니다.

## 실행

프로젝트 루트에서 처음 한 번만 설치합니다.

```powershell
& .\backend\.venv\Scripts\python.exe -m pip install -r project_tree_explorer/requirements.txt
& .\backend\.venv\Scripts\python.exe -m streamlit run project_tree_explorer/app.py --server.port 8501
```

또는 `start-streamlit.ps1`을 실행합니다.

React 관리자 학습 영역의 마지막 `전체 구조` 탭은 이 화면을 표시합니다. `start-dev.ps1`은 Streamlit이 설치된 경우 Backend·AI Server·Frontend와 함께 포트 `8501`도 시작합니다. 다른 PC에서 React의 LAN 주소로 접속하면 같은 개발 PC 호스트의 `8501`을 사용합니다.

## 화면 읽는 순서

1. 상단 **전체 시스템 한눈에 보기**에서 React → API → 검증된 데이터 → Agent → 결과의 책임 경계를 확인합니다.
2. **기능별 실행 구조**에서 사용 기능을 고르고 이전·다음 버튼으로 단계를 이동합니다. 각 단계는 입력, 실제 담당 파일, 처리 함수·데이터·판단 기준, 다음 출력 순서로 설명합니다.
3. **현재 파일 위치**에서 선택한 파일이 폴더 구조의 어디에 있는지 확인합니다.
4. **전체 파일 트리**에서 폴더를 펼쳐 개별 파일 역할을 조회합니다.

이 화면은 프로젝트 코드를 실행하거나 수정하지 않고 현재 파일 구조를 읽어 설명합니다. 숫자는 MySQL·ML, 공식 문서는 RAG, 전략 문장은 LLM이 담당한다는 역할 경계를 화면 상단에 고정해 기획서 생성 과정을 잘못 해석하지 않도록 했습니다.

## CLI 트리

```powershell
& .\backend\.venv\Scripts\python.exe project_tree_explorer\tree_cli.py
```

의존성·캐시 폴더까지 포함하려면 다음 옵션을 사용합니다.

```powershell
& .\backend\.venv\Scripts\python.exe project_tree_explorer\tree_cli.py --include-generated
```

기본 출력에서 `.git`, `node_modules`, Python 가상환경, `__pycache__`, Vite 빌드 결과 같은 폴더는 접어 둡니다. 원본 데이터·모델·문서 폴더는 기본 트리에 포함합니다.
# ML 결과에서 전략까지

상세 화면은 왼쪽 설명 60%, 오른쪽 담당 파일 트리 40%로 함께 표시합니다. 오른쪽에는 현재 경로와 같은 폴더의 코드 파일·역할이 나오며, 추가 파일은 펼쳐 확인합니다. 파일 위치를 보기 위해 탭을 전환할 필요가 없습니다.

읽기 순서: **기능 선택 → 단계 직접 선택 → 처리 과정 상세**. 오른쪽의 `담당 파일 위치` 탭에서 경로를 확인합니다. ML 흐름은 지표를 선택해 현재 단계의 설명을 비교할 수 있습니다. 전체 서비스 개요와 호출 트리는 필요할 때 펼칩니다. 단계 이동 시 강제 스크롤하지 않습니다.

기능별 실행 구조에서 **ML 결과 → 전략**을 선택하면 기존 이전/다음 단계와 현재 파일 트리를 유지하면서 원자료 → 학습 → 추론 → 진단 신호 → 공식 사례 → Qwen/Gemma → 저장·출력의 7단계를 확인할 수 있습니다. 지표별 설명은 `ai_server/ml/module_usage.py`를 관리자 ML 결과 화면과 공유합니다. 계산이나 LLM 호출은 실행하지 않습니다.
