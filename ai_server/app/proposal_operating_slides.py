"""Editable operating-volume and scenario evidence in the approved theme."""
import json

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.opc.packuri import PackURI
from pptx.util import Pt

from .proposal_layout_v7 import EMU, text, rect
from .proposal_theme_spicus import GRAY, DARK, MUTED, WHITE, RED, OCEAN, JADE, rounded, center, get
from .proposal_infographics import icon, route


def title(slide, name, subtitle):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb=RGBColor.from_string(GRAY)
    text(slide,'editorial-kicker','2. 사업 목표',106,35,680,43,23,RED,True)
    text(slide,'title',name,106,86,1388,77,40,DARK,True)
    lead=text(slide,'operating-intro',subtitle,106,176,1388,62,26/.75,MUTED)
    center(lead)


def amount(value):
    return f'{value/1e8:,.2f}억 원' if value>=1e8 else f'{value/10000:,.0f}만 원'


def operating_page(slide, plan, report=None):
    title(slide,'2.3 운영 규모와 산출 근거','운영량을 먼저 제안하고, 참여와 추가 방문을 차례로 계산합니다')
    c=plan['central']
    stages=[('지역 관광 규모',f"월평균 {plan['mean_monthly_visitors']/10000:,.1f}만 명",'저장 ML 방문 전망',OCEAN,'database'),
            ('제안 운영 규모',f"{plan['sites']}개 {plan['site_label']}",f"월 {plan['days_per_month']}일 · 하루 {plan['sessions_per_day']}회",RED,'map-pinned'),
            ('참여 목표',f"{c['participants']:,}명",f"편성 한도 {plan['funded_capacity']:,} × 이용률 {c['utilization_pct']:g}%",JADE,'users'),
            ('추가 방문 목표',f"{c['additional_visitors']:,}명",f"참여 목표 × 추가 방문 비중 {c['additional_visitor_share_pct']:g}%",OCEAN,'target')]
    for i,(label,value,detail,color,symbol) in enumerate(stages):
        x=106+i*355
        panel=rect(slide,f'capacity-stage-{i}',x,277,325,247,WHITE);rounded(panel)
        icon(slide,f'capacity-icon-{i}',symbol,x+22,295,46)
        text(slide,f'capacity-label-{i}',label,x+81,305,228,39,24,DARK,True)
        text(slide,f'capacity-value-{i}',value,x+20,369,289,62,33,color,True)
        text(slide,f'capacity-detail-{i}',detail,x+20,446,289,61,20,MUTED)
        if i<3:route(slide,f'capacity-arrow-{i}',[(x+329,393),(x+352,393)])
    panel=rect(slide,'capacity-formula-panel',106,550,1388,128,WHITE);rounded(panel)
    text(slide,'capacity-formula-label','운영량 계산',127,568,250,40,25,JADE,True)
    text(slide,'capacity-formula',plan['capacity_formula'],385,567,1080,48,27,DARK,True)
    text(slide,'capacity-limit',f"{plan.get('operating_period', plan['forecast_period'])} 운영 · 예상 견적 {amount(plan['estimate']['total_krw'])}",385,620,1080,38,23,MUTED)
    if plan.get('status')=='budget_below_operating_floor':
        get(slide,'capacity-limit').text=f"기본 운영비 가정 {amount(plan['minimum_operating_budget_krw'])} · 입력 예산 내 현재 운영안 미편성"
    from .proposal_case_outcomes import report_outcome
    case=next(iter(plan['case_sources']),{})
    outcome=report_outcome(report) if report else None
    comparison='공식 사례의 운영 방식을 참고하며, 발표 실적을 우리 지역 정원으로 환산하지 않습니다.'
    source_url=case.get('source_url')
    if outcome:
        delta=outcome['after']-outcome['before']
        comparison=(f"{outcome['title']}: {outcome['metric']} {outcome['before']:,} → "
                    f"{outcome['after']:,}명, 차이 {delta:+,}명. 우리 지역 운영 정원과 집계 기준이 다릅니다.")
        source_url=outcome['references'][1 if len(outcome['references'])>1 else 0][1]
    text(slide,'capacity-case','사례와의 차이',106,700,230,36,23,JADE,True)
    copy=text(slide,'capacity-case-name',comparison,350,700,1144,62,21,DARK)
    if source_url:copy.click_action.hyperlink.address=source_url
    region=(report or {}).get('region_name') or '선택 지역'
    rule=(f"{region}: 월평균 ML 방문 {plan['mean_monthly_visitors']/10000:,.1f}만 명을 규모 입력으로 사용.\n"
          f"거점은 √(월평균 방문 ÷ 10만)을 올려 1~12개로 제안한 뒤 예산을 반영합니다. 인구 보정·학습 모델의 결과는 아닙니다.")
    text(slide,'capacity-scale-rule',rule,106,767,1388,60,20,MUTED)
    label=plan.get('participation_basis','참여 목표의 비율과 운영 정원을 함께 적용합니다.')
    disclosure=text(slide,'capacity-disclosure',label,
         106,832,1388,57,19,MUTED)
    participation=next((r for r in plan['rate_basis'] if r.get('metric')=='utilization_rate'),{})
    if participation.get('source_url'):disclosure.click_action.hyperlink.address=participation['source_url']


