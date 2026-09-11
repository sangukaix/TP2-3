"""Editable document layout revision; saved facts and models remain immutable.

Coordinates follow the approved 1600x900 template. Missing target values are
never filled with an arbitrary uplift. Five saved tasks map to four display
stages, with all final evaluation tasks retained in the fourth stage.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import math
import re
from pathlib import Path

from PIL import ImageFont
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.util import Pt

from . import proposal_presentation_v3 as base
from .proposal_evidence import complete_source_records, source_display_name, build_reference_estimate
from .report_projection import select_report_forecast

BLUE='004EA2'; CYAN='00B7C9'; ORANGE='FF6B00'; INK='1D2227'
SLATE='59636E'; BG='F4F7FA'; PALE='E6F4F7'; WHITE='FFFFFF'; BORDER='DCE5EF'
EMU=9525


def copy_text(value, *, limit=None):
    """Normalize wording without truncating it. The layout handles text fit."""
    return re.sub(r'\s+', ' ', str(value or '')).replace('…', '').replace('...', '').replace('자연추세', 'ML예측치').replace('자연 추세', 'ML예측치').strip()


@lru_cache(maxsize=80)
def _font(size):
    # PowerPoint uses the installed Malgun Gothic face on development Windows.
    candidates = ('C:/Windows/Fonts/NotoSansKR-VF.ttf', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'C:/Windows/Fonts/malgun.ttf')
    path = next((p for p in candidates if Path(p).is_file()), None)
    if path:
        return ImageFont.truetype(path, max(1, round(size)))
    return ImageFont.load_default(size=max(1, round(size)))


def _width(text, size):
    return _font(size).getlength(text)


def wrap_words(text, width, size):
    """Wrap at spaces; prefer 70/30 for two lines, never a lone last word."""
    result=[]
    for paragraph in str(text).splitlines() or ['']:
        start=len(result)
        words=paragraph.split()
        # File names and source IDs can be long unspaced tokens. Wrap them too.
        expanded=[]
        for word in words:
            chunk=''
            for char in word:
                if chunk and _width(chunk+char,size)>width:
                    expanded.append(chunk);chunk=''
                chunk+=char
            if chunk:expanded.append(chunk)
        words=expanded
        if not words:
            result.append(''); continue
        if _width(' '.join(words), size)<=width:
            result.append(' '.join(words)); continue
        splits=[]
        for i in range(1,len(words)):
            a,b=' '.join(words[:i]),' '.join(words[i:])
            wa,wb=_width(a,size),_width(b,size)
            if max(wa,wb)<=width:
                score=abs(wa/(wa+wb)-.70)+(1 if len(words[i:])==1 and len(words)>3 else 0)
                splits.append((score,a,b))
        if splits:
            _,a,b=min(splits);result.extend([a,b]);continue
        line=[]
        for word in words:
            if line and _width(' '.join(line+[word]),size)>width:
                result.append(' '.join(line));line=[]
            line.append(word)
        if line:result.append(' '.join(line))
        if len(result)-start >= 3:
            tail=(result[-2]+' '+result[-1]).split()
            choices=[]
            for i in range(1,len(tail)-1):
                a,b=' '.join(tail[:i]),' '.join(tail[i:])
                wa,wb=_width(a,size),_width(b,size)
                if max(wa,wb)<=width:
                    choices.append((abs(wa/(wa+wb)-.70),a,b))
            if choices:
                _,a,b=min(choices);result[-2:]=[a,b]
    return result


def fit_text(shape, value, size=24, color=INK, bold=False):
    value=str(value or '').replace('…','').replace('...','').replace('자연추세','ML예측치')
    w=shape.width/EMU-12; h=shape.height/EMU-8
    chosen=size
    while chosen>12:
        lines=wrap_words(value,w,chosen)
        if len(lines)*chosen*1.25<=h and all(_width(t,chosen)<=w for t in lines):break
        chosen-=.5
    lines=wrap_words(value,w,chosen)
    if len(lines)*chosen*1.25>h+1 or any(_width(t,chosen)>w+1 for t in lines):
        raise ValueError(f'PPT 본문이 표시 공간을 초과합니다: {shape.name}. 문장 또는 배치를 조정해야 합니다.')
    tf=shape.text_frame;tf.clear();tf.word_wrap=False;tf.auto_size=MSO_AUTO_SIZE.NONE
    tf.margin_left=tf.margin_right=EMU*6;tf.margin_top=tf.margin_bottom=EMU*4
    tf.vertical_anchor=MSO_ANCHOR.TOP
    for i,line in enumerate(lines):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph()
        p.space_before=p.space_after=Pt(0);p.line_spacing=Pt(chosen*.75*1.25)
        p._p.get_or_add_pPr().set('eaLnBrk','0')
        r=p.add_run();r.text=line;r.font.name='Noto Sans KR';r.font.size=Pt(chosen*.75)
        r.font.color.rgb=RGBColor.from_string(color);r.font.bold=bold


def text(slide,name,value,x,y,w,h,size=24,color=INK,bold=False):
    s=slide.shapes.add_textbox(*(round(v*EMU) for v in (x,y,w,h)));s.name=name
    fit_text(s,value,size,color,bold);return s


def rect(slide,name,x,y,w,h,color):
    s=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,*(round(v*EMU) for v in (x,y,w,h)))
    s.name=name;s.fill.solid();s.fill.fore_color.rgb=RGBColor.from_string(color);s.line.fill.background();return s


def clear(slide, keep=()):
    for s in list(slide.shapes):
        if s.name not in keep:s._element.getparent().remove(s._element)


def header(slide,title,subtitle=''):
    clear(slide);slide.background.fill.solid();slide.background.fill.fore_color.rgb=RGBColor.from_string(BG)
    text(slide,'title',title,100,75,1400,85,48,BLUE,True)
    rect(slide,'title-rule',106,181,1388,3,BLUE)
    if subtitle:text(slide,'subtitle',subtitle,106,198,1388,55,23,SLATE)


def short_title(report):
    from .proposal_presentation_v4 import _selected_candidate
    strategy=base._first_strategy(report);candidate=_selected_candidate(report)
    options=[strategy.get('title'),candidate.get('title')]
    for title in options:
        title=copy_text(title)
        title=re.sub(r'\s*모델\s*도입$', ' 사업', title)
        if title and len(title)<=32 and not any(t in title for t in ('사무관리','민간경상보조','연구용역','예산 편성')):return title
    original=copy_text(strategy.get('title'))
    region=str(report.get('region_name') or '지역').split()[-1]
    if '야간' in original:return f'{region} 야간관광 운영 사업'
    if '환급' in original or '반값' in original:return f'{region} 여행비 환급 사업'
    # Preserve the full administrative description in the body and notes.
    return f'{region} 관광 운영 사업'


def project(prs,report,photo_sources):
    from .proposal_presentation_v4 import _selected_candidate
    s=prs.slides[2];clear(s,('visitor-photo','hero-source-bg','hero-source-label','title-rule'))
    strategy=base._first_strategy(report);candidate=_selected_candidate(report)
    text(s,'title',short_title(report),561,80,950,135,46,BLUE,True)
    text(s,'s3-thesis',copy_text(strategy.get('solution') or candidate.get('mechanism') or report.get('summary')),561,275,895,190,34,INK,True)
    text(s,'s3-detail-label','사업 대상과 운영 범위',561,500,895,45,26,BLUE,True)
    detail='\n'.join(filter(None,[candidate.get('target_users'),candidate.get('pilot_scope'),strategy.get('timeframe')]))
    text(s,'s3-detail',detail or '대상·운영 권역은 사업 착수 전 협의합니다.',561,554,895,95,26,SLATE)
    rect(s,'s3-operation-rule',567,678,6,127,CYAN)
    text(s,'s3-operation',copy_text(candidate.get('prerequisites') or '참여처와 담당 역할을 정하고 이용·정산 절차를 확인한 뒤 시범 운영합니다.'),589,683,850,135,25,SLATE)
    label=next((o for o in s.shapes if o.name=='hero-source-label'),None)
    if label:
        if photo_sources:
            src=photo_sources[0];loc=src.get('address') or src.get('addr1') or src.get('location') or report.get('region_name')
            caption=f"{loc} · {src.get('title') or '지역 관광명소'}"
        else:caption='참고 이미지 · 실제 장소 사진 아님'
        label.top=832*EMU;label.height=60*EMU
        background=next((o for o in s.shapes if o.name=='hero-source-bg'),None)
        if background:
            background.left=label.left; background.top=label.top-6*EMU
            background.width=label.width; background.height=label.height+12*EMU
        fit_text(label,caption,17,WHITE)


def chart(slide,name,x,y,w,h,scenario,key,divisor):
    data=CategoryChartData();data.categories=scenario['categories'][:3]
    # Keep native workbook cells and chart XML caches at identical precision.
    # 8 decimals in 억 원 retain single-won resolution; raw values stay in notes.
    data.add_series('ML예측치',[round(v/divisor,8) for v in scenario['baseline_'+key][:3]])
    if scenario['has_target']:data.add_series('목표 KPI',[round(v/divisor,8) for v in scenario['target_'+key][:3]])
    shape=slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS,*(round(v*EMU) for v in (x,y,w,h)),data);shape.name=name
    c=shape.chart;c.has_legend=True;c.legend.position=XL_LEGEND_POSITION.BOTTOM;c.legend.include_in_layout=False
    c.legend.font.name='맑은 고딕';c.legend.font.size=Pt(14)
    for axis in (c.category_axis,c.value_axis):
        axis.tick_labels.font.name='맑은 고딕';axis.tick_labels.font.size=Pt(13)
        axis.tick_labels.font.color.rgb=RGBColor.from_string(SLATE)
        axis.format.line.color.rgb=RGBColor.from_string(BORDER)
    c.value_axis.minimum_scale=0;c.value_axis.tick_labels.number_format='#,##0'
    c.value_axis.has_major_gridlines=True;c.value_axis.major_gridlines.format.line.color.rgb=RGBColor.from_string(BORDER)
    for series,color in zip(c.series,(BLUE,ORANGE)):
        series.format.line.color.rgb=RGBColor.from_string(color);series.format.line.width=Pt(3)
        series.marker.style=XL_MARKER_STYLE.CIRCLE;series.marker.size=7
        series.marker.format.fill.solid();series.marker.format.fill.fore_color.rgb=RGBColor.from_string(color)
    return shape


def detail(prs,report):
    from .proposal_presentation_v4 import _selected_candidate,_scenario_for_display
    s=prs.slides[3];strategy=base._first_strategy(report);candidate=_selected_candidate(report)
    header(s,'사업 설계와 3개월 목표')
    blocks=[('사업내용',candidate.get('mechanism') or strategy.get('solution')),
            ('타겟 목표',(candidate.get('target_users') or '선택 지역 방문객')+'\n'+(candidate.get('pilot_scope') or '협의된 시범 권역')),
            ('진행순서 및 소요기간',f"{strategy.get('timeframe') or '일정 협의'}\n준비 → 실행 점검 → 시범 운영 → 평가"),
            ('목표 KPI',strategy.get('kpi') or '측정 지표와 목표 수준을 착수 전에 확정합니다.')]
    for i,(label,body) in enumerate(blocks):
        x=106+i*354;rect(s,f'block-{i}',x,222,326,213,WHITE)
        rect(s,f'block-rail-{i}',x,222,326,5,CYAN if i%2 else BLUE)
        text(s,f'block-title-{i}',label,x+12,239,302,45,25,BLUE,True)
        text(s,f'block-body-{i}',copy_text(body),x+12,295,302,127,22,SLATE)
    scenario,demo=_scenario_for_display(report)
    for i,(key,label,divisor) in enumerate([('visitors','관광객 방문자 수 · 만 명',1e4),('spending','관광소비액 · 억 원',1e8)]):
        x=106+i*714;text(s,f'chart-title-{i}',label,x,454,674,43,27,BLUE,True)
        if scenario:chart(s,f'comparison-chart-{i}',x,505,674,275,scenario,key,divisor)
        else:text(s,f'chart-missing-{i}','사업 기간의 ML예측치 미제공',x,550,674,100,26,SLATE)
    note='목표 KPI는 계획값이며 사업 효과를 학습한 예측치가 아닙니다.'
    if scenario and not scenario['has_target']:note='지역 전체 목표율 미입력: ML예측치만 표시합니다. 목표율 확정 후 비교선이 추가됩니다.'
    if demo or report.get('layout_target_sample'):note='디자인 확인용 예시 목표율 적용. '+note
    cautions=select_report_forecast(report).get('notes') or []
    if cautions:note+=' '+ ' '.join(cautions)
    text(s,'comparison-note',note,106,812,1388,53,19,SLATE)


def cases(prs,report):
    from .proposal_presentation_v4 import _selected_case
    s=prs.slides[5];header(s,'유사지역사례')
    selected,assessment=_selected_case(report)
    from .proposal_presentation_v4 import _selected_candidate
    decision=report.get('planning_decision') or {}
    chosen_ids=[*(_selected_candidate(report).get('case_source_ids') or []),*(decision.get('recommended_case_ids') or [])]
    if selected.get('source_id') not in chosen_ids:selected={};assessment={}
    rows=[r for r in complete_source_records(report) if r.get('source_type') in ('benchmark_case','case_study','official_case')]
    rows=([selected] if selected else [])+[r for r in rows if r.get('source_id')!=selected.get('source_id')]
    for i in range(4):
        x=106+(i%2)*714;y=235+(i//2)*304;r=rows[i] if i<len(rows) else {}
        rect(s,f'case-panel-{i}',x,y,674,278,PALE if i==0 and selected else WHITE)
        if i==0 and selected:rect(s,'selected-rail',x,y,6,278,CYAN)
        text(s,f'case-number-{i}',f'{i+1:02d}',x+20,y+18,60,52,34,CYAN,True)
        text(s,f'case-badge-{i}','선정 사례' if i==0 and selected else '기타 유사 사례',x+90,y+20,552,38,20,BLUE,True)
        parts=copy_text(r.get('summary')).split(' · ')
        label=' · '.join(parts[:2]) if len(parts)>=3 else r.get('title')
        text(s,f'case-title-{i}',copy_text(label or '추가 공식 사례 미확보'),x+20,y+70,634,74,28,INK,True)
        body=r.get('operating_model') or r.get('summary') or '확인된 자료가 없어 사례를 임의로 추가하지 않습니다.'
        if i==0 and assessment.get('adaptation'):
            body='적용 조건: '+assessment['adaptation']
        text(s,f'case-body-{i}',copy_text(body),x+20,y+151,634,109,22,SLATE)


def roadmap(prs,report):
    s=prs.slides[6];header(s,'4단계 실행 가이드','상단은 진행 흐름, 하단은 담당자가 확인할 업무와 완료 기준입니다.')
    steps=[v for v in base._first_strategy(report).get('implementation_steps') or [] if isinstance(v,dict)]
    groups=[[v] for v in steps[:3]]+[steps[3:]]
    while len(groups)<4:groups.append([])
    roles=('사업 총괄','운영·정산 담당','현장 운영 담당','사업·평가 담당')
    labels=('준비와 협의','운영 절차 점검','시범 운영','운영 개선과 평가')
    rows=[['단계·기간','담당 역할(제안)','세부 실행 업무','확인 산출물·완료 기준']]
    checks=('모집 기준·지원 한도·담당자 확인', '개인정보·취소·중복 신청·정산 절차 시험', '현장 안내·안전 점검·일별 이용 기록', '비용·민원·이용 실적을 기준기간과 비교')
    for i,group in enumerate(groups):
        x=106+i*355
        rect(s,f'pipeline-{i}',x,272,316,68,BLUE if i%2==0 else CYAN)
        text(s,f'step-{i}-label',f'STEP {i+1:02d}  {labels[i]}',x+8,282,300,48,24,WHITE,True)
        if i<3:text(s,f'arrow-{i}','→',x+320,282,37,48,27,CYAN,True)
        schedule=' / '.join(dict.fromkeys(copy_text(v.get('schedule')) for v in group if v.get('schedule')))
        text(s,f'step-{i}-period',schedule or '일정 협의',x,351,316,65,22,SLATE)
        tasks='\n'.join(copy_text(v.get('task')) for v in group) or '업무 범위 협의'
        if len(tasks)<65:tasks+='\n확인 제안: '+checks[i]
        rows.append([f'{i+1:02d}\n{schedule}',roles[i], tasks,
                     '\n'.join(copy_text(v.get('deliverable')) for v in group) or '완료 기준 협의'])
    native_table(s,'execution-table',rows,106,422,1388,402,[165,195,565,463],23)
    text(s,'roadmap-note','담당 역할과 확인 항목은 제안입니다. 착수 전 담당자·협력처·운영시간·안전·정산 조건을 확정합니다.',106,839,1388,48,20,SLATE)


def native_table(slide,name,rows,x,y,w,h,widths,size=24):
    sh=slide.shapes.add_table(len(rows),len(rows[0]),*(round(v*EMU) for v in (x,y,w,h)));sh.name=name;t=sh.table
    for col,width in zip(t.columns,widths):col.width=round(width*EMU)
    t.rows[0].height=round(52*EMU)
    for row in list(t.rows)[1:]:row.height=round((h-52)/(len(rows)-1)*EMU)
    for ri,row in enumerate(rows):
        for ci,value in enumerate(row):
            c=t.cell(ri,ci);c.margin_left=c.margin_right=10*EMU;c.margin_top=c.margin_bottom=7*EMU
            c.fill.solid();c.fill.fore_color.rgb=RGBColor.from_string(BLUE if ri==0 else WHITE if ri%2 else 'EAF1F6')
            # Cell text has the same no-word-splitting layout policy as shape text.
            width=widths[ci]-65;height=t.rows[ri].height/EMU-14;chosen=size
            while chosen>12 and (len(wrap_words(str(value),width,chosen))*chosen*1.25>height or any(_width(v,chosen)>width for v in wrap_words(str(value),width,chosen))):chosen-=.5
            if len(wrap_words(str(value),width,chosen))*chosen*1.25>height+1:
                raise ValueError(f'PPT 표 본문 초과: {name} {ri}행 {ci}열')
            c.text='\n'.join(wrap_words(str(value),width,chosen));c.text_frame.word_wrap=False
            for p in c.text_frame.paragraphs:
                p.space_before=p.space_after=Pt(0);p.line_spacing=1.12;p._p.get_or_add_pPr().set('eaLnBrk','0')
                for r in p.runs:
                    r.font.name='Noto Sans KR';r.font.size=Pt(chosen*.75);r.font.bold=ri==0 or ci==0
                    r.font.color.rgb=RGBColor.from_string(WHITE if ri==0 else INK)
    return sh


def kpi(prs,report):
    from .proposal_presentation_v4 import _scenario_for_display
    from .proposal_slide_content import _people,_money
    s=prs.slides[7];scenario,demo=_scenario_for_display(report)
    header(s,'ML예측치와 목표 KPI','같은 월·같은 지표를 비교합니다. 목표와 예측의 차이는 달성해야 할 규모입니다.')
    rows=[['지표·기준월','ML예측치','목표 KPI','달성 필요량']]
    for key,label,fmt in [('visitors','방문자 수',_people),('spending','관광소비액',_money)]:
        for i,month in enumerate(scenario['categories'][:3] if scenario else ['예측치 미제공']):
            b=scenario['baseline_'+key][i] if scenario else None
            target=scenario['target_'+key][i] if scenario and scenario['has_target'] else None
            rows.append([f'{month} {label}',fmt(b) if b is not None else '미제공',fmt(target) if target is not None else '목표율 미입력',
                         fmt(target-b) if target is not None else '산출 보류'])
    native_table(s,'kpi-comparison-table',rows,106,280,1388,430,[360,342,343,343],27)
    note='목표 KPI = 해당 월 ML예측치 × (1 + 해당 월 목표율). 입력한 최종 목표율까지 월별로 단계 적용합니다.'
    if not scenario or not scenario['has_target']:
        e=build_reference_estimate(report)
        note=f"지역 전체 목표율은 미입력입니다. 별도 운영 제안: 지원 가능량 {e['quantity']:,}건, 완료 목표 {e['redemption_count']:,}건(가정 80%). 참여 건수를 신규 관광객 수로 더하지 않습니다."
    text(s,'kpi-calculation',note,106,742,1388,90,23,SLATE)
    if demo or report.get('layout_target_sample'):text(s,'demo-label','목표율은 디자인 확인용 예시입니다.',106,839,1388,37,19,ORANGE)


def provenance(prs,report):
    from .proposal_slide_content import _source_groups,_copy_source_slide
    source=prs.slides[10];groups=_source_groups(report)
    entries=[]
    for title,items in groups:
        for value,url in items:entries.append((title.split(' · ')[0],copy_text(value).replace('한국관광공사 TourAPI','').strip(),url))
    if not entries:entries=[('출처','저장된 출처 레코드 없음','')]
    # Allocate height by wrapped text; append pages instead of hiding sources.
    page_rows=[[]];col=0;y=270
    for kind,value,url in entries:
        height=max(48,len(wrap_words(f'{kind}  {value}',434,18))*18*1.25+18)
        if y+height>850:
            col+=1;y=270
        if col==3:
            page_rows.append([]);col=0
        page_rows[-1].append((kind,value,url,col,y,height))
        y+=height
    pages=len(page_rows)
    slides=[source]+[_copy_source_slide(prs,source) for _ in range(pages-1)]
    for page,(s,portion) in enumerate(zip(slides,page_rows)):
        header(s,'근거·데이터·출처',f'전체 자료명과 머신러닝 모델  {page+1}/{pages} · 파란 자료명을 누르면 원문으로 이동합니다.')
        for i,(kind,value,url,col,y,height) in enumerate(portion):
            shape=text(s,f'reference-{i}',f'{kind}  {value}',106+col*470,y,446,height-3,18,BLUE)
            if url.startswith(('https://','http://')):
                for p in shape.text_frame.paragraphs:
                    for r in p.runs:r.hyperlink.address=url;r.font.underline=False
    thank=prs.slides._sldIdLst[11];prs.slides._sldIdLst.remove(thank);prs.slides._sldIdLst.append(thank)
    return pages


def finish(prs,report):
    """Remove the superseded forecast page and refresh the exact table of contents."""
    sid=prs.slides._sldIdLst[4];prs.part.drop_rel(sid.rId);prs.slides._sldIdLst.remove(sid)
    labels=['프로젝트 개요','사업 설계와 3개월 목표','유사지역사례','4단계 실행 가이드','ML예측치와 목표 KPI','견적','지속 운영 방안','근거·데이터·출처','맺음말']
    toc=prs.slides[1]
    for slide in (prs.slides[0],prs.slides[-1]):
        for sh in slide.shapes:
            if sh.name=='report-topic':fit_text(sh,sh.text.replace('\n',' '),28,BLUE,True)
            elif sh.name=='org-owner':fit_text(sh,'관광 전략 검토용',18,SLATE)
    for i in range(10):
        col,row=divmod(i,5)
        for shape in list(toc.shapes):
            if shape.name==f'toc-{col}-{row}-label':
                fit_text(shape,labels[i] if i<len(labels) else '',26,INK,True)
            elif i==9 and shape.name.startswith(f'toc-{col}-{row}'):
                shape._element.getparent().remove(shape._element)
    for slide in prs.slides:
        for shape in slide.shapes:
            if not getattr(shape,'has_text_frame',False) or not shape.text.strip():continue
            for p in shape.text_frame.paragraphs:
                p._p.get_or_add_pPr().set('eaLnBrk','0')
                for r in p.runs:r.text=r.text.replace('자연추세','ML예측치').replace('…','').replace('...','')
    assert len([s for s in prs.slides[3].shapes if s.has_chart]) in (0,2)
    if len(prs.slides)<11:raise ValueError('본문 9장·출처 1~2장·감사 장 구조를 확인해주세요.')
