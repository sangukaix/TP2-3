import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

// 이 스크립트는 사용자가 승인한 12장 편집형 템플릿을 불러와
// 강남구 실제 데이터·ML 자연추세·공식 사례를 같은 레이아웃에 채운다.
const buildDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(buildDir, "..", "..");
const starterPath = path.join(buildDir, "template-starter.pptx");
const assetDir = path.join(buildDir, "assets");
const outputPath = path.join(projectRoot, "storage", "previews", "강남구_이브닝스테이패스_샘플기획서.pptx");

const FONT = "Noto Sans KR";
const C = {
  black: "#18191B",
  blue: "#004EA2",
  cyan: "#00C1D4",
  orange: "#FF6B00",
  gray: "#6E747B",
  gray2: "#4F555B",
  bg: "#F4F7FA",
  white: "#FFFFFF",
  rule: "#DDE5EC",
};

const presentation = await PresentationFile.importPptx(await FileBlob.load(starterPath));
const slides = presentation.slides.items;

// PPTX를 다시 불러오면 내부 ID가 새로 부여될 수 있으므로,
// 현재 메모리에 있는 실제 개체를 이름으로 직접 찾아 수정한다.
const nameMaps = [];
for (let slideNo = 1; slideNo <= 12; slideNo += 1) {
  nameMaps[slideNo] = new Map(
    slides[slideNo - 1].elements.items
      .filter((item) => item.name)
      .map((item) => [item.name, item]),
  );
}

function objectAt(slideNo, name) {
  const object = nameMaps[slideNo]?.get(name);
  if (!object) throw new Error(`Missing template object: slide ${slideNo}, ${name}`);
  return object;
}

// 기존 텍스트 프레임과 위치·테두리·자동맞춤은 보존하고 내용만 바꾼다.
function setText(slideNo, name, value) {
  objectAt(slideNo, name).text = value;
}

