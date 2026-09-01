# 전국 시군구 데이터·사례 저장 구조

## 1. 먼저 구분할 것

| 종류 | 현재 위치 | 쓰임 | OpenAI 전달 방식 |
|---|---|---|---|
| 월별 수치 원본 | `data/raw/<시도>/<시군구>/` | 방문자·소비·체류·검색 ML 학습 | 전체 원본을 보내지 않음 |
| 지역 등록표 | `data/catalog/region_data_registry.csv` | 지역코드·경로·출처 검증 상태 | 보내지 않음 |
| 전처리 월별 수치 | `data/processed/` → 운영 시 MySQL | 대시보드·정확한 수치 조회 | 선택 지역 요약만 전달 |
| 저장 ML 모델 | `artifacts/ml/<region_code>/` | 지역별 예측 | 예측 결과·오차만 전달 |
| 공식 사례 카드 | `data/rag/official_case_studies.jsonl` | 운영 방식·예산·성과 비교 | 관련 사례 Top-K만 전달 |
| 공식 문서 Chunk | `data/chroma/` | RAG 의미 검색 | 관련 Chunk Top-K만 전달 |
| 기획안·작업 상태 | MySQL + `storage/strategy_documents/` | 재조회·다운로드·재시작 복구 | 필요한 현재 기획안만 전달 |

전국 월별 수치가 많아지면 지역 비교와 지역별 ML 학습은 좋아진다. 그러나 정책 사례는
자동으로 늘지 않는다. 지자체 보도자료·예산서·성과평가서를 별도 검수해 사례 카드와 RAG에
등록해야 Case Scout가 더 많은 실행 사례를 비교할 수 있다.

## 2. 현재 공식 사례 4건

1. 전라남도 강진군: 반값여행 지역환급
2. 전국 인구감소지역 34곳: 디지털 관광주민증과 교통·숙박·상점 할인
3. 야간관광 특화도시 10곳: 상설 야간 콘텐츠·경관·교통·안전 운영
4. 전주시: 2026년 야간관광 특화도시 예산 편성

파일은 `data/rag/official_case_studies.jsonl`이며, 다음 명령으로 필수 필드·HTTPS URL·중복 ID를 확인한다.

```powershell
python -m ai_server.app.scripts.check_case_registry
```

## 3. 수백 개 시군구로 늘릴 때

```text
공식 다운로드/API
  └─ data/raw/<시도>/<시군구>/              # 원본 불변
       └─ region_data_registry.csv 등록
            └─ check_regions.py              # 열·기간·월 연속성·출처 점검
                 └─ 공통 전처리
                      ├─ MySQL monthly_tourism_metrics  # 운영 조회
                      └─ artifacts/ml/<region_code>/    # 지역별 Joblib

공식 정책·예산·성과 문서
  └─ 출처·기간·성과 의미를 사람이 검수
       ├─ official_case_studies.jsonl         # 비교 가능한 사례 카드
       └─ ChromaDB tourism_official_docs      # 긴 문서 Chunk
```

운영 MySQL의 월별 수치 테이블은 `region_code + year_month + metric_code`를 유일 키로 두는
긴 형식(long format)이 적합하다. 새 지표가 추가되어도 열을 계속 늘리지 않고 행으로 적재할 수 있다.

```text
monthly_tourism_metrics
  region_code, year_month, metric_code, value, unit,
  source_id, source_period, loaded_at
  UNIQUE(region_code, year_month, metric_code, source_id)
```

현재 TP2-3는 파일 기반 전처리·Joblib 학습과 일부 MySQL 보고서 저장까지 구현되어 있다.
전국 수치의 MySQL 일괄 적재는 원본 출처 검증이 끝난 지역부터 별도 마일스톤으로 진행한다.

## 4. AWS 전환 시

| 로컬 개발 | AWS 운영 예정 |
|---|---|
| `data/raw`, `data/processed` | S3 버킷, 원본/전처리 prefix 분리 |
| MySQL 로컬 | Amazon RDS MySQL |
| `artifacts/ml` | S3 모델 저장 + EC2 로컬 캐시 |
| `data/chroma` | EC2 영속 볼륨 또는 운영 Vector DB |
| `storage/strategy_documents` | S3 문서 저장 |

한 요청에서 전국 데이터를 모두 읽거나 LLM에 모두 보내지 않는다. 선택 지역, 같은 기준의 비교지역
집계, 관련 공식 사례 Top-K만 가져와야 응답시간·토큰비·근거 정확도를 함께 관리할 수 있다.

