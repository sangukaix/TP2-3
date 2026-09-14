import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const dir='C:/Users/Admin/mbca/TP2-3/storage/previews/final_presentation';
const source='C:/Users/Admin/mbca/TP2-3/output/presentation/OLIGO-K_프로젝트발표_최종본.pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(source));
await fs.mkdir(dir+'/final_render',{recursive:true});
for(let i=0;i<p.slides.items.length;i++){
 const slide=p.slides.items[i];
 const png=await p.export({slide,format:'png',scale:1.25});
 await fs.writeFile(dir+'/final_render/slide-'+String(i+1).padStart(2,'0')+'.png',new Uint8Array(await png.arrayBuffer()));
 console.log('Rendered',i+1);
}
