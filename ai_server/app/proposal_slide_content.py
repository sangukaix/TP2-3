"""Data bindings for the approved v6 native-chart/table template.

The layout is authored in the PPT template. This module only fills inherited
objects and duplicates its provenance layout when a complete inventory needs it.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import unicodedata
from urllib.parse import urlparse
from typing import Any

from . import proposal_presentation_v3 as base
from .proposal_evidence import build_reference_estimate, complete_source_records, source_display_name, METRIC_LABELS
from .report_projection import select_report_forecast


def _text(slide, name, value):
    base._set_text(slide, name, str(value))


def _table(slide, rows):
    from .proposal_presentation_v4 import _set_cell_text
    tables = [s.table for s in slide.shapes if getattr(s, 'has_table', False)]
    if len(tables) != 1:
        raise ValueError('편집 가능한 표가 누락되었습니다.')
    table = tables[0]
    if len(table.rows) != len(rows) or len(table.columns) != len(rows[0]):
        raise ValueError('템플릿 표와 데이터 행·열 수가 다릅니다.')
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            _set_cell_text(table.cell(r, c), str(value))


def _people(n):
    return f'{n:,.0f}명'


def _money(n):
    return f'{n / 1e8:,.2f}억 원' if n >= 1e8 else f'{n / 1e4:,.0f}만 원'


def _period_label(period):
    import re
    return re.sub(r'(20\d{2})(0[1-9]|1[0-2])', r'\1.\2', str(period))


def populate_ml(prs, report):
    from .proposal_presentation_v4 import _scenario_for_display, _set_chart, BLUE, CYAN, _remove_shape
    slide = prs.slides[4]
    scenario, demo = _scenario_for_display(report)
    selection = select_report_forecast(report)
    ml = report.get('ml_analysis') or {}
    _text(slide, 'eyebrow', 'MACHINE LEARNING FORECAST' + (' · 교육용 더미' if demo else ''))
    charts = [s for s in slide.shapes if getattr(s, 'has_chart', False)]
    if not scenario:
        _text(slide, 'title', '머신러닝 예측치 · 제공 상태 확인')
        _text(slide, 'intro', '기획 기간 전체를 채우는 저장 예측값이 없습니다. 임의 수치나 0으로 대체하지 않습니다.')
        for shape in charts: _remove_shape(slide, shape.name)
        for name in ('prediction-title','consumption-title'):_text(slide,name,'예측치 미제공')
        for name in ('prediction-body','consumption-note','forecast-chart-note'):_text(slide,name,'')
        _text(slide,'forecast-reading-body',' · '.join(selection.get('notes') or []))
        return
    values = scenario['baseline_visitors']; money = scenario['baseline_spending']
    labels = scenario['categories']
    _text(slide,'title',f"사업 기간 {len(values)}개월 · 방문자·관광소비액")
    _text(slide,'intro',f"{_period_label(selection.get('period') or scenario['period'])} | 지역 전체의 월별 자연추세이며 사업 효과를 학습한 예측은 아닙니다.")
    _text(slide,'prediction-title','방문자 수  |  단위: 만 명')
    _text(slide,'consumption-title','관광소비액  |  단위: 억 원')
    for chart,series,color,divisor,label in zip(charts,[values,money],[BLUE,CYAN],[1e4,1e8],['방문자 수','관광소비액']):
        _set_chart(chart, labels, [(label,[n/divisor for n in series],color)])
        chart.chart.value_axis.minimum_scale=0
        chart.chart.plots[0].data_labels.number_format='#,##0.00'
        chart.chart.plots[0].data_labels.number_format_is_linked=False
    # No observed month is silently spliced into the forecast chart.
    _text(slide,'prediction-body','  ·  '.join(f'{m} {_people(n)}' for m,n in zip(labels,values)))
    _text(slide,'consumption-note','  ·  '.join(f'{m} {_money(n)}' for m,n in zip(labels,money)))
    metrics=(ml.get('evaluation') or {}).get('metrics') or {}
    names=' / '.join(str((metrics.get(k) or {}).get('selected_model') or '모델명 미기록') for k in ('visitors','spending_krw'))
    _text(slide,'forecast-chart-note',f"학습 원자료 {_period_label(ml.get('source_period') or '미기록')} | 방문·소비 모델: {names}")
    weak=any((metrics.get(k) or {}).get('model_reliability')=='below_baseline_on_test' for k in ('visitors','spending_krw'))
    warning='시험구간에서 전년동월 단순예측보다 오차가 큽니다. 탐색적 참고값이며 성과 약속에 사용하지 않습니다.' if weak else '실제 관측값과 예측값은 다를 수 있습니다. 장기 전망의 검증 범위는 출처 페이지에서 확인합니다.'
    _text(slide,'forecast-reading-body',warning)


def populate_kpi(prs, report):
    from .proposal_presentation_v4 import _scenario_for_display
    slide=prs.slides[7]; scenario,demo=_scenario_for_display(report)
    estimate=build_reference_estimate(report)
    _text(slide,'title','자연추세 → 목표 KPI')
    _text(slide,'subtitle','지역 전체 예측과 사업 참여 목표를 구분하고, 목표 수치는 운영 기록으로 검증합니다.' + (' [교육용 더미]' if demo else ''))
    _text(slide,'baseline-period',f"{scenario['categories'][-1]} · 최종 월" if scenario else '예측치 미제공')
    _text(slide,'visit-forecast',_people(scenario['baseline_visitors'][-1]) if scenario else '미제공')
    _text(slide,'spend-forecast',_money(scenario['baseline_spending'][-1]) if scenario else '미제공')
    if scenario and scenario['has_target']:
        v=scenario['target_visitors'][-1]; s=scenario['target_spending'][-1]
        rows=[['측정 지표','목표 KPI','자연추세 대비'],
              ['최종 월 방문자 수',_people(v),f"+{_people(v-scenario['baseline_visitors'][-1])}"],
              ['최종 월 관광소비액',_money(s),f"+{_money(s-scenario['baseline_spending'][-1])}"],
              ['기간','최종 월 기준',f"{scenario['period']}"]]
        derivation=(f"입력 목표율: 방문자 {scenario['visitor_target_pct']:g}% · 소비액 {scenario['spending_target_pct']:g}%. "
                    '목표 = 최종 월 자연추세 × (1 + 목표율). 이 비율을 실현할 사업 효과는 아직 검증되지 않았습니다.')
        note='목표 KPI는 입력된 계획값입니다. 정책 시행 효과를 학습한 머신러닝 예측값이 아닙니다.'
    else:
        q=estimate['quantity']; redeemed=estimate['redemption_count']
        if estimate['refund']:
            rows=[['측정 지표','목표 KPI','가정·산출기준'],['환급 완료 신청',f'{q:,}건',f"지원금 ÷ 평균 {estimate['unit_krw']:,}원"],
                  ['참여자 증빙 소비',_money(estimate['qualifying_spend_krw']),f'{q:,}건 × 평균 10만원'],
                  ['후속 상품권 사용',f'{redeemed:,}건',f'{q:,}건 × 사용 목표 80%']]
        else:
            rows=[['측정 지표','목표 KPI','가정·산출기준'],['혜택 지원 가능량',f'{q:,}건',f"혜택예산 ÷ {estimate['unit_krw']:,}원"],
                  ['이용·결제 완료',f'{redeemed:,}건',f'{q:,}건 × 완료 목표 80%'],
                  ['운영 점검',f"{estimate['months']}회",'매월 1회 집계·검토']]
        derivation=f"{estimate['months']}개월 소규모 운영을 가정한 제안 목표입니다. 지원량·평균 소비·80% 사용률은 관측 결과가 아닌 조정 가능한 가정입니다."
        note='지역 전체 목표율은 미입력입니다. 참여 건수≠추가 관광객, 증빙 소비≠증분 매출이며 지역 ML에 더하지 않습니다.'
    _table(slide,rows)
    _text(slide,'kpi-heading','목표 KPI · ' + ('입력 목표율 기준' if scenario and scenario['has_target'] else '참고 견적과 연결한 운영 제안'))
    _text(slide,'kpi-derivation',derivation)
    _text(slide,'kpi-footnote',note)


def populate_budget(prs, report):
    slide=prs.slides[8]; estimate=build_reference_estimate(report)
    _text(slide,'title','견적')
    _text(slide,'eyebrow','REFERENCE ESTIMATE · NOT A FINAL QUOTE')
    _text(slide,'budget-table-title',f"{estimate['months']}개월 참고 견적  |  총 {estimate['total_krw']/10000:,.0f}만 원")
    rows=[['세부 항목','수량 × 가정 단가','참고 금액']]
    rows.extend([[i['name'],i['basis'],f"{i['amount']/10000:,.0f}만 원"] for i in estimate['items']])
    rows.append(['합계','직접비 + 예비비 10%',f"{estimate['total_krw']/10000:,.0f}만 원"])
    _table(slide,rows)
    _text(slide,'intro','임시 참고 견적이며 확정 견적이 아닙니다. 계약 전 수량·세금·수수료와 비교견적을 확인합니다.')
    basis=('강진군 공식 환급방식(50%) 참고; 평균 10만원 소비·5만원 지원은 이번 기획의 가정. ' if estimate['refund'] else '참여 혜택·운영량은 소규모 시범을 위한 가정. ')
    _text(slide,'dashboard-body',basis+'인력·시스템·홍보·평가 금액은 가정 한도입니다. 신규 앱·키오스크 구축은 제외합니다.' + (' 입력 예산 상한보다 커 범위 축소가 필요합니다.' if not estimate['within_hard_budget'] else ''))


def _copy_source_slide(prs, source):
    # Reuse the approved source layout and inherited editable text slots.
    slide=prs.slides.add_slide(source.slide_layout)
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
    for shape in source.shapes:slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
    return slide


def _source_groups(report):
    """All records, not top-N; no ellipsis and no generic names substituted for files."""
    records=complete_source_records(report)
    data=[]; web=[]; assets=[]
    for i,s in enumerate(records,1):
        typ=s.get('source_type',''); title=source_display_name(s)
        page_reference = str(s.get('page_references') or '').strip()
        if page_reference:
            pages = [item.strip() for item in page_reference.split(',') if item.strip()]
            # A visible bibliography must stay legible; the complete page list remains
            # in slide notes and the source inventory JSON below.
            display_pages = page_reference if len(pages) <= 3 else (
                f'{pages[0]} 외 {len(pages) - 1}쪽 ({s.get("source_chunk_count", len(pages))}개 청크)'
            )
            title += f' · {display_pages}'
        prefix=f'D{i:02d}'
        if typ=='model_forecast':continue  # expanded into every actual metric below
        url=s.get('source_url') or s.get('url') or ''
        domain=urlparse(url).netloc or '원문 URL 미기록'
        period=s.get('observation_period') or s.get('published_or_updated_at') or ''
        if typ in {'open_api','official_open_api'}:
            assets.append((f'{prefix}  {title}\n한국관광공사 TourAPI',url))
        elif typ in {'dataset','nationwide_dataset','nationwide_bigdata_dataset','regional_dataset','regional_tourism_status','tourism_datalab'}:
            title=title.replace('한국관광 데이터랩 · ','').replace(str(report.get('region_name') or '')+' ','')
            # Source filenames can span 2024/2025 while the comparison query is
            # 2026. Do not relabel archive coverage as the query period.
            suffix = '' if s.get('source_file_name') else '\n' + str(period or report.get('period') or '기간 미기록')
            data.append((f'{prefix}  {title}{suffix}',url))
        else:
            web.append((f'{prefix}  {title}\n{domain}',url))
    ml=report.get('ml_analysis') or {}; metrics=(ml.get('evaluation') or {}).get('metrics') or {}
    selected_rows=select_report_forecast(report).get('rows') or []
    final=selected_rows[-1] if selected_rows else {}
    model=[]
    for key,item in metrics.items():
        name=str(item.get('selected_model') or '모델명 미기록')
        display='전년동월 계절 기준선' if name.startswith('seasonal_naive') else name
        value=final.get(key)
        if value is None:
            original=next((r for r in ml.get('forecasts',[]) if r.get('month')==final.get('month')), {})
            value=original.get(key)
        if value is None: formatted='예측치 미기록'
        elif key=='spending_krw': formatted=_money(value)
        elif key=='visitors': formatted=_people(value)
        else:
            unit={'stay_minutes':'분','lodging_nights':'일','lodging_rate_pct':'%','lodging_searches':'건','navigation_searches':'건'}.get(key,'')
            if key=='lodging_rate_pct':
                from .proposal_presentation_v4 import _display_percent
                formatted=_display_percent(value)
            else:
                formatted=f'{value:,.0f}{unit}' if key in ('stay_minutes','lodging_searches','navigation_searches') else f'{value:,.2f}{unit}'
        model.append((f'{METRIC_LABELS.get(key,key)}\n{display}\n최종 월 {formatted}', ''))
    if not model:model=[('예측 모델 메타데이터 없음\n검증되지 않은 수치는 표시하지 않습니다.','')]
    for s in (build_reference_estimate(report)['sources'] if report.get('generation_mode') == 'offline_sample' else []):
        web.append((f"참고 견적 추가 조사  {s['title']}\n{urlparse(s['source_url']).netloc} · 2026-09-05",s['source_url']))
    # Retain actual forecast values for all metrics in speaker notes, alongside model IDs.
    return [('관측 데이터 · 전체 원자료 목록',data),('머신러닝 예측치 · 모든 모델',model),
            ('공식 사례·문서 · 전체 원문 목록',web),('관광자원·사진 · 전체 API 조회 목록',assets)]


def _wrapped_lines(text: str, width: int = 38) -> list[str]:
    """Predictable CJK-aware wrapping: preserves every character, never ellipsizes."""
    lines=[]
    for paragraph in text.split('\n'):
        current=''; units=0
        for char in paragraph:
            weight=2 if unicodedata.east_asian_width(char) in 'WF' else 1
            if units+weight>width and current:
                lines.append(current);current='';units=0
            current+=char;units+=weight
        lines.append(current)
    return lines


def populate_provenance(prs, report):
    source=prs.slides[10]
    groups=_source_groups(report); pages=[]
    # Fill three columns top-to-bottom with a measured line budget. A long source
    # moves to the next column/page instead of colliding with the following item.
    for title,entries in groups:
        if not entries:continue
        page=[]; column=0; y=330; counts=[0,0,0]
        for value,url in entries:
            lines=_wrapped_lines(value); height=max(78,len(lines)*27+18)
            if y+height>825 or counts[column]>=5:
                column+=1;y=330
            if column>=3:
                pages.append((title,page));page=[];column=0;y=330;counts=[0,0,0]
            # Exceptionally long entries get their own wide page, not clipped.
            if height>490:
                raise ValueError('출처명이 한 열의 표시 범위를 초과합니다. 출처 메타데이터를 확인해주세요.')
            slot=column*5+counts[column];counts[column]+=1
            page.append((slot,'\n'.join(lines),url,y,height));y+=height+15
        if page:pages.append((title,page))
    if not pages:pages=[('출처 미제공',[(0,'저장된 출처 레코드가 없습니다.','',330,90)])]
    created=[source]+[_copy_source_slide(prs,source) for _ in pages[1:]]
    # Keep the thank-you page at the end, after all provenance continuations.
    thank=prs.slides._sldIdLst[11]
    prs.slides._sldIdLst.remove(thank);prs.slides._sldIdLst.append(thank)
    for index,(slide,(title,entries)) in enumerate(zip(created,pages),1):
        _text(slide,'title','근거·데이터 · '+title.split(' · ')[0])
        _text(slide,'source-subtitle',f'{title}  |  {index}/{len(pages)}')
        filled={item[0]:item[1:] for item in entries}
        for slot in range(15):
            name=f'source-{slot//5}-{slot%5}'
            value,url,y,height=filled.get(slot,('','',330,78))
            _text(slide,name,value)
            shape=next(s for s in slide.shapes if s.name==name)
            shape.top=round(y*9525);shape.height=round(height*9525)
            from pptx.enum.text import MSO_ANCHOR
            from pptx.util import Pt
            from pptx.dml.color import RGBColor
            shape.text_frame.vertical_anchor=MSO_ANCHOR.TOP
            shape.text_frame.word_wrap=False
            for paragraph in shape.text_frame.paragraphs:
                paragraph.space_before=Pt(0);paragraph.space_after=Pt(0)
                paragraph.line_spacing=1.15
            if url.startswith(('https://','http://')):
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.hyperlink.address=url
                        run.font.underline=False
                        run.font.color.rgb=RGBColor(0,78,162)
        ml=report.get('ml_analysis') or {}
        if '머신러닝' in title:
            footer=f"원자료 {ml.get('source_period','미기록')} | 버전 {ml.get('model_version','미기록')} | 예측 원수치·지표별 검증값은 이 장의 노트에 모두 수록"
        else:
            footer='후보·보조 조회를 포함한 저장 근거 목록입니다. 파란 이름을 누르면 원문으로 이동합니다. 전체 URL·출처 ID는 노트에 보존합니다.'
        _text(slide,'source-footer',footer)
    return len(pages)


def apply_notes(prs,report,photo_sources):
    from .proposal_presentation_v4 import _selected_case
    from .proposal_evidence import saved_budget_view
    inventory=complete_source_records(report)
    estimate=build_reference_estimate(report) if report.get('generation_mode') == 'offline_sample' else saved_budget_view(report)
    sources=inventory+photo_sources+estimate['sources']
    source_lines=[]
    for s in sources:
        page_note = f" | {s.get('page_references')}" if s.get('page_references') else ''
        source_lines.append(f"{s.get('source_id','')} | {source_display_name(s)}{page_note} | {s.get('source_url') or s.get('url') or 'URL 미기록'}")
    block='[Sources]\n'+'\n'.join(dict.fromkeys(source_lines))+'\n[/Sources]'
    selected=select_report_forecast(report)
    numeric=json.dumps({'source_inventory': sources, 'selected_forecast':selected,'all_ml_forecasts':(report.get('ml_analysis') or {}).get('forecasts'),
                        'evaluation':(report.get('ml_analysis') or {}).get('evaluation'), 'execution_scenario':report.get('execution_scenario'),
                        'reference_estimate':estimate},ensure_ascii=False,indent=2)
    for i,slide in enumerate(prs.slides):
        method='관측값·저장 예측·계획 목표는 별개입니다. 문서용 참고 견적이며 원 보고서의 검수 결과를 변경하지 않습니다.'
        if i==7:method+=' 목표율 입력 시 최종 월의 자연추세와 목표를 비교합니다. 미입력 시 견적에 기반한 별도 참여 목표만 제안합니다.'
        narrative = '\n[Saved narrative]\n' + json.dumps(report.get('strategies') or [], ensure_ascii=False, indent=2) if i in (2,3,5,6) else ''
        slide.notes_slide.notes_text_frame.text=method+'\n'+block+narrative+ ('\n[Calculation audit]\n'+numeric if i in (4,7,8) or i>=10 else '')
