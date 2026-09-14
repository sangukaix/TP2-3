from PIL import Image
from pathlib import Path
import json
p=Path(__file__).parent
meta=json.loads((p/'frames.json').read_text(encoding='utf-8'))
frames=[];durations=[]
for i,row in enumerate(meta['frames']):
    im=Image.open(p/'frames'/row['file']).convert('RGB')
    frames.append(im.quantize(colors=192,method=Image.Quantize.MEDIANCUT))
    nexttime=meta['frames'][i+1]['time'] if i+1<len(meta['frames']) else meta['duration']
    durations.append(max(20,round((nexttime-row['time'])/10)*10))
frames[0].save(p/'home_workflow.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=False,disposal=2)
print({'frames':len(frames),'duration_ms':sum(durations),'bytes':(p/'home_workflow.gif').stat().st_size,'stages':sorted(set(r['step'] for r in meta['frames']))})
