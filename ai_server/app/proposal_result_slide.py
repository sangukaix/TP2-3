"""Editable case comparison slide. No made-up or unbound performance metrics."""
import json
from PIL import Image
from .proposal_layout_v7 import text, rect, header, EMU, BLUE, CYAN, ORANGE, SLATE, PALE, WHITE
from .proposal_case_outcomes import report_outcome


def case_performance(slide, report):
    from .case_recommendation import report_cases
    from .case_images import case_image
    header(slide, '사례 실적')
    _, primary = report_cases(report)
    source = primary[0] if primary else {}
    result = report_outcome(report)
    title = result['title'] if result else ' · '.join(filter(None, [source.get('case_region'), source.get('intervention')]))
    text(slide,'result-title',title,106,211,1388,58,34,BLUE,True)
    text(slide,'result-scope',result['scope'] if result else '공식 자료에서 확인한 운영 사례',106,277,1388,42,22,SLATE)
    photo = (result or {}).get('photo') or case_image(source)
    rect(slide,'result-photo-panel',106,350,586,354,WHITE)
    if photo and photo['path'].is_file():
        with Image.open(photo['path']) as im:
            scale=min(586/im.width,354/im.height);w,h=im.width*scale,im.height*scale
        sh=slide.shapes.add_picture(str(photo['path']),int((106+(586-w)/2)*EMU),int((350+(354-h)/2)*EMU),int(w*EMU),int(h*EMU));sh.name='result-photo'
        cap=text(slide,'result-photo-source',photo['caption']+'\n출처: '+photo['credit'],106,715,586,63,19,SLATE)
        for p in cap.text_frame.paragraphs:
            for r in p.runs:r.hyperlink.address=photo['page_url']
    if result:
        before,after=result['before'],result['after'];delta=after-before;pct=delta/before*100
        text(slide,'result-metric',result['metric'],753,340,741,38,24,BLUE,True)
        # Bar lengths encode the two reported values, retaining editable labels.
        for i,(label,value,color) in enumerate([(result['before_label'],before,'8097B6'),(result['after_label'],after,BLUE)]):
            y=392+i*99
            text(slide,f'result-year-{i}',label,753,y,440,37,23,SLATE)
            rect(slide,f'result-bar-{i}',753,y+48,480*value/max(before,after),24,color)
            text(slide,f'result-count-{i}',f'약 {value/10000:,.1f}만 명',1250,y+32,244,56,29,BLUE,True)
        rect(slide,'result-change-band',753,615,741,111,PALE)
        text(slide,'result-change',f'{"↑" if delta >= 0 else "↓"} 약 {abs(delta)/10000:,.1f}만 명  |  {pct:+,.2f}%',775,630,695,58,43,ORANGE,True)
        text(slide,'result-change-formula',f'({after/10000:g}만 − {before/10000:g}만) ÷ {before/10000:g}만 × 100',775,687,695,29,19,SLATE)
        text(slide,'result-data-labels',result['before_note']+' / '+result['after_note'],753,739,741,51,18,SLATE)
        action=result['action'];foot=result['interpretation']
    else:
        # Budget/operating documents are not evidence of visitor growth. Preserve
        # useful operating information without importing another region's stats.
        verified_result=source.get('observed_result') if source.get('quantitative_result_approved') is True else None
        from .case_mechanism import case_mechanism_family
        from .proposal_infographics import icon, route
        family = case_mechanism_family(source)
        text(slide,'result-operation-label','사례에서 참고한 이용 흐름',753,345,741,49,30,'26323C',True)
        if family == 'spend_conversion' and any(w in str(source.get('operating_model')) for w in ('환급','돌려')):
            stages = [('지역에서 소비', '여행자가 지역 내에서 지출', 'coins', 'jade'),
                      ('혜택을 환급', '지출 일부를 상품권으로 지급', 'files', 'blue'),
                      ('지역 상점 재이용', '받은 혜택을 지역에서 다시 사용', 'map-pinned', 'ocean')]
        else:
            # General structure is explicitly an application guide, not invented
            # case-specific operating details or evidence of achieved growth.
            stages = [('공식 운영 확인', '사례의 대상·이용 방식 확인', 'files', 'blue'),
                      ('지역 조건 연결', '우리 지역 자원·참여처와 비교', 'map-pinned', 'ocean'),
                      ('실행안 구성', '일정·규모·집계 방법을 제안', 'coins', 'jade')]
        for i,(label,detail,kind,color) in enumerate(stages):
            y=410+i*98
            rect(slide,f'result-flow-panel-{i}',753,y,741,82,'F0F5F8')
            icon(slide,f'result-flow-icon-{i}',kind,773,y+15,48,color)
            text(slide,f'result-flow-title-{i}',label,838,y+10,628,30,24,'26323C',True)
            text(slide,f'result-flow-detail-{i}',detail,838,y+45,628,28,21,SLATE)
            if i<2:route(slide,f'result-flow-arrow-{i}',[(797,y+83),(797,y+97)],color='839BA7')
        text(slide,'result-operation',verified_result or source.get('operating_model') or '공식 사업 내용에 맞춰 운영 범위를 설계합니다.',753,717,741,73,20,SLATE)
        action='사례의 운영 내용 → 지역 조건에 맞춘 실행 계획'
        foot=('집계 기준: '+str(source.get('measurement_period') or '인용한 공식 자료의 집계 기간')+'. 우리 지역의 목표는 별도로 설정합니다.' if verified_result else
              '자료 구분: 운영 사례. 수치 목표와 견적은 뒤의 산출 근거에서 제시합니다.')
    text(slide,'result-action',action,106,799,1388,43,26,BLUE,True)
    text(slide,'result-interpretation',foot,106,851,1388,36,19,SLATE)
    slide.notes_slide.notes_text_frame.text=json.dumps({'selected_source':source,'export_evidence':result,
        'rule':'Facts refer only to the named event / period. Saved regional targets are unchanged.'},ensure_ascii=False,indent=2,default=str)
