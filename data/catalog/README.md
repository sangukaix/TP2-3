# 지역 데이터 카탈로그

`data/raw/`는 제공기관 원본을 보관하는 읽기 전용 영역입니다. 이 폴더는 원본을 수정하지 않고, 어느 지역 원본을 어떤 ML 어댑터로 읽을지와 출처 상태를 기록합니다.

## 새 지역 추가 순서

1. 공식 ZIP/CSV를 `data/raw/<시도>/<시군구>/`에 원본 그대로 둡니다.
2. `region_data_registry.csv`에 지역 코드·경로·출처 상태를 한 줄 추가합니다.
3. 아래 명령으로 7개 Target, 월 연속성, 기간, 출처 정보를 점검합니다.

```powershell
.\backend\.venv\Scripts\python.exe -m ai_server.ml.scripts.check_regions --region-code <시군구코드>
```

4. `standard_datalab_csv` 점검이 통과한 뒤 `train_regions`로 학습합니다.
5. 열 정의가 다르면 새 전처리 어댑터를 먼저 만들고, 다른 지역 모델을 복사하지 않습니다.

`source_url`과 `downloaded_at`은 반드시 공식 다운로드 화면·기록을 확인해 보완합니다. `provenance_status=verified` 전에는 출처 보완 경고가 계속 표시됩니다.
