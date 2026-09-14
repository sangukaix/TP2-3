from pathlib import Path
p=Path(__file__).parent
old=p.parent/'presentation_motion'
media=(old/'package_media.py').read_text(encoding='utf-8').replace("(p/'home_workflow.gif').read_bytes()","(p.parent/'presentation_motion/home_workflow.gif').read_bytes()")
(p/'package_media.py').write_text(media,encoding='utf-8')
final=(old/'finalize.mjs').read_text(encoding='utf-8').replace('presentation_motion','presentation_revision').replace('38장_모션_','40장_발표완성_').replace('[14,17,22,24,27,29,30,34,37]','[11,14,19,21,24,26,27,36,39]').replace('explicitTotalSlideCount:38','explicitTotalSlideCount:40').replace('requiredNativeChartOwnerSlides:[19]','requiredNativeChartOwnerSlides:[16]')
(p/'finalize.mjs').write_text(final,encoding='utf-8')
render=(old/'render.mjs').read_text(encoding='utf-8').replace('presentation_motion','presentation_revision').replace("await fs.writeFile(dir+'/render/slide-'","console.log('Rendering',i+1); await fs.writeFile(dir+'/render/slide-'")
(p/'render.mjs').write_text(render,encoding='utf-8')
