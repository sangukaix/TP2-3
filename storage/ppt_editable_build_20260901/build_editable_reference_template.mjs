import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const assetDir = path.join(scriptDir, "assets");
const previewDir = path.join(scriptDir, "preview");
const finalPath = path.join(
  projectRoot,
  "storage",
  "previews",
  "관광전략_완전편집형_12장_PPT템플릿.pptx",
);

const C = {
  bg: "#F4F7FA",
  white: "#FFFFFF",
  black: "#18191B",
  blue: "#004EA2",
  blue2: "#004EA2",
  cyan: "#00C1D4",
  cyan2: "#00C1D4",
  orange: "#FF6B00",
  gray: "#6E747B",
  gray2: "#4F555B",
  light: "#EDF2F6",
  border: "#D7DEE5",
  rule: "#E5EAF0",
};

const FONT = "Noto Sans KR";
const noLine = { style: "solid", fill: "none", width: 0 };

async function writeBlob(outputFile, blob) {
  await fs.writeFile(outputFile, new Uint8Array(await blob.arrayBuffer()));
}

async function imageBytes(imagePath) {
  const bytes = await fs.readFile(imagePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function rect(slide, name, x, y, w, h, fill = "none", lineFill = "none", lineWidth = 0, radius = 0) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function line(slide, name, x, y, w, h, color = C.blue, width = 2) {
  // PowerPoint는 음수 너비·높이를 허용하지 않으므로 대각선 방향만 좌표로 보정한다.
  if (w < 0) {
    x += w;
    w = Math.abs(w);
  }
  if (h < 0) {
    y += h;
    h = Math.abs(h);
  }
  return slide.shapes.add({
    geometry: "line",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: color, width },
  });
}

function text(slide, name, x, y, w, h, value, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position: {
      left: x,
      top: y,
      width: w,
      height: Math.min(h, Math.max(0, 900 - y)),
      ...(options.rotation !== undefined ? { rotation: options.rotation } : {}),
    },
    fill: options.fill ?? "none",
    line: options.line ?? noLine,
  });
  shape.text = value;
  shape.text.style = {
    typeface: options.typeface ?? FONT,
    fontSize: options.size ?? 18,
    color: options.color ?? C.black,
    bold: options.bold ?? false,
    italic: options.italic ?? false,
    underline: options.underline,
    alignment: options.align ?? "left",
    verticalAlignment: options.valign ?? "top",
    autoFit: options.autoFit ?? "shrinkText",
    wrap: options.wrap ?? "square",
    lineSpacing: options.lineSpacing,
    insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function rich(slide, name, x, y, w, h, runs, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: noLine,
  });
  shape.text.set([[...runs.map((r) => ({
    run: r.text,
    textStyle: {
      typeface: r.typeface ?? FONT,
      fontSize: `${r.size ?? options.size ?? 50}px`,
      bold: r.bold ?? options.bold ?? false,
      color: r.color ?? options.color ?? C.black,
      italic: r.italic ?? false,
      underline: r.underline,
    },
  }))]]);
  shape.text.style = {
    typeface: FONT,
    fontSize: options.size ?? 50,
    alignment: options.align ?? "left",
    verticalAlignment: options.valign ?? "middle",
    autoFit: "shrinkText",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function pill(slide, name, x, y, w, h, label, options = {}) {
  const p = rect(
    slide,
    name,
    x,
    y,
    w,
    h,
    options.fill ?? "none",
    options.line ?? C.border,
    options.lineWidth ?? 1,
    options.radius ?? h / 2,
  );
  p.text = label;
  p.text.style = {
    typeface: FONT,
    fontSize: options.size ?? 16,
    color: options.color ?? C.gray2,
    bold: options.bold ?? true,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    insets: { top: 0, right: 8, bottom: 0, left: 8 },
  };
  return p;
}

function outerFrame(slide) {
  rect(slide, "outer-frame", 3, 3, 1594, 894, "none", C.border, 1, 8);
}

function floatingBadge(slide) {
  const e = rect(slide, "floating-control", 1540, 748, 52, 52, C.white, C.border, 1, 26);
  e.shadow = "shadow-sm";
  text(slide, "floating-control-symbol", 1550, 757, 32, 30, "▣", {
    typeface: "Segoe UI Symbol",
    size: 22,
    color: C.gray,
    bold: false,
    align: "center",
    valign: "middle",
  });
}

async function photo(slide, file, name, x, y, w, h, alt) {
  const img = slide.images.add({
    blob: await imageBytes(path.join(assetDir, file)),
    contentType: "image/png",
    alt,
    fit: "cover",
    position: { left: x, top: y, width: w, height: h },
  });
  img.name = name;
  return img;
}

function notes(slide, n) {
  slide.speakerNotes.textFrame.setText(
    `[Sources]\n- User-provided visual reference: C:\\Users\\Admin\\Desktop\\ppt예시안 이미지\\${n}.png`,
  );
}

function bankIcon(slide, x, y) {
  slide.shapes.add({ geometry: "triangle", name: "bank-roof", position: { left: x + 16, top: y, width: 72, height: 28 }, fill: C.blue, line: noLine });
  rect(slide, "bank-entablature", x + 18, y + 26, 68, 9, C.blue);
  [0, 1, 2].forEach((i) => rect(slide, `bank-column-${i}`, x + 25 + i * 20, y + 34, 10, 42, C.blue));
  rect(slide, "bank-base", x + 15, y + 74, 74, 9, C.blue);
}

function peopleIcon(slide, x, y) {
  [0, 1, 2].forEach((i) => {
    rect(slide, `person-head-${i}`, x + i * 39, y, 17, 17, C.cyan, "none", 0, 9);
    rect(slide, `person-body-${i}`, x - 6 + i * 39, y + 18, 29, 18, C.cyan, "none", 0, 8);
  });
}

function chartIcon(slide, x, y) {
  line(slide, "chart-axis-y", x, y, 0, 65, C.blue, 7);
  line(slide, "chart-axis-x", x, y + 65, 65, 0, C.blue, 7);
  line(slide, "chart-line-1", x + 12, y + 45, 18, -18, C.blue, 7);
  line(slide, "chart-line-2", x + 30, y + 27, 14, 10, C.blue, 7);
  line(slide, "chart-line-3", x + 44, y + 37, 22, -24, C.blue, 7);
}

function miniAnalytics(slide, x, y) {
  text(slide, "analytics-glyph", x, y, 135, 42, "◔  ▮▮▮  ◉", {
    typeface: "Segoe UI Symbol",
    size: 28,
    color: C.cyan,
    bold: true,
    align: "center",
  });
}

function shopIcon(slide, x, y) {
  slide.shapes.add({ geometry: "trapezoid", name: "shop-awning", position: { left: x + 8, top: y, width: 76, height: 27 }, fill: C.blue, line: noLine });
  rect(slide, "shop-body", x + 17, y + 25, 58, 48, C.blue);
  rect(slide, "shop-window", x + 27, y + 38, 20, 22, C.white);
  rect(slide, "shop-door", x + 55, y + 38, 12, 35, C.white);
}

function miniShops(slide, x, y) {
  text(slide, "shops-glyph", x, y, 135, 42, "▰  ▦  ♜", {
    typeface: "Segoe UI Symbol",
    size: 27,
    color: C.cyan,
    bold: true,
    align: "center",
  });
}

function slide1(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  text(slide, "background-wordmark", -58, 300, 1720, 310, "TOURISM AI", {
    size: 300,
    color: "#E7EDF4",
    bold: true,
    align: "center",
    valign: "middle",
    wrap: "none",
  });
  line(slide, "center-top-vertical", 800, 94, 0, 132, C.blue, 3);
  line(slide, "center-bottom-vertical", 800, 673, 0, 131, C.blue, 3);
  rect(slide, "title-panel", 367, 222, 868, 451, C.white);
  line(slide, "title-panel-top", 367, 222, 868, 0, C.blue, 4);
  text(slide, "security-label", 694, 310, 296, 34, "대 외 비   문 서", { size: 18, color: C.gray2, bold: true, align: "center" });
  text(slide, "cover-title-line1", 448, 382, 707, 75, "지역 관광 데이터 분석 및", { size: 58, color: C.black, bold: true, align: "center" });
  rich(slide, "cover-title-line2", 439, 463, 727, 74, [
    { text: "AI 전략 지원 웹서비스", color: C.blue, bold: true, size: 58 },
    { text: " 기획안", color: C.black, bold: true, size: 58 },
  ], { align: "center", size: 58 });
  line(slide, "date-rule-left", 642, 579, 49, 0, C.cyan, 2);
  text(slide, "cover-date", 708, 561, 275, 40, "2026년 09월 01일", { size: 21, color: C.black, align: "center", valign: "middle" });
  line(slide, "date-rule-right", 1001, 579, 49, 0, C.cyan, 2);
  text(slide, "org-title", 1325, 109, 170, 34, "데이터 혁신 전략실", { size: 20, color: C.blue, bold: true, align: "center" });
  line(slide, "org-orange-rule", 1427, 146, 68, 0, C.orange, 2);
  text(slide, "org-owner", 1370, 167, 125, 63, "수석 전략 기획자 /\n박 서 준 실장", { size: 16, color: C.gray, bold: false, align: "right" });
  text(slide, "report-number", 110, 663, 369, 31, "보 고 서  번 호  2 0 2 6 - 0 1", { size: 18, color: C.cyan, bold: true });
  text(slide, "report-topic", 110, 706, 369, 106, "공공 데이터 기반\n관광 활성화", { size: 42, color: C.blue, bold: true });
  line(slide, "corner-tl-h", 68, 65, 31, 0, C.cyan, 2);
  line(slide, "corner-tl-v", 68, 65, 0, 31, C.cyan, 2);
  line(slide, "corner-br-h", 1531, 834, 31, 0, C.cyan, 2);
  line(slide, "corner-br-v", 1562, 803, 0, 31, C.cyan, 2);
  notes(slide, 1);
}

function slide2(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  text(slide, "top-brand", 90, 39, 414, 32, "지역 관광 데이터 분석 시스템", { size: 19, color: C.blue, bold: true });
  text(slide, "top-date", 1370, 34, 170, 28, "2026. 09. 01", { size: 16, color: C.gray2, bold: true, align: "right" });
  line(slide, "top-rule", 3, 103, 1594, 0, C.rule, 1);
  rect(slide, "contents-rail", 3, 103, 505, 797, C.blue);
  text(slide, "contents-vertical", -91, 437, 710, 110, "CONTENTS", { size: 100, color: "#2B6CB2", bold: true, rotation: -90, align: "center", valign: "middle", wrap: "none" });
  text(slide, "contents-en", 45, 423, 418, 37, "T A B L E   O F   C O N T E N T S", { size: 23, color: C.cyan, bold: true, align: "center" });
  text(slide, "contents-ko", 132, 483, 250, 68, "목차 안내", { size: 47, color: C.white, bold: true, align: "center", valign: "middle" });
  line(slide, "contents-orange", 216, 565, 74, 0, C.orange, 4);
  const left = [
    ["01", "프로젝트 개요 및 기획 배경"],
    ["02", "문제 정의 및 서비스 목표"],
    ["03", "주요 사용자 및 활용 시나리오"],
    ["04", "핵심 기능 7가지 정의"],
    ["05", "서비스 이용 Flow 및 산출물"],
  ];
  const right = [
    ["06", "차별화 포인트 및 경쟁력"],
    ["07", "데이터 및 AI/ML 모델 구조"],
    ["08", "주요 화면 구성 및 UI 기획"],
    ["09", "시스템 아키텍처 및 기술 스택"],
    ["10", "기대 효과 및 향후 확장 방향"],
  ];
  [left, right].forEach((items, col) => {
    const x = col === 0 ? 570 : 1122;
    items.forEach(([n, label], i) => {
      const y = 334 + i * 74;
      text(slide, `toc-${col}-${i}-num`, x, y, 44, 32, n, { size: 20, color: C.cyan, bold: true });
      text(slide, `toc-${col}-${i}-label`, x + 55, y - 1, col === 0 ? 440 : 410, 34, label, { size: 20, color: C.black, bold: true });
      line(slide, `toc-${col}-${i}-rule`, x, y + 42, col === 0 ? 480 : 455, 0, C.rule, 1);
    });
  });
  notes(slide, 2);
}

async function slide3(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  await photo(slide, "photo-3.png", "tourism-photo", 1036, 3, 561, 894, "겨울 관광 현장 사진");
  text(slide, "section", 105, 107, 259, 31, "S E C T I O N   0 1", { size: 18, color: C.gray2, bold: true });
  rich(slide, "title", 104, 148, 900, 74, [
    { text: "프로젝트 개요 및 ", color: C.blue, bold: true, size: 54 },
    { text: "기획 배경", color: C.cyan, bold: true, size: 54 },
  ], { size: 54 });
  line(slide, "title-rule", 104, 236, 835, 0, C.blue, 2);
  text(slide, "intro", 105, 297, 844, 81, "관광 데이터의 양적 팽창에도 불구하고 전문 인력 부족으로 실질적인 정책 반영에 한계를 겪\n고 있습니다. 지자체는 객관적 근거 기반의 의사결정이 절실한 상황입니다.", { size: 19, color: C.gray2, lineSpacing: 1.25 });
  line(slide, "decision-rail", 105, 409, 0, 105, C.cyan, 3);
  text(slide, "decision-title", 132, 413, 338, 39, "의사결정 체계 마련", { size: 22, color: C.blue, bold: true });
  text(slide, "decision-body", 132, 461, 383, 69, "파편화된 공공데이터를 통합하여 지자체 담당자가\n즉각 활용 가능한 분석 환경을 구축합니다.", { size: 18, color: C.gray });
  line(slide, "activation-rail", 547, 409, 0, 105, C.cyan, 3);
  text(slide, "activation-title", 574, 413, 338, 39, "지역 관광 활성화", { size: 22, color: C.blue, bold: true });
  text(slide, "activation-body", 574, 461, 388, 69, "데이터 공백을 메우고 증거 기반의 정책 수립을 지\n원하여 지역 경쟁력을 강화합니다.", { size: 18, color: C.gray });
  rect(slide, "release-card", 105, 571, 405, 135, C.white);
  line(slide, "release-card-rail", 105, 571, 0, 135, C.cyan, 5);
  text(slide, "release-label", 133, 598, 225, 31, "배포 예정일", { size: 16, color: C.gray2, bold: true });
  text(slide, "release-value", 133, 637, 170, 54, "2026.09", { size: 38, color: C.blue, bold: true, wrap: "none" });
  text(slide, "release-suffix", 300, 652, 155, 27, "RELEASE", { size: 14, color: C.cyan, bold: true, wrap: "none" });
  rect(slide, "strategy-card", 535, 571, 405, 135, C.white);
  line(slide, "strategy-card-rail", 535, 571, 0, 135, C.cyan, 5);
  text(slide, "strategy-label", 564, 598, 225, 31, "주요 전략", { size: 16, color: C.gray2, bold: true });
  text(slide, "strategy-value", 564, 637, 175, 54, "AI+DATA", { size: 38, color: C.blue, bold: true, wrap: "none" });
  text(slide, "strategy-suffix", 739, 652, 175, 27, "INTEGRATED", { size: 14, color: C.cyan, bold: true, wrap: "none" });
  notes(slide, 3);
}

async function slide4(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  await photo(slide, "photo-4.png", "city-photo", 1074, 0, 526, 900, "도시 관광 인프라 사진");
  text(slide, "eyebrow", 104, 87, 383, 31, "P R O B L E M   &   O B J E C T I V E", { size: 18, color: C.cyan, bold: true });
  text(slide, "title", 102, 140, 890, 201, "문제 정의 및\n서비스 목표", { size: 78, color: C.black, bold: true, lineSpacing: 0.98 });
  line(slide, "orange-rule", 102, 353, 101, 0, C.orange, 9);
  const labels = ["데이터 수집", "맞춤 시각화", "수요 예측", "AI 전략 제안", "의사결정 지원", "실행 가능성", "정책 최적화", "원스톱 체계"];
  labels.forEach((label, i) => {
    const row = Math.floor(i / 4);
    const col = i % 4;
    const x = 102 + col * 223;
    const y = 411 + row * 72;
    const box = rect(slide, `feature-${i}`, x, y, 204, 51, "#F3F6F9", C.border, 1);
    box.text = label;
    box.text.style = { typeface: FONT, fontSize: 16, color: C.blue, bold: true, alignment: "center", verticalAlignment: "middle", autoFit: "shrinkText", insets: { top: 0, right: 2, bottom: 0, left: 2 } };
  });
  line(slide, "body-rail", 104, 603, 0, 216, C.cyan, 4);
  text(slide, "body", 134, 613, 878, 212, "현재의 관광 데이터 서비스는 단순 통계 수치 조회에 그쳐 실제 정책 수립에 활용하기 어\n렵습니다. 본 서비스는 데이터 수집부터 AI 전략 제안을 잇는 원스톱 의사결정 체계를 구\n축합니다.\n\n단순 통계를 넘어 머신러닝 기반의 미래 수요를 예측하고, 실무자가 즉시 정책에 반영할\n수 있는 구체적이고 실행 가능한 전략적 통찰력을 제공하는 것을 최우선 목표로 합니다.", { size: 19, color: C.gray, lineSpacing: 1.35 });
  notes(slide, 4);
}

function slide5(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  text(slide, "title", 402, 100, 796, 70, "주요 사용자 및 활용 시나리오", { size: 52, color: C.blue, bold: true, align: "center" });
  line(slide, "title-rule", 682, 172, 68, 0, C.blue, 4);
  text(slide, "subtitle", 430, 205, 740, 36, "지역 관광 데이터 분석 및 AI 전략 지원 웹서비스 기획안", { size: 18, color: C.gray2, align: "center" });
  const cards = [
    { x: 87, title: "지자체 관광 담당자", body: "데이터 기반 신규 관광 상품 기획 및 정책 예산 편성의\n객관적 근거 확보", role: "역할: 정책 및 예산 수립", icon: "bank" },
    { x: 576, title: "공공 및 유관 기관", body: "지역별 관광 현황 실시간 모니터링 및 핵심 성과 지표\n(KPI) 효율적 관리", role: "역할: 모니터링 및 KPI 관리", icon: "chart" },
    { x: 1066, title: "지역 관광 사업자", body: "방문객 소비 트렌드 분석을 통한 타깃 마케팅 전략 수\n립 및 서비스 품질 개선 지원", role: "역할: 마케팅 및 서비스 개선", icon: "shop" },
  ];
  cards.forEach((card, i) => {
    rect(slide, `audience-card-${i}`, card.x, 316, 448, 477, C.white, C.border, 1, 8);
    pill(slide, `audience-pill-${i}`, card.x + 30, 357, 388, 50, card.title, { fill: C.white, line: C.blue, lineWidth: 1, size: 19, color: C.blue, bold: true, radius: 25 });
    if (card.icon === "bank") {
      bankIcon(slide, card.x + 174, 452);
      peopleIcon(slide, card.x + 160, 540);
    } else if (card.icon === "chart") {
      chartIcon(slide, card.x + 190, 454);
      miniAnalytics(slide, card.x + 158, 540);
    } else {
      shopIcon(slide, card.x + 177, 452);
      miniShops(slide, card.x + 157, 540);
    }
    text(slide, `audience-body-${i}`, card.x + 30, 622, 388, 62, card.body, { size: 15, color: C.black, align: "center", valign: "middle" });
    line(slide, `audience-divider-${i}`, card.x + 30, 681, 388, 0, C.rule, 2);
    text(slide, `audience-role-${i}`, card.x + 35, 724, 378, 34, card.role, { size: 14, color: C.gray2, bold: true, align: "center" });
  });
  text(slide, "footer-left", 87, 830, 380, 24, "지역 관광 데이터 분석 및 AI 전략 지원 솔루션", { size: 13, color: C.gray2 });
  rect(slide, "footer-dot", 1278, 833, 10, 10, C.orange, "none", 0, 5);
  text(slide, "footer-right", 1300, 823, 245, 26, "AI Data-Driven Decision Making", { size: 12, color: C.gray2 });
  notes(slide, 5);
}

async function slide6(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  await photo(slide, "photo-6.png", "visitor-photo", 0, 0, 503, 900, "관광객 현장 사진");
  text(slide, "title", 561, 92, 850, 85, "핵심 기능 7가지 정의", { size: 59, color: C.blue, bold: true });
  line(slide, "title-rule", 501, 226, 1096, 0, C.blue, 4);
  const rows = [
    ["01", "지역 검색 및 선택: 전국 시군구 단위의 간편한 대상지 설정"],
    ["02", "관광 데이터 대시보드: 방문객, 소비, SNS 트렌드 시각화"],
    ["03", "지역 특성 분석: SWOT 분석을 포함한 지역별 관광 강약점 도출"],
  ];
  rows.forEach(([n, label], i) => {
    const y = 310 + i * 87;
    rect(slide, `function-row-${i}`, 562, y, 975, 66, C.white, C.border, 1, 8).shadow = "shadow-sm";
    text(slide, `function-num-${i}`, 594, y + 19, 50, 34, n, { size: 22, color: C.blue, bold: true });
    text(slide, `function-label-${i}`, 646, y + 17, 850, 36, label, { size: 20, color: C.black });
  });
  rect(slide, "bottom-band", 501, 628, 1096, 272, "#F6F8FA");
  pill(slide, "analysis-tag", 562, 689, 264, 38, "A I  &  D A T A  A N A L Y S I S", { fill: "none", line: C.cyan, size: 15, color: C.cyan, bold: true, radius: 19 });
  text(slide, "function-more-left", 562, 756, 493, 103, "④ 수요 예측: 머신러닝 기반 미래 관광객 수 및 소비 패턴 예측\n⑤ AI 전략 리포트: 분석 데이터를 근거로 한 최적의 관광 활성화\n방안 제안", { size: 17, color: C.gray, lineSpacing: 1.25 });
  text(slide, "function-more-right", 1069, 756, 510, 103, "⑥ AI 챗봇: 선택 지역 데이터에 특화된 실시간 질의응답 기능\n⑦ 지도 시각화: 카카오맵 연동을 통한 공간적 관광 밀집도 분석", { size: 17, color: C.gray, lineSpacing: 1.25 });
  notes(slide, 6);
}

function slide7(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  text(slide, "eyebrow", 96, 78, 300, 28, "S E R V I C E   P L A N N I N G", { size: 14, color: C.blue, bold: true });
  rich(slide, "title", 96, 107, 850, 68, [
    { text: "서비스 이용 ", size: 52, color: C.black, bold: true },
    { text: "Flow 및 산출물", size: 52, color: C.blue, bold: true },
  ], { size: 52 });
  line(slide, "title-rule", 96, 181, 1400, 0, C.gray, 2);
  const steps = [
    ["STEP 01", "지역 선택 및 로딩", "사용자 정의 지역 설정 및 데이터랩 기반 맞춤형\n데이터셋 자동 큐레이션"],
    ["STEP 02", "대시보드 및 분석", "방문객 및 소비 시각화 차트와 데이터 근거 기반\n지역별 SWOT 분석 결과 도출을 통한 전략적 통\n찰 제공."],
    ["STEP 03", "수요 예측 및 리포트", "시계열 모델 기반 관광 수요 예측 및 AI 해석이\n포함된 PDF 전략 보고서 발행"],
    ["STEP 04", "AI 챗봇 전략 활용", "RAG 기반 AI 챗봇과의 심층 질의응답을 통한 실\n무 정책 반영 및 최종 의사결정을 지원하는 고도\n화 프로세스."],
  ];
  steps.forEach(([step, titleValue, body], i) => {
    const x = 109 + i * 356;
    line(slide, `step-${i}-rule`, x, 261, 319, 0, C.blue, 2);
    text(slide, `step-${i}-label`, x, 299, 180, 28, step, { size: 15, color: C.blue, bold: true });
    text(slide, `step-${i}-title`, x, 341, 310, 38, titleValue, { size: 23, color: C.blue, bold: true });
    text(slide, `step-${i}-body`, x, 389, 320, 117, body, { size: 16, color: C.gray, lineSpacing: 1.25 });
  });
  rect(slide, "value-panel", 107, 575, 1386, 247, C.white);
  line(slide, "value-panel-rail", 107, 575, 0, 247, C.blue, 5);
  text(slide, "value-title", 162, 630, 506, 38, "AI 전략 지원 웹서비스 핵심 가치", { size: 22, color: C.blue, bold: true });
  text(slide, "value-body", 162, 678, 1281, 105, "본 웹서비스는 공공 관광 데이터를 인공지능 기술과 결합하여 실질적인 정책 수립을 지원합니다. 데이터 로딩부터 AI 리포트 생성, 챗봇을 통한 정책 질의까지 이어지는 통합 Flow를\n통해 지자체의 관광 경쟁력을 극대화합니다. 데이터 기반의 객관적인 분석과 AI의 미래 예측을 통해 의사결정의 정확성을 높이고 지역 경제 활성화를 위한 맞춤형 전략을 제시하는 것\n을 목표로 합니다.", { size: 17, color: C.gray, lineSpacing: 1.35 });
  notes(slide, 7);
}

function slide8(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  text(slide, "eyebrow", 108, 71, 471, 30, "D I F F E R E N T I A T I O N   &   C O M P E T I T I V E N E S S", { size: 15, color: C.blue, bold: true });
  rich(slide, "title", 108, 117, 827, 76, [
    { text: "차별화 ", size: 57, color: C.black, bold: false },
    { text: "포인트 및 경쟁력", size: 57, color: C.blue, bold: false },
  ], { size: 57 });
  line(slide, "title-rule", 108, 219, 1372, 0, C.blue, 2);
  rect(slide, "grid", 108, 292, 1371, 552, C.white);
  line(slide, "grid-v", 793, 292, 0, 552, C.rule, 2);
  line(slide, "grid-h", 108, 567, 1371, 0, C.rule, 2);
  const cells = [
    { x: 108, y: 301, n: "01", title: "데이터 가치 사슬 구축", body: "단순한 통계 조회를 넘어 AI 모델을 통해 2026년 관광 트렌드 등 미래 수요를 정\n확히 예측하고 선제적 대응 전략을 제시하여 데이터의 실질적 가치를 창출합니\n다.", plus: "+ 예측 기반 전략 제안" },
    { x: 854, y: 301, n: "02", title: "전국 단위 확장 분석", body: "특정 지역에 국한되지 않는 전국 단위 확장형 분석 프레임워크를 적용하여 광범\n위한 데이터 수집 및 비교 분석을 가능하게 합니다.", plus: "+ 범용적 분석 모델 적용" },
    { x: 108, y: 641, n: "03", title: "LLM 및 RAG 결합 기술", body: "최신 LLM과 RAG 기술을 결합하여 단순 수치 나열이 아닌, 데이터 근거에 기반\n한 신뢰도 높은 AI 해석 및 맞춤형 정책 리포트를 자동 생성하여 제공합니다.", plus: "+ 고신뢰도 AI 정책 리포트" },
    { x: 854, y: 641, n: "04", title: "데이터 기반 의사결정", body: "복잡한 관광 데이터를 공공 행정에 즉시 활용 가능한 인사이트로 변환하여, 지자\n체 및 공공기관의 과학적이고 효율적인 정책 수립을 강력하게 지원합니다.", plus: "+ 실효성 있는 정책 지원" },
  ];
  cells.forEach((c, i) => {
    text(slide, `diff-num-${i}`, c.x, c.y, 57, 48, c.n, { size: 39, color: C.cyan, bold: true });
    text(slide, `diff-title-${i}`, c.x + 65, c.y + 2, 563, 48, c.title, { size: 32, color: C.black });
    text(slide, `diff-body-${i}`, c.x, c.y + 72, 620, 98, c.body, { size: 17, color: C.gray2, lineSpacing: 1.25 });
    text(slide, `diff-plus-${i}`, c.x, c.y + 152, 379, 32, c.plus, { size: 16, color: C.gray2, bold: true });
    text(slide, `diff-plus-orange-${i}`, c.x, c.y + 152, 14, 32, "+", { size: 18, color: C.orange, bold: true });
  });
  notes(slide, 8);
}

async function slide9(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  await photo(slide, "photo-9.png", "palace-photo", 975, 0, 625, 900, "궁궐 관광 사진");
  text(slide, "eyebrow", 106, 111, 371, 31, "T E C H N I C A L   F R A M E W O R K", { size: 16, color: C.gray2, bold: true });
  rich(slide, "title", 106, 152, 853, 74, [
    { text: "데이터 및 ", size: 56, color: C.black, bold: false },
    { text: "AI/ML 모델 구조", size: 56, color: C.blue, bold: true },
  ], { size: 56 });
  line(slide, "title-rule", 106, 238, 770, 0, C.blue, 2);
  text(slide, "intro", 106, 301, 792, 73, "본 서비스는 한국관광 데이터랩 및 공공데이터 API를 통해 실시간 데이터를 수\n집하고 전처리하는 통합 파이프라인을 구축합니다.", { size: 18, color: C.gray, lineSpacing: 1.3 });
  line(slide, "prediction-rail", 106, 418, 0, 94, C.cyan, 4);
  text(slide, "prediction-title", 140, 421, 584, 34, "수요 예측 모델 (PREDICTION)", { size: 19, color: C.blue, bold: true });
  text(slide, "prediction-body", 140, 462, 769, 60, "LSTM 및 Prophet 시계열 모델과 회귀 모델을 병합 활용하며, MAE와 RMSE 지표를 통해 예측\n성능의 정밀도를 검증합니다.", { size: 17, color: C.gray });
  line(slide, "rag-rail", 106, 553, 0, 94, C.cyan, 4);
  text(slide, "rag-title", 140, 556, 584, 34, "AI 전략 생성 (RAG SYSTEM)", { size: 19, color: C.blue, bold: true });
  text(slide, "rag-body", 140, 597, 769, 60, "RAG(검색 증강 생성) 기반 LLM을 도입하여 지자체 맞춤형 정밀 보고서를 자동 생성하는 프로세\n스를 구현합니다.", { size: 17, color: C.gray });
  [
    [106, 703, 103, "시계열 분석"],
    [229, 703, 94, "RAG 모델"],
    [342, 703, 138, "실시간 파이프라인"],
  ].forEach(([x, y, w, label], i) => pill(slide, `tech-tag-${i}`, x, y, w, 32, label, { fill: "none", line: C.blue, size: 13, color: C.blue, bold: true, radius: 0 }));
  notes(slide, 9);
}

async function slide10(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  await photo(slide, "photo-10.png", "island-photo", 1037, 4, 560, 893, "해안 관광 사진");
  text(slide, "eyebrow", 107, 113, 371, 31, "U I / U X   P L A N N I N G", { size: 16, color: C.gray2, bold: false });
  rich(slide, "title", 107, 153, 853, 74, [
    { text: "주요 화면 구성 및 ", size: 55, color: C.blue, bold: false },
    { text: "UI 기획", size: 55, color: C.cyan, bold: false },
  ], { size: 55 });
  line(slide, "title-rule", 107, 238, 831, 0, C.blue, 2);
  text(slide, "intro", 107, 299, 798, 100, "본 서비스는 사용자 친화적인 인터페이스를 통해 복잡한 데이터를 직관적으로 전\n달합니다. 각 화면은 공공기관의 의사결정을 지원하기 위해 최적화된 레이아웃을\n제공합니다.", { size: 18, color: C.gray2, lineSpacing: 1.35 });
  line(slide, "dashboard-rail", 107, 445, 0, 125, C.cyan, 4);
  text(slide, "dashboard-title", 140, 450, 371, 36, "메인 및 대시보드", { size: 22, color: C.blue, bold: true });
  text(slide, "dashboard-body", 140, 496, 365, 91, "지역 선택 기능과 방문객 수, 소비 현황 등 핵심 지\n표 위젯을 전면에 배치하여 즉각적인 통찰을 제공합\n니다.", { size: 17, color: C.gray, lineSpacing: 1.25 });
  line(slide, "analysis-rail", 548, 445, 0, 125, C.cyan, 4);
  text(slide, "analysis-title", 582, 450, 371, 36, "분석 및 예측 화면", { size: 22, color: C.blue, bold: true });
  text(slide, "analysis-body", 582, 496, 365, 91, "다각도 차트와 함께 머신러닝 기반의 미래 관광 수\n요 타임라인을 직관적인 UI로 시각화하여 제공합니\n다.", { size: 17, color: C.gray, lineSpacing: 1.25 });
  rect(slide, "report-card", 107, 630, 400, 132, C.white, C.border, 1);
  text(slide, "report-card-title", 130, 657, 258, 30, "AI 리포트 및 챗봇", { size: 17, color: C.cyan, bold: true });
  text(slide, "report-card-body", 130, 696, 326, 27, "가독성 높은 전략 텍스트 및", { size: 16, color: C.gray2 });
  text(slide, "report-card-orange", 130, 725, 292, 27, "자연어 대화형 인터페이스", { size: 16, color: C.orange, bold: true });
  rect(slide, "map-card", 537, 630, 401, 132, C.white, C.border, 1);
  text(slide, "map-card-title", 562, 657, 258, 30, "지도 서비스 기획", { size: 17, color: C.cyan, bold: true });
  text(slide, "map-card-body", 562, 696, 326, 27, "카카오맵 기반 핫플레이스", { size: 16, color: C.gray2 });
  text(slide, "map-card-orange", 562, 725, 292, 27, "관광지 클러스터링 시각화", { size: 16, color: C.orange, bold: true });
  notes(slide, 10);
}

async function slide11(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  await photo(slide, "photo-11.png", "workspace-photo", 1076, 0, 524, 900, "개발 환경 이미지");
  text(slide, "eyebrow", 106, 51, 534, 31, "T E C H   S T A C K   &   I N F R A S T R U C T U R E", { size: 16, color: C.gray2, bold: true });
  text(slide, "title", 106, 99, 821, 170, "시스템 아키텍처 및\n기술 스택", { size: 64, color: C.black, bold: true, lineSpacing: 0.95 });
  line(slide, "short-rule", 106, 286, 81, 0, C.blue, 5);
  const cards = [
    [106, 388, "Frontend", "React, Vite, Tailwind CSS"],
    [551, 388, "Backend", "Python FastAPI 고성능 서버"],
    [106, 497, "ML/AI", "PyTorch & LangChain LLM"],
    [551, 497, "Infrastructure", "AWS EC2, S3, RDS 클라우드"],
  ];
  cards.forEach(([x, y, titleValue, body], i) => {
    rect(slide, `stack-card-${i}`, x, y, 426, 89, C.white);
    line(slide, `stack-card-${i}-rail`, x, y, 0, 89, C.cyan, 4);
    text(slide, `stack-card-${i}-title`, x + 25, y + 22, 281, 29, titleValue, { size: 17, color: C.black, bold: true });
    text(slide, `stack-card-${i}-body`, x + 25, y + 56, 360, 25, body, { size: 14, color: C.gray });
  });
  text(slide, "body", 136, 657, 854, 279, "본 서비스는 최신 웹 기술과 AI 프레임워크를 결합하여 안정적인 분석 환경을 제공합니다.\nFrontend는 React와 Vite, Tailwind CSS를 통해 고성능 반응형 UI를 구현하며, Backend\n는 Python FastAPI로 데이터 처리 효율을 극대화합니다. ML/AI 영역에서는 PyTorch 기반의\n수요 예측 모델과 LangChain 기반 LLM 오케스트레이션을 통해 지능형 에이전트 기능을 수\n행합니다. 전체 인프라는 AWS EC2, S3, RDS를 활용하여 최적화된 클라우드 아키텍처로 설\n계되었습니다.", { size: 18, color: C.black, lineSpacing: 1.3 });
  notes(slide, 11);
}

function slide12(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.bg;
  text(slide, "title", 471, 238, 667, 77, "기대 효과 및 향후 확장 방향", { size: 56, color: C.blue, bold: true, align: "center" });
  line(slide, "column-line-1", 580, 354, 0, 382, C.border, 2);
  line(slide, "column-line-2", 1026, 354, 0, 382, C.border, 2);
  pill(slide, "expected-pill", 86, 354, 425, 49, "기대 효과", { fill: C.blue, line: C.blue, size: 19, color: C.white, bold: true, radius: 25 });
  rect(slide, "expected-card", 86, 434, 425, 134, C.white, C.border, 1, 8);
  text(slide, "expected-body", 115, 476, 366, 72, "과학적 분석을 통한 정책 실효성 증대 및 불필요한\n예산 절감으로 관광 행정 효율성을 극대화합니다.", { size: 17, color: C.gray2, lineSpacing: 1.35 });
  pill(slide, "indicator-pill", 86, 608, 425, 49, "분석 고도화 지표", { fill: "none", line: C.border, size: 17, color: C.gray2, bold: false, radius: 25 });
  const glyphs = ["⌁", "◔", "▦", "▤", "⚡", "◎"];
  glyphs.forEach((g, i) => {
    const fill = i < 4 ? C.blue : i === 4 ? C.cyan : "#70D4DF";
    rect(slide, `indicator-circle-${i}`, 95 + i * 71, 685, 52, 52, fill, "none", 0, 26);
    text(slide, `indicator-glyph-${i}`, 104 + i * 71, 692, 34, 34, g, { typeface: "Segoe UI Symbol", size: 24, color: C.white, bold: true, align: "center", valign: "middle" });
  });
  pill(slide, "service-pill", 611, 354, 383, 49, "서비스 확장 및 고도화", { fill: "none", line: C.border, size: 18, color: C.gray2, bold: true, radius: 25 });
  text(slide, "service-body", 611, 451, 383, 115, "실시간 유동인구 연동 및 외국인 관광객 정밀 분석 기\n능을 추가하여 글로벌 관광 수요에 기민하게 대응합니\n다.", { size: 17, color: C.gray2, lineSpacing: 1.3 });
  text(slide, "service-note", 611, 583, 383, 77, "* AI 기반의 예측 모델을 도입하여 향후 관광 트렌드 변화에 대\n한 선제적인 의사결정 지원 체계를 구축할 예정입니다.", { size: 15, color: C.gray, italic: true, lineSpacing: 1.25 });
  pill(slide, "service-scope", 611, 688, 383, 49, "범위: 글로벌 및 실시간", { fill: "none", line: C.cyan, size: 18, color: C.blue, bold: true, radius: 25 });
  pill(slide, "private-pill", 1096, 354, 425, 49, "민간 데이터 융합", { fill: "none", line: C.border, size: 18, color: C.gray2, bold: true, radius: 25 });
  text(slide, "private-body", 1096, 451, 425, 122, "카드사, 통신사 등 민간 데이터 결합을 통한 정밀한 지역 상\n권 분석 및 개인화된 관광 전략 서비스 제공으로 지역 경제\n활성화를 견인합니다.", { size: 17, color: C.gray2, lineSpacing: 1.35 });
  rect(slide, "private-info", 1264, 522, 18, 18, C.blue, "none", 0, 9);
  text(slide, "private-info-label", 1268, 522, 10, 15, "i", { size: 11, color: C.white, bold: true, align: "center", valign: "middle" });
  text(slide, "private-goal", 1096, 603, 361, 34, "핵심 목표: 지역 경제 활성화", { size: 17, color: C.orange, bold: true });
  pill(slide, "private-scope", 1096, 688, 425, 49, "협력: 민간 데이터 거버넌스", { fill: "none", line: C.orange, size: 18, color: C.orange, bold: true, radius: 25 });
  notes(slide, 12);
}

async function main() {
  await fs.mkdir(previewDir, { recursive: true });
  await fs.mkdir(path.dirname(finalPath), { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: 1600, height: 900 } });
  slide1(presentation);
  slide2(presentation);
  await slide3(presentation);
  await slide4(presentation);
  slide5(presentation);
  await slide6(presentation);
  slide7(presentation);
  slide8(presentation);
  await slide9(presentation);
  await slide10(presentation);
  await slide11(presentation);
  slide12(presentation);

  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(previewDir, `${stem}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(previewDir, `${stem}.layout.json`), await layout.text());
  }
  await writeBlob(path.join(previewDir, "montage.webp"), await presentation.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(finalPath);
  console.log(finalPath);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
