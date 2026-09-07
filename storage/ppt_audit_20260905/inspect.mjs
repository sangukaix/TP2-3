import fs from 'node:fs/promises';
import {FileBlob, PresentationFile} from '@oai/artifact-tool';
const p = await PresentationFile.importPptx(await FileBlob.load('C:/Users/Admin/mbca/TP2-3/ai_server/app/templates/tourism_strategy_12_slide_template.pptx'));
await fs.writeFile('inspect.json',JSON.stringify(p.toProto()));
await fs.writeFile('inspect.txt',(await p.inspect({kind:'slide,layout,chart,table',maxChars:30000})).ndjson);
console.log(p.help('shapes',{search:'delete remove',include:['index','notes'],maxChars:2000}));
console.log(JSON.stringify({slideKeys:Object.keys(p.toProto().slides[4]),elements:p.toProto().slides[4].elements?.map(e=>Object.keys(e))}));
