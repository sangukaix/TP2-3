import fs from 'node:fs/promises';
import {Presentation, PresentationFile} from '@oai/artifact-tool';
const proto=JSON.parse(await fs.readFile('inspect.json','utf8'));
// The source masters/layouts and untouched slides are retained. Only the four
// user-requested content zones are redesigned; source headings are inherited.
for(const i of [4,7,8,10]) proto.slides[i].elements=proto.slides[i].elements.filter(e=>['title','eyebrow'].includes(e.name));
const p=Presentation.load(proto);
const C={blue:'#004EA2',cyan:'#00B7C9',ink:'#1D2227',slate:'#59636E',light:'#DCE5EF',bg:'#F4F7FA'};
function text(s,name,value,x,y,w,h,size=24,color=C.ink,bold=false){
 const o=s.shapes.add({name,geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 o.text=value; o.text.style={fontFamily:'Noto Sans KR',fontSize:size,color,bold,verticalAlignment:'middle',wrap:true};return o;
}
function rect(s,name,x,y,w,h,color){return s.shapes.add({name,geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:color,line:{fill:'none',width:0}});}
function header(s,title,eyebrow){
 const t=s.shapes.items.find(e=>e.name==='title');t.text=title;t.position={left:106,top:128,width:1390,height:66};t.text.style={fontFamily:'Noto Sans KR',fontSize:46,bold:true,color:C.blue};
 let e=s.shapes.items.find(e=>e.name==='eyebrow');if(!e)e=text(s,'eyebrow','',106,75,1390,32,18,C.cyan,true);
 e.text=eyebrow;e.position={left:106,top:75,width:1390,height:32};
 rect(s,'heading-rule',106,220,1388,2,C.blue);
}
function table(s,name,x,y,w,h,rows,cols,widths){
 const t=s.tables.add({rows,columns:cols,left:x,top:y,width:w,height:h,columnWidths:widths,values:Array.from({length:rows},()=>Array(cols).fill('기획서 데이터'))});t.name=name;
 for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?C.blue:r===rows-1?'#DEF1F5':r%2?'#FFFFFF':'#EAF0F6';
  cell.text.style={fontFamily:'Noto Sans KR',fontSize:23,color:r===0?'#FFFFFF':c===cols-1?C.blue:C.ink,bold:r===0||c===cols-1};
 }
 t.borders.assign({style:'solid',fill:'#FFFFFF',width:2});return t;
}
// 5: equal-height native charts, shared zero baseline and exact monthly figures.
{
 const s=p.slides.items[4];header(s,'향후 3개월 방문자·관광소비액','MACHINE LEARNING FORECAST');
 text(s,'intro','사업 기간의 월별 자연추세',106,243,1388,42,24,C.slate);
 for(const [j,x,label,color] of [[0,106,'방문자 수',C.blue],[1,834,'관광소비액',C.cyan]]){
  text(s,j?'consumption-title':'prediction-title',label,x,308,650,48,31,color,true);
  const chart=s.charts.add('bar',{position:{left:x,top:378,width:650,height:320},categories:['9월','10월','11월'],series:[{name:label,values:[1,2,3],fill:color}],hasLegend:false,barOptions:{direction:'column',grouping:'clustered',gapWidth:100},yAxis:{min:0,numberFormatCode:'#,##0',majorGridlines:{fill:C.light,width:1}},xAxis:{textStyle:{fontSize:21,fontFamily:'Noto Sans KR'}},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:23,bold:true,color}},chartFill:'none',plotAreaFill:'none'});
  chart.name=j?'spending-chart':'visitors-chart';
  text(s,j?'consumption-note':'prediction-body','정확한 월별 값',x,713,650,78,23,C.slate);
 }
 text(s,'forecast-chart-note','학습기간 · 모델 · 정확한 수치',106,813,1388,29,19,C.slate);
 text(s,'forecast-reading-body','예측 신뢰도 및 해석 한계',106,850,1388,30,18,C.slate);
}
// 8: large regional baseline next to an editable numeric KPI/derivation table.
{
 const s=p.slides.items[7];header(s,'자연추세 → 목표 KPI','BASELINE & MEASURABLE TARGETS');
 text(s,'subtitle','예측과 운영 목표를 구분합니다.',106,243,1388,48,24,C.slate);
 rect(s,'baseline-panel',106,320,416,408,C.blue);
 text(s,'baseline-label','지역 전체 자연추세',134,343,360,38,26,'#FFFFFF',true);
 text(s,'baseline-period','최종 월',134,395,360,34,21,'#BBD5EE');
 text(s,'visit-label','월 방문자 수',134,450,360,32,22,'#FFFFFF');
 text(s,'visit-forecast','2,632,315명',134,490,360,59,40,'#FFFFFF',true);
 text(s,'spend-label','월 관광소비액',134,577,360,32,22,'#FFFFFF');
 text(s,'spend-forecast','899억 원',134,617,360,61,40,'#FFFFFF',true);
 text(s,'kpi-heading','목표 KPI',569,319,919,43,30,C.blue,true);
 table(s,'kpi-table',570,382,920,276,4,3,[280,250,390]);
 text(s,'kpi-derivation','목표 수치의 산출근거',570,683,920,98,23,C.slate);
 text(s,'kpi-footnote','사업 참여 목표는 지역 전체의 추가 방문·소비 예측이 아닙니다.',106,812,1388, sixty(),21,C.slate);
}
function sixty(){return 62;}
// 9: keep the blue table style while expanding quantity/basis column.
{
 const s=p.slides.items[8];header(s,'견적','REFERENCE ESTIMATE · NOT A FINAL QUOTE');
 text(s,'budget-table-title','시범 운영 참고 견적',106,250,1388,50,32,C.blue,true);
 table(s,'budget-table',106,324,1388,408,8,3,[352,690,346]);
 text(s,'intro','확정 견적이 아닌, 운영 규모 검토를 위한 임시 참고 견적입니다.',106,754,1388,38,23,C.blue,true);
 text(s,'dashboard-body','수량·단가 가정과 공식 사례의 참고 범위를 구분합니다.',106,800,1388,70,21,C.slate);
}
// 11: provenance page style; populated/paginated without truncating names.
{
 const s=p.slides.items[10];header(s,'근거·데이터 · 전체 사용 내역','EVIDENCE & TRACEABILITY');
 text(s,'source-subtitle','관측 데이터 · 머신러닝 예측치 · 공식 사례',106,242,1388,44,24,C.slate);
 for(let c=0;c<3;c++){
  let x=106+c*474;
  rect(s,`source-rule-${c}`,x,309,432,3,c===1?C.cyan:C.blue);
  for(let r=0;r<5;r++){
   text(s,`source-${c}-${r}`,'',x,328+r*99,432,94,21,C.ink);
  }
 }
 text(s,'source-footer','전체 원문 URL은 각 항목의 링크와 발표자 노트에 보존합니다.',106,850,1388,28,18,C.slate);
}
await fs.writeFile('template-frame-map.json',JSON.stringify({outputSlides:proto.slides.map((s,i)=>({outputSlide:i+1,sourceSlide:i+1,reuseMode:'duplicate-slide',narrativeRole:[4,7,8,10].includes(i)?'requested numeric/provenance redesign':'unchanged',editTargets:[{action:[4,7,8,10].includes(i)?'replace':'preserve',reason:'User-requested design edit; source theme retained'}]})),omittedSourceSlides:[]},null,2));
await fs.writeFile('source-notes.txt','Design source: tourism_strategy_12_slide_template.pptx. Only slides 5/8/9/11 redesigned. Other slide parts and all theme bytes preserved at package merge. New charts and tables remain native/editable.');
await (await PresentationFile.exportPptx(p)).save('artifact_template.pptx');
console.log('Exported redesigned template');
