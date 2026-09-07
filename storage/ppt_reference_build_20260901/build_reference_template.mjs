import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

// 사용자가 제공한 12장 시안을 슬라이드 크기에 맞춰 배치해
// 디자인 확인용 PowerPoint 템플릿을 만든다.
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..", "..");
const referenceDir = path.join(projectRoot, "storage", "template_reference_20260901");
const previewDir = path.join(scriptDir, "preview");
const outputPath = path.join(
  projectRoot,
  "storage",
  "previews",
  "tourism_reference_design_template_exact.pptx",
);

async function writeBlob(outputFile, blob) {
  await fs.writeFile(outputFile, new Uint8Array(await blob.arrayBuffer()));
}

async function readImageBlob(imagePath) {
  const bytes = await fs.readFile(imagePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

async function main() {
  await fs.mkdir(previewDir, { recursive: true });
  await fs.mkdir(path.dirname(outputPath), { recursive: true });

  // 원본 시안 해상도(1600×900)를 슬라이드 좌표계로 그대로 사용한다.
  const presentation = Presentation.create({
    slideSize: { width: 1600, height: 900 },
  });

  for (let index = 1; index <= 12; index += 1) {
    const referencePath = path.join(referenceDir, `${index}.png`);
    const slide = presentation.slides.add();
    slide.background.fill = "white";

    // 이미지 한 장을 전체 슬라이드에 배치하므로 비율과 디자인이 정확히 유지된다.
    const image = slide.images.add({
      blob: await readImageBlob(referencePath),
      contentType: "image/png",
      alt: `사용자 제공 관광 전략 PPT 참고 시안 ${index}페이지`,
      fit: "fill",
      position: { left: 0, top: 0, width: 1600, height: 900 },
    });
    image.name = `reference-slide-${String(index).padStart(2, "0")}`;

    // 사용한 원본 이미지는 슬라이드 발표자 노트에 출처로 기록한다.
    slide.speakerNotes.textFrame.setText(
      `[Sources]\n- User-provided reference image: ${referencePath}`,
    );

    const stem = `slide-${String(index).padStart(2, "0")}`;
    const png = await presentation.export({ slide, format: "png", scale: 1 });
    await writeBlob(path.join(previewDir, `${stem}.png`), png);

    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(previewDir, `${stem}.layout.json`), await layout.text());
  }

  // 전체 장표를 빠르게 비교할 수 있는 몽타주도 함께 만든다.
  const montage = await presentation.export({
    format: "webp",
    montage: true,
    scale: 1,
  });
  await writeBlob(path.join(previewDir, "deck-montage.webp"), montage);

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPath);
  console.log(outputPath);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
