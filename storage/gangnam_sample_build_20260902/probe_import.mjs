import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "C:/Users/Admin/mbca/TP2-3/storage/previews/관광전략_완전편집형_12장_PPT템플릿.pptx";
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const title = presentation.resolve("sh/sryl4zqx");
const photo = presentation.resolve("im/n2tc3y1g");
console.log(JSON.stringify({
  slideCount: presentation.slides.items.length,
  titleName: title?.name,
  titleText: String(title?.text ?? ""),
  photoName: photo?.name,
  photoFrame: photo?.frame,
}, null, 2));