// 한 제목 안의 핵심어를 템플릿의 파랑·청록 강조로 나눌 때 사용한다.
function setRich(slideNo, name, runs, options = {}) {
  const shape = objectAt(slideNo, name);
  shape.text.set([[
    ...runs.map((item) => ({
      run: item.text,
      textStyle: {
        typeface: FONT,
        fontSize: `${item.size ?? options.size ?? 50}px`,
        color: item.color ?? options.color ?? C.black,
        bold: item.bold ?? true,
      },
    })),
  ]]);
  shape.text.style = {
    typeface: FONT,
    fontSize: options.size ?? 50,
    alignment: options.align ?? "left",
    verticalAlignment: options.valign ?? "middle",
    autoFit: "shrinkText",
    wrap: "square",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
}

function clearText(slideNo, names) {
  for (const name of names) setText(slideNo, name, "");
}

async function imageBytes(filePath) {
  const bytes = await fs.readFile(filePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

// 사진은 기존 프레임·자르기·마스크를 모두 보존한 채 원본만 교체한다.
async function replaceImage(slideNo, name, fileName, alt) {
  const image = objectAt(slideNo, name);
  const oldFrame = image.frame;
  const oldCrop = image.crop;
  const oldFit = image.fit;
  const oldGeometry = image.geometry;
  const oldBorderRadius = image.borderRadius;
  const oldRotation = image.rotation;
  const oldFlipHorizontal = image.flipHorizontal;
  const oldFlipVertical = image.flipVertical;
  const oldLockAspectRatio = image.lockAspectRatio;

  image.replace({
    blob: await imageBytes(path.join(assetDir, fileName)),
    contentType: "image/jpeg",
    alt,
    fit: oldFit ?? "cover",
  });
  image.frame = oldFrame;
  image.crop = oldCrop;
  image.geometry = oldGeometry;
  image.borderRadius = oldBorderRadius;
  image.rotation = oldRotation;
  image.flipHorizontal = oldFlipHorizontal;
  image.flipVertical = oldFlipVertical;
  image.lockAspectRatio = oldLockAspectRatio;
}

// 모든 수치·사진·사례의 근거 경로를 발표자 노트에 남겨 검증 가능하게 한다.
function setSources(slideNo, lines) {
  slides[slideNo - 1].speakerNotes.textFrame.setText(`[Sources]\n${lines.map((line) => `- ${line}`).join("\n")}`);
}

// 1. 표지
setText(1, "security-label", "정 책 검 토 용");
setText(1, "cover-title-line1", "강남 이브닝 스테이 패스");
setRich(1, "cover-title-line2", [
  { text: "야간·숙박 전환", color: C.blue, size: 55 },
  { text: " 3개월 시범사업", color: C.black, size: 55 },
], { size: 55, align: "center" });
setText(1, "cover-date", "2026년 09월 02일");
setText(1, "org-title", "서울특별시 강남구");
setText(1, "org-owner", "관광정책 검토용 /\n데이터·AI 샘플");
setText(1, "report-number", "보 고 서  번 호  G N - 2 0 2 6 - 0 1");
setText(1, "report-topic", "식음·쇼핑 소비를\n숙박으로 연결");
setSources(1, [
  "한국관광 데이터랩 강남구 처리본: data/processed/ml/11680/monthly_demand.csv",
  "강남구 모델 메타데이터: artifacts/ml/11680/demand_model.metadata.json",
]);

// 2. 목차
setText(2, "top-brand", "강남구 관광 전략기획 데이터 시스템");
setText(2, "top-date", "2026. 09. 02");
setText(2, "contents-en", "T A B L E   O F   C O N T E N T S");
setText(2, "contents-ko", "목차 안내");
const toc = [
  "데이터 근거와 기획 배경",
  "문제 정의 및 시범사업 목표",
  "참여자와 이용 시나리오",
  "핵심 사업 구성 7가지",
  "3개월 실행 Flow·산출물",
  "유사 지역 비교와 차별점",
  "ML 자연추세·목표 시나리오",
  "예산 산식·성과 측정",
  "5-Agent·공식 근거 파이프라인",
  "기대효과·확대 판단",
];
for (let col = 0; col < 2; col += 1) {
  for (let row = 0; row < 5; row += 1) {
    setText(2, `toc-${col}-${row}-label`, toc[col * 5 + row]);
  }
}
setSources(2, ["본 샘플 기획서의 12장 구성 및 내부 데이터 근거 목차"]);

// 3. 데이터 근거와 기획 배경
setText(3, "section", "S E C T I O N   0 1");
setRich(3, "title", [
  { text: "강한 방문·소비, ", color: C.blue, size: 52 },
  { text: "낮은 숙박 전환", color: C.cyan, size: 52 },
], { size: 52 });
setText(3, "intro", "강남구는 비교 가능한 166개 지역 중 방문 규모 100백분위, 방문자당 국내 관광소비 93.98백분위입니다.\n반면 평균 숙박방문 비율은 3.1167%로 3.61백분위에 머뭅니다.");
setText(3, "decision-title", "이미 확보된 방문·소비 기반");
setText(3, "decision-body", "2026년 7월 순 방문자 1,796만 명,\n외지인 관광소비 4,820억 원을 기록했습니다.");
setText(3, "activation-title", "전환이 필요한 숙박 연결");
setText(3, "activation-body", "식음·쇼핑 소비는 강하지만 숙박업 비중 2.4%로,\n야간 체류와 숙박을 연결할 여지가 큽니다.");
setText(3, "release-label", "식음·쇼핑 소비 비중");
setText(3, "release-value", "84.2%");
setText(3, "release-suffix", "2026.07 실제값");
setText(3, "strategy-label", "평균 숙박방문 비율");
setText(3, "strategy-value", "3.12%");
setText(3, "strategy-suffix", "166개 중 3.61백분위");
await replaceImage(3, "tourism-photo", "01_mice.jpg", "강남 마이스 관광특구 공식 관광 사진");
setSources(3, [
  "data/processed/ml/11680/monthly_demand.csv (2026-07 actual)",
  "data/processed/nationwide/merged_planning_context/regional_planning_context.csv (2025-07~2026-06 comparison)",
  "한국관광공사 국문관광정보 Open API: http://tong.visitkorea.or.kr/cms/resource/13/3464913_image2_1.jpg",
]);

// 4. 문제 정의와 사업 목표
setText(4, "eyebrow", "P R O B L E M   &   P I L O T   O B J E C T I V E");
setText(4, "title", "문제 정의 및\n시범사업 목표");
const features = ["대규모 방문", "식음·쇼핑 84.2%", "숙박비율 하위권", "3개월 검증", "야간 동선", "숙박 인증", "사업자 연계", "성과 측정"];
features.forEach((label, index) => setText(4, `feature-${index}`, label));
setText(4, "body", "강남구의 문제는 관광객이 적다는 것이 아니라, 이미 형성된 식음·쇼핑 방문이 야간 체류와 숙박으로 충분히 이어지지 않는다는 점입니다.\n\n본 시범사업은 18시 이후 동선, 식음·쇼핑 혜택, 실제 숙박 완료 인증을 하나의 패스로 묶고 3개월간 전환율을 측정합니다. 목표는 성과를 가정하는 것이 아니라 중단·보완·확대를 판단할 수 있는 검증 가능한 근거를 만드는 것입니다.");
await replaceImage(4, "city-photo", "02_coex.jpg", "강남구 코엑스 공식 관광 사진");
setSources(4, [
  "data/processed/ml/11680/monthly_demand.csv",
  "data/processed/nationwide/merged_planning_context/regional_planning_context.csv",
  "한국관광공사 국문관광정보 Open API: http://tong.visitkorea.or.kr/cms/resource/43/3590343_image2_1.jpg",
]);

// 5. 참여자와 이용 시나리오
setText(5, "title", "참여자별 역할과 이용 시나리오");
setText(5, "subtitle", "방문 수요를 야간 결제와 실제 숙박 완료까지 연결하는 3자 협업 구조");
setText(5, "audience-pill-0", "타지역 방문객");
setText(5, "audience-body-0", "MICE·문화·쇼핑 방문자가 패스를 신청하고\n18시 이후 제휴 동선을 이용합니다.");
setText(5, "audience-role-0", "행동: 방문 → 야간 소비 → 숙박 인증");
setText(5, "audience-pill-1", "강남구·운영기관");
setText(5, "audience-body-1", "패스 운영, 참여업체 기준 관리, 월별 KPI와\n참여·비참여 집단을 비교합니다.");
setText(5, "audience-role-1", "역할: 품질관리·성과측정·의사결정");
setText(5, "audience-pill-2", "식음·쇼핑·숙박업체");
setText(5, "audience-body-2", "혜택을 제공하고 결제·쿠폰·숙박 완료 데이터를\n정해진 항목으로 제출합니다.");
setText(5, "audience-role-2", "역할: 현장 운영·데이터 협력");
setText(5, "footer-left", "강남 이브닝 스테이 패스 | 3개월 데이터 검증형 시범사업");
setText(5, "footer-right", "Evidence-Driven Tourism Pilot");
setSources(5, ["사용자 입력 조건과 강남구 실제 데이터에서 도출한 운영 시나리오"]);

// 6. 핵심 사업 구성
setText(6, "title", "핵심 사업 구성 7가지");
const functionLabels = [
  "패스 신청: 방문 목적·동행·숙박 여부를 최소 항목으로 등록",
  "야간 동선: 코엑스–가로수길 등 18:00~23:00 추천 루트",
  "연계 혜택: 식음·쇼핑 이용 후 숙박 완료 시 혜택 확정",
];
functionLabels.forEach((label, index) => setText(6, `function-label-${index}`, label));
setText(6, "analysis-tag", "P I L O T   &   M E A S U R E");
setText(6, "function-more-left", "④ 숙박 인증: 예약이 아니라 실제 완료 기준 확인\n⑤ 업체 운영: 참여 기준·정산·민원 대응 매뉴얼\n⑥ 성과 측정: 발급·결제·쿠폰·숙박 전환 월별 추적");
setText(6, "function-more-right", "⑦ 판단 게이트: 3개월 후 중단·보완·확대\n  · 행사일/비행사일 비교\n  · 참여자/비참여자 비교");
await replaceImage(6, "visitor-photo", "03_garosu.jpg", "강남구 신사동 가로수길 공식 관광 사진");
setSources(6, [
  "한국관광공사 국문관광정보 Open API: http://tong.visitkorea.or.kr/cms/resource/61/3566961_image2_1.jpg",
  "사업 구성은 관측값과 공식 야간관광·숙박연계 사례를 바탕으로 설계",
]);

// 7. 3개월 실행 계획
setText(7, "eyebrow", "T H R E E - M O N T H   P I L O T   P L A N");
setRich(7, "title", [
  { text: "3개월 실행 ", color: C.black, size: 49 },
  { text: "Flow 및 산출물", color: C.blue, size: 49 },
], { size: 49 });
const steps = [
  ["STEP 01 · 1~2주", "설계·협약", "대상 방문객과 참여업체 기준을 확정하고,\n수집 동의·KPI·정산 규칙을 설계합니다."],
  ["STEP 02 · 3~4주", "업체 모집·리허설", "식음·쇼핑·숙박업체를 모집하고 인증·쿠폰·\n민원 동선을 현장에서 점검합니다."],
  ["STEP 03 · 2개월차", "시범 운영", "18시 이후 패스를 운영하며 발급·결제·쿠폰·\n숙박 완료 데이터를 주 단위로 확인합니다."],
  ["STEP 04 · 3개월차", "성과 검증", "참여/비참여, 행사/비행사일을 비교하고\n이탈 구간과 비용 대비 성과를 분석합니다."],
];
steps.forEach(([label, title, body], index) => {
  setText(7, `step-${index}-label`, label);
  setText(7, `step-${index}-title`, title);
  setText(7, `step-${index}-body`, body);
});
setText(7, "value-title", "STEP 05 · 중단·보완·확대 의사결정");
setText(7, "value-body", "월별 산출물은 참여업체 명단, 운영 매뉴얼, 패스 발급·이용 데이터, 숙박 완료율, 야간 결제, 쿠폰 사용률, 이슈 로그입니다. 3개월 종료 시 목표 달성 여부뿐 아니라\n어느 동선·업종·시간대에서 전환이 발생했는지 확인하고, 근거가 부족하면 확대하지 않습니다.");
setSources(7, [
  "data/rag/official_case_studies.jsonl: 야간관광 특화도시, 숙박 할인, 야간 축제 사례",
  "본 일정은 3개월 시범사업용 실행안이며 실제 협약·조달 일정에 따라 조정",
]);

// 8. 유사 지역 비교
setText(8, "eyebrow", "P E E R   C O M P A R I S O N   &   D E C I S I O N");
setRich(8, "title", [
  { text: "유사 지역 비교가 가리키는 ", color: C.black, size: 48 },
  { text: "전략", color: C.blue, size: 48 },
], { size: 48 });
const diff = [
  ["01", "방문 규모는 이미 최상위", "강남구 방문자 연인원은 비교 가능한 166개 지역 중 100백분위입니다. 대규모 신규 유입 캠페인보다 기존 방문의 질을 높이는 편이 타당합니다.", "+ 방문 유치보다 전환 우선"],
  ["02", "소비력도 높은 편", "방문자당 국내 관광소비는 26,719원으로 93.98백분위입니다. 강한 식음·쇼핑 소비를 야간 체류와 숙박으로 연결해야 합니다.", "+ 식음·쇼핑 84.2% 활용"],
  ["03", "숙박 전환은 비교 열위", "숙박방문 비율은 송파구 대비 1.60%p, 성남시 대비 1.67%p 낮습니다. 단, 지역 차이는 인과효과가 아닌 비교 신호입니다.", "+ 숙박 완료율 직접 측정"],
  ["04", "작게 검증하고 확대", "자연추세상 방문자는 소폭 증가하지만 소비는 보합입니다. 야간·숙박 전환 시범사업으로 실제 추가 전환이 있었는지 확인합니다.", "+ 3개월 판단 게이트"],
];
diff.forEach(([num, title, body, plus], index) => {
  setText(8, `diff-num-${index}`, num);
  setText(8, `diff-title-${index}`, title);
  setText(8, `diff-body-${index}`, body);
  setText(8, `diff-plus-${index}`, plus);
  setText(8, `diff-plus-orange-${index}`, "+");
});
setSources(8, [
  "data/processed/nationwide/merged_planning_context/regional_planning_context.csv",
  "data/processed/nationwide/merged_planning_context/peer_comparisons.csv",
  "비교지역 선정: 표준화 Euclidean distance; 비교는 인과효과가 아님",
]);

// 9. ML 자연추세와 담당자 입력 목표 시나리오
setText(9, "eyebrow", "M L   N A T U R A L   T R E N D   &   T A R G E T");
setRich(9, "title", [
  { text: "3개월 자연추세와 ", color: C.black, size: 47 },
  { text: "검토 목표", color: C.blue, size: 47 },
], { size: 47 });
setText(9, "intro", "ML은 기존 이력의 자연추세를 예측합니다. 아래 목표선은 정책효과 예측이 아니라, 담당자가 검토를 위해 입력한\n방문 +1%·소비 +2% 샘플 목표를 자연추세에 단순 적용한 값입니다.");
setText(9, "prediction-title", "자연추세: 방문 +0.76% · 소비 보합 · 숙박비율 -2.02%");
setText(9, "prediction-body", "2026.08~10 방문자 합계 5,403만 명, 외지인 관광소비 1.393조 원.\n샘플 목표와의 산술 차이: 방문 +54만 명 · 소비 +279억 원.");
clearText(9, ["rag-title", "rag-body", "tech-tag-0", "tech-tag-1", "tech-tag-2"]);

// 그래프 값은 백만 명 단위이며 자연추세와 목표 가정을 분리해 표시한다.
const forecastChart = slides[8].charts.add("line", {
  position: { left: 106, top: 545, width: 790, height: 245 },
  categories: ["2026.08", "2026.09", "2026.10"],
  series: [
    { name: "ML 자연추세", values: [18.027844, 18.237833, 17.767384], line: { style: "solid", fill: C.blue, width: 3 } },
    { name: "샘플 목표(+1%)", values: [18.208122, 18.420211, 17.945058], line: { style: "solid", fill: C.orange, width: 3 } },
  ],
  legend: { position: "bottom", overlay: false },
  xAxis: { textStyle: { fill: C.gray2, fontSize: 12 }, line: { style: "solid", fill: C.rule, width: 1 } },
  yAxis: {
    numberFormatCode: "0.0",
    textStyle: { fill: C.gray2, fontSize: 12 },
    majorGridlines: { style: "solid", fill: C.rule, width: 1 },
  },
  chartFill: C.bg,
  chartLine: { style: "solid", fill: "none", width: 0 },
  plotAreaFill: C.bg,
  plotAreaLine: { style: "solid", fill: "none", width: 0 },
});
forecastChart.name = "visitor-natural-target-chart";

const chartNote = slides[8].shapes.add({
  geometry: "textbox",
  name: "forecast-chart-note",
  position: { left: 683, top: 538, width: 210, height: 28 },
  fill: "none",
  line: { style: "solid", fill: "none", width: 0 },
});
chartNote.text = "단위: 백만 명 · 정책효과 예측 아님";
chartNote.text.style = {
  typeface: FONT,
  fontSize: 12,
  color: C.orange,
  bold: true,
  alignment: "right",
  verticalAlignment: "middle",
  autoFit: "shrinkText",
  insets: { top: 0, right: 0, bottom: 0, left: 0 },
};
await replaceImage(9, "palace-photo", "04_winter_festa.jpg", "강남 미디어 윈터페스타 공식 관광 사진");
setSources(9, [
  "artifacts/ml/11680/demand_model.metadata.json (demand-v3.0)",
  "data/processed/ml/11680/monthly_demand.csv",
  "ML 자연추세 2026-08~10; 목표선은 방문 +1%, 소비 +2% 사용자 입력 예시이며 정책효과 예측이 아님",
  "한국관광공사 국문관광정보 Open API: http://tong.visitkorea.or.kr/cms/resource/54/3579654_image2_1.jpg",
]);

// 10. 예산 산식과 KPI
setText(10, "eyebrow", "B U D G E T   F O R M U L A   &   K P I");
setRich(10, "title", [
  { text: "예산 산식 및 ", color: C.blue, size: 48 },
  { text: "성과 측정", color: C.cyan, size: 48 },
], { size: 48 });
setText(10, "intro", "총예산을 임의로 단정하지 않고 참여업체 수·패스 발급량·혜택 단가·측정 비용을 변수로 산출합니다.\n희망예산과 견적이 들어오면 범위 안에서 우선순위를 다시 계산합니다.");
setText(10, "dashboard-title", "예산 구성 산식");
setText(10, "dashboard-body", "고정 운영비 + 콘텐츠·행사비 +\n(실사용자 수 × 혜택 단가) + 성과측정비");
setText(10, "analysis-title", "성과 판단 KPI");
setText(10, "analysis-body", "숙박 완료율, 18시 이후 결제, 쿠폰 사용률,\n참여/비참여 및 행사/비행사일 변화");
setText(10, "report-card-title", "예산 확정 원칙");
setText(10, "report-card-body", "수량·단가·운영범위 검증 후 산출");
setText(10, "report-card-orange", "샘플 문서에서 총액 임의 생성 금지");
setText(10, "map-card-title", "공식 사례 참고선");
setText(10, "map-card-body", "전주 2026 야간관광 예산 10억 원");
setText(10, "map-card-orange", "연간 타지역 기준 · 강남 추정치 아님");
await replaceImage(10, "island-photo", "05_kukkiwon.jpg", "강남구 국기원 공식 관광 사진");
setSources(10, [
  "data/rag/official_case_studies.jsonl: 전주 2026 야간관광 사업 예산 사례",
  "공식 사례 금액은 예산 구조 참고선이며 강남구 사업비 추정치가 아님",
  "한국관광공사 국문관광정보 Open API: http://tong.visitkorea.or.kr/cms/resource/96/3567696_image2_1.jpg",
]);

// 11. 5-Agent + OpenAI 파이프라인
setText(11, "eyebrow", "E V I D E N C E   T O   P L A N   P I P E L I N E");
setText(11, "title", "근거가 기획안이 되는\n5-Agent 구조");
const agents = [
  ["① Evidence Agent", "MySQL 실제값·ML 자연추세 정리"],
  ["② Case Scout", "RAG에서 공식 유사 사례·출처 검색"],
  ["③ Transfer Agent", "지역 차이·적용 가능 조건 검토"],
  ["④ Planner Agent", "실행 단계·예산 산식·KPI 설계"],
];
agents.forEach(([title, body], index) => {
  setText(11, `stack-card-${index}-title`, title);
  setText(11, `stack-card-${index}-body`, body);
});
setText(11, "body", "⑤ Reviewer Agent가 관측 사실·ML 예측·목표 가정·추천을 다시 분리하고, 근거 없는 수치와 관광지를 차단합니다.\n\nOpenAI는 이 검증된 근거 묶음을 전달받은 뒤 문장 구성, 대안 비교, 실행안 초안을 담당합니다. MySQL은 사실, ML은 자연추세, RAG는 공식 사례, LLM은 설명과 기획을 맡아 역할을 섞지 않습니다.\n\n최종 출력은 JSON 스키마 검증을 통과한 뒤 PPT·Word 미리보기로 변환됩니다.");
await replaceImage(11, "workspace-photo", "06_coex_plaza.jpg", "강남구 코엑스 동측광장 공식 관광 사진");
setSources(11, [
  "ai_server/app/orchestrator.py 및 관련 Agent·schema 코드",
  "docs/ARCHITECTURE.md, docs/DATA_AND_AI_RULES.md",
  "한국관광공사 국문관광정보 Open API: http://tong.visitkorea.or.kr/cms/resource/56/3467556_image2_1.jpg",
]);

// 12. 기대효과와 확대 판단
setText(12, "title", "기대 효과 및 확대 판단");
setText(12, "expected-pill", "측정 가능한 전환");
setText(12, "expected-body", "숙박 완료율·야간 결제·쿠폰 사용률을 실제값으로\n확인해 사업이 어디에서 작동했는지 설명합니다.");
setText(12, "indicator-pill", "월별 KPI 추적");
setText(12, "service-pill", "3개월 판단 게이트");
setText(12, "service-body", "목표 달성 여부뿐 아니라 비용, 이탈 구간, 업체 운영 가능성을 함께 검토해 중단·보완·확대를 결정합니다.");
setText(12, "service-note", "* 자연추세와 사업 참여자의 실제 결과를 비교하되, 관측 설계가 약하면 인과효과로 표현하지 않습니다.");
setText(12, "service-scope", "의사결정: 증거 우선");
setText(12, "private-pill", "근거 확보 후 확장");
setText(12, "private-body", "검증된 동선·업종·계절부터 확대하고, 이후 MICE·외국인·민간 결제 데이터를 단계적으로 연계합니다.");
setText(12, "private-goal", "핵심: 성과 검증 후 예산 확대");
setText(12, "private-scope", "원칙: 효과 보장 표현 금지");
setSources(12, [
  "기대효과는 검증 프레임이며 보장 수치가 아님",
  "3개월 실제 운영 결과를 저장한 뒤 다음 기획안의 비교 근거로 재사용",
]);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await PresentationFile.exportPptx(presentation);
await output.save(outputPath);

const stat = await fs.stat(outputPath);
if (stat.size <= 0) throw new Error(`Empty PPTX: ${outputPath}`);
console.log(JSON.stringify({ outputPath, bytes: stat.size, slides: slides.length }, null, 2));
