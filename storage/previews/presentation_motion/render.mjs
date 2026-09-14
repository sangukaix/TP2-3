import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const dir='C:/Users/Admin/mbca/TP2-3/storage/previews/presentation_motion';
const file=process.argv[2]||dir+'/candidate.pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(file));
await fs.mkdir(dir+'/render',{recursive:true});
for(let i=0;i<p.slides.items.length;i++){
 const png=await p.export({slide:p.slides.items[i],format:'png',scale:1.25});
 await fs.writeFile(dir+'/render/slide-'+String(i+1).padStart(2,'0')+'.png',new Uint8Array(await png.arrayBuffer()));
}
console.log('Rendered',p.slides.items.length);
