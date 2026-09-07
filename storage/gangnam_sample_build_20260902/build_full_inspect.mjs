import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

// 템플릿 검사 도구가 슬라이드당 일부 개체만 기록하는 경우를 보완한다.
// 이미 생성된 레이아웃 JSON은 실제 PPT 개체를 전부 포함하므로,
// 여기서 스타터 덱 검증용 전체 개체 인벤토리를 재구성한다.
const buildDir = path.dirname(fileURLToPath(import.meta.url));
const layoutDir = path.join(buildDir, "template-inspect", "layouts");
const outputPath = path.join(buildDir, "template-inspect", "template-inspect-full.ndjson");

const rows = [];
for (let slideNo = 1; slideNo <= 12; slideNo += 1) {
  const fileName = `source-slide-${String(slideNo).padStart(2, "0")}.layout.json`;
  const layout = JSON.parse(await fs.readFile(path.join(layoutDir, fileName), "utf8"));
  rows.push({
    kind: "slide",
    id: layout.slideId ?? `source-slide-${slideNo}`,
    slide: slideNo,
    title: layout.title ?? "",
    textShapes: layout.elements.filter((item) => item.text).length,
  });

  for (const element of layout.elements) {
    if (!element.aid) continue;
    rows.push({
      kind: element.kind ?? "shape",
      id: element.aid,
      slide: slideNo,
      name: element.name ?? "",
      bbox: element.bbox ?? null,
      textChars: typeof element.text === "string" ? element.text.length : undefined,
    });
  }
}

await fs.writeFile(outputPath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
console.log(`${outputPath}\nobjects=${rows.length}`);