def scenario_chart(slide,name,x,key,color,money=False):
    plan=key[0]; metric=key[1]
    data=CategoryChartData();data.categories=[s['label'] for s in plan['scenarios']]
    divisor=10000 if money else 1
    # The chart is shown in whole 만원; retain two decimal places in its editable
    # workbook to avoid binary-float/cache discrepancies. Full won values stay in notes.
    data.add_series('계획 시나리오',[round(s[metric]/divisor,2) for s in plan['scenarios']])
    obj=slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,round(x*EMU),round(351*EMU),round(652*EMU),round(300*EMU),data)
    obj.name=name
    chart=obj.chart;chart.has_legend=False;chart.has_title=False
    chart.category_axis.tick_labels.font.size=Pt(15)
    chart.category_axis.tick_labels.font.name='Noto Sans KR'
    chart.value_axis.tick_labels.font.size=Pt(11)
    chart.value_axis.minimum_scale=0
    chart.value_axis.has_major_gridlines=True
    chart.value_axis.major_gridlines.format.line.color.rgb=RGBColor.from_string('DEE4E8')
    series=chart.series[0]
    for i,point in enumerate(series.points):
        point.format.fill.solid();point.format.fill.fore_color.rgb=RGBColor.from_string(color if i==1 else 'B9C9D4')
        point.format.line.fill.background()
    chart.plots[0].has_data_labels=True
    labels=chart.plots[0].data_labels;labels.position=XL_LABEL_POSITION.OUTSIDE_END
    labels.font.size=Pt(15);labels.font.bold=True;labels.number_format='#,##0'
    for element in chart._chartSpace.xpath('.//c:axId | .//c:crossAx'):
        element.set('val',str(abs(int(element.get('val')))))
    return obj


def scenario_page(slide,plan):
    title(slide,'2.4 기대 변화의 시나리오','같은 운영량에서 이용률과 추가 방문 비중을 달리한 계획 범위')
    for i,(label,metric,color,money) in enumerate([('추가 방문 목표 · 명','additional_visitors',OCEAN,False),
                                                   ('추가 소비 목표 · 만 원','additional_spending_krw',JADE,True)]):
        x=106+i*714
        panel=rect(slide,f'scenario-panel-{i}',x,270,674,434,WHITE);rounded(panel)
        text(slide,f'scenario-label-{i}',label,x+24,289,626,47,29,color,True)
        scenario_chart(slide,f'operating-scenario-chart-{i}',x+10,(plan,metric),color,money)
        c=plan['central'];pct=c['spending_growth_pct' if money else 'visitor_growth_pct']
        text(slide,f'scenario-growth-{i}',f"기준 시나리오 · 기간 합계 ML 전망 대비 +{pct:.2f}%",x+24,653,626,40,22,color,True)
    rates=' / '.join(f"{s['label']} {s['utilization_pct']:g}%·{s['additional_visitor_share_pct']:g}%" for s in plan['scenarios'])
    text(slide,'scenario-rates','이용률·추가 방문 비중  '+rates,106,730,1388,45,23,DARK)
    formula=plan['spending_formula']
    text(slide,'scenario-consumption-formula',formula,106,780,1388,48,21,MUTED)
    text(slide,'scenario-disclaimer','계획 가정을 바꾼 범위이며 통계적 신뢰구간이 아닙니다. 소비/방문 비율은 실측 객단가가 아니며 사업 효과는 사후 확인합니다.',106,845,1388,42,18,MUTED)


def append_operating_pages(prs,report):
    basis=report.get('target_proposal_basis') or {};plan=basis.get('capacity_plan') or {}
    if not plan.get('central'):return
    for i,slide in enumerate(prs.slides,1):slide.part._partname=PackURI(f'/ppt/slides/slide{i}.xml')
    anchor=next((i for i,s in enumerate(prs.slides) if get(s,'title') is not None and '2.2 ' in get(s,'title').text),6)
    for offset,draw in enumerate((operating_page,scenario_page),1):
        slide=prs.slides.add_slide(prs.slides[-1].slide_layout)
        if draw is operating_page:draw(slide,plan,report)
        else:draw(slide,plan)
        if basis.get('target_mode')=='user' or (report.get('reference_estimate') or {}).get('user_adjusted'):
            text(slide,'manual-target-notice','사용자 지정 목표·견적과 별도로 계산한 운영 참고안입니다.',106,237,1388,29,18,RED)
        slide.notes_slide.notes_text_frame.text=json.dumps(plan,ensure_ascii=False,indent=2)
        sid=next(s for s in prs.slides._sldIdLst if s.id==slide.slide_id)
        prs.slides._sldIdLst.remove(sid);prs.slides._sldIdLst.insert(anchor+offset,sid)
    for i,slide in enumerate(prs.slides):
        page=get(slide,'editorial-page')
        if page is not None:page.text=f'{i+1:02d} / {len(prs.slides):02d}'
        elif i not in (0,1,len(prs.slides)-1):
            page=text(slide,'editorial-page',f'{i+1:02d} / {len(prs.slides):02d}',1393,45,101,28,15,MUTED)
        if page is not None:
            for p in page.text_frame.paragraphs:
                p.alignment=PP_ALIGN.RIGHT
                for r in p.runs:r.font.size=Pt(11.25);r.font.name='Noto Sans KR';r.font.color.rgb=RGBColor.from_string(MUTED)
