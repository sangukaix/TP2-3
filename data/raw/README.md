# 원본 데이터 보관

- `downloads/`: 관광데이터랩에서 받은 ZIP 원본. 파일명과 내부 파일을 바꾸지 않는다.
- `extracted/`: ZIP에서 꺼낸 CSV/XLSX 원본. 내용·컬럼을 수정하지 않는다.
- `SOURCE_REGISTRY.csv`: 파일별 출처·기간·단위·필터·hash를 기록한다.

자료 종류별로 `visitor`, `spending`, `navigation`, `stay`, `demographics` 하위 폴더를 만들어도 된다. 아직 자료 종류가 불확실하면 `downloads/` 바로 아래에 넣는다.
