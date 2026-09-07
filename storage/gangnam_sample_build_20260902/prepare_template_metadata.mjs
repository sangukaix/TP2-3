import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const buildDir = path.dirname(fileURLToPath(import.meta.url));
const layoutDir = path.join(buildDir, "template-inspect", "layouts");

const roles = [
  "opening thesis",
  "content map",
  "evidence summary",
  "problem and objective analysis",
  "target user scenario",
  "strategy components",
  "execution timeline",
  "peer comparison",
  "forecast chart and target scenario",
  "budget and KPI plan",
  "AI evidence pipeline",
  "decision summary and expansion",
];

const outputSlides = [];
for (let slideNo = 1; slideNo <= 12; slideNo += 1) {
  const layoutPath = path.join(layoutDir, `source-slide-${String(slideNo).padStart(2, "0")}.layout.json`);
  const layout = JSON.parse(await fs.readFile(layoutPath, "utf8"));
  const inherited = layout.elements.filter((item) => item.aid && item.kind !== "image").map((item) => item.aid);
  const images = layout.elements.filter((item) => item.aid && item.kind === "image").map((item) => item.aid);
  const editTargets = [
    {
      action: "rewrite",
      shapeIds: inherited,
      reason: "원본 디자인 개체를 유지하면서 강남구 기획안 문구와 표시값으로 교체",
    },
  ];
  if (images.length) {
    editTargets.push({
      action: "replace",
      shapeIds: images,
      reason: "원본 사진 프레임을 한국관광공사 Open API의 강남구 공식 사진으로 교체",
    });
  }
  if (slideNo === 9) {
    editTargets.push({
      action: "add",
      newPrimitiveAllowed: true,
      zone: { left: 106, top: 500, width: 770, height: 260 },
      reason: "자연추세와 담당자 입력 목표의 차이를 보여 주는 편집 가능한 PowerPoint 선 그래프",
      mustNotOverlapInherited: true,
    });
  }
  outputSlides.push({
    outputSlide: slideNo,
    sourceSlide: slideNo,
    narrativeRole: roles[slideNo - 1],
    reuseMode: "duplicate-slide",
    editTargets,
  });
}

await fs.writeFile(
  path.join(buildDir, "template-frame-map.json"),
  `${JSON.stringify({ outputSlides, omittedSourceSlides: [] }, null, 2)}\n`,
  "utf8",
);

await fs.writeFile(
  path.join(buildDir, "template-audit.txt"),
  [
    "SOURCE: 관광전략_완전편집형_12장_PPT템플릿.pptx",
    "SLIDES: 12 / 1600×900",
    "TYPOGRAPHY: Noto Sans KR, 큰 제목과 16px 이상 본문",
    "PALETTE: #F4F7FA / #004EA2 / #00C1D4 / #FF6B00",
    "MEDIA: source image frames on slides 3, 4, 6, 9, 10, 11",
    "INSERTION CONTRACT: 모든 출력 슬라이드는 같은 번호의 원본 슬라이드를 복제하고 inherited 개체를 직접 편집한다.",
    "PLACEHOLDERS: source deck has no inherited empty placeholders; slide-local named objects are used.",
    "NEW PRIMITIVE: slide 9 only, native line chart in the cleared left-bottom zone.",
  ].join("\n") + "\n",
  "utf8",
);

await fs.writeFile(
  path.join(buildDir, "deviation-log.txt"),
  [
    "1. 모든 슬라이드는 원본 레이아웃·좌표·타이포그래피를 기본 유지한다.",
    "2. 사진 6개는 같은 프레임 안에서 강남구 공식 관광 사진으로만 교체한다.",
    "3. 슬라이드 9 왼쪽 하단의 기존 설명·태그 영역은 비우고 native line chart를 추가한다.",
    "4. 슬라이드 7은 기존 4열을 1~4단계로 유지하고 하단 가치 패널을 5단계 평가·확대 결정으로 전환한다.",
    "5. 성과 숫자는 정책효과 예측이 아니라 ML 자연추세와 샘플 사용자 목표의 산술 차이로 표시한다.",
  ].join("\n") + "\n",
  "utf8",
);

await fs.writeFile(
  path.join(buildDir, "source-notes.txt"),
  [
    "한국관광 데이터랩 처리본: data/processed/ml/11680/monthly_demand.csv",
    "강남구 모델 메타데이터: artifacts/ml/11680/demand_model.metadata.json",
    "전국 비교 처리본: data/processed/nationwide/merged_planning_context/",
    "공식 사례: data/rag/official_case_studies.jsonl",
    "공식 사진: 한국관광공사 국문관광정보 Open API / https://apis.data.go.kr/B551011/KorService2",
    "사진 원본 URL은 최종 슬라이드 speaker notes의 [Sources]에 기록한다.",
  ].join("\n") + "\n",
  "utf8",
);

console.log(path.join(buildDir, "template-frame-map.json"));
