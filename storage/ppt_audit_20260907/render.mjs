import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const path=process.argv[2];
const out=process.argv[3];
await fs.mkdir(out,{recursive:true});
const p=await PresentationFile.importPptx(await FileBlob.load(path));
for (const [i,slide] of p.slides.items.entries()) {
  const blob=await p.export({slide,format:'png',scale:1});
  await fs.writeFile(`${out}/slide-${i+1}.png`,new Uint8Array(await blob.arrayBuffer()));
  console.log(`Rendered ${i+1}`);
}
