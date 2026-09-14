"""Editable calculation diagrams drawn from the report, never invented values."""
from .proposal_layout_v7 import text, rect, header, BLUE, CYAN, ORANGE, SLATE, PALE, WHITE
from .proposal_calculation_basis import calculation_basis


def arrow(slide,name,x,y,w=72):
    text(slide,name,'→',x,y,w,65,42,CYAN,True)


def metric(slide,name,label,value,sub,x,y,w=380):
    text(slide,name+'-label',label,x,y,w,38,24,BLUE,True)
    text(slide,name+'-value',value,x,y+48,w,60,38,ORANGE,True)
    text(slide,name+'-sub',sub,x,y+117,w,76,21,SLATE)


def calculations(slide,report):
    b=calculation_basis(report);e=b['estimate'];totals={r['key']:r for r in b['totals']}
    header(slide,'산출 근거 ① 전망 × 목표율 → 운영 예산')
    observed=(report.get('target_proposal_basis') or {}).get('observed_visitors')
    scenario=report.get('execution_scenario') or {}
    visitor=scenario.get('visitor_target_pct',0);spend=scenario.get('spending_target_pct',0)
    text(slide,'basis-origin','공식 사례의 실적',106,212,365,37,25,BLUE,True)
    if observed:
        for i,(value,label) in enumerate([('25%','강진 발표 증가율'),('80%','계획 계수'),('20%','초기 목표')]):
            x=106+i*306
            text(slide,f'basis-factor-{i}',value,x,263,243,69,48,ORANGE,True)
            text(slide,f'basis-factor-label-{i}',label,x,342,243,39,24,SLATE)
            if i<2:text(slide,f'basis-operator-{i}','×' if i==0 else '=',x+235,276,63,55,38,CYAN,True)
    else:
        text(slide,'basis-formula','운영 사례 참고 → 초기 목표 5%',106,263,925,69,48,ORANGE,True)
        text(slide,'basis-factor-labels','전후 효과 추정이 아닌 계획 가정',106,342,925,39,24,SLATE)
    rect(slide,'basis-divider',1050,224,3,155,CYAN)
    text(slide,'basis-actual','이 기획서의 최종월 목표',1081,223,413,42,25,BLUE,True)
    text(slide,'basis-actual-value',f'방문 +{visitor:g}%\n소비 +{spend:g}%',1081,275,413,94,31,ORANGE,True)
    text(slide,'basis-meaning','20%는 ML이 찾아낸 사업 효과가 아닙니다. 80%는 계획 가정이며 인구 보정값도 아닙니다.' if observed else '5%는 ML이 찾아낸 사업 효과가 아닌 초기 계획 목표이며 생성 후 조정할 수 있습니다.',106,399,1388,42,23,SLATE)
    rect(slide,'basis-mid-rule',106,459,1388,2,'DCE5EF')
    v=totals.get('visitors');s=totals.get('spending')
    if v and s:
        metric(slide,'baseline','01  ML 기준 전망',f"{v['baseline']/1e4:,.2f}만 명",f"관광소비 {s['baseline']/1e8:,.2f}억 원\n사업기간 3개월 월별 합계",106,484,391)
        arrow(slide,'to-target',499,539)
        metric(slide,'uplift','02  단계 목표를 합산',f"+{v['additional']/1e4:,.2f}만 명",f"추가 소비 +{s['additional']/1e8:,.2f}억 원\n최종월까지 ⅓ → ⅔ → 전체 목표율",587,484,418)
        arrow(slide,'to-volume',1000,539)
        quantity=e.get('quantity')
        metric(slide,'quantity','03  직접 운영할 규모',f'{quantity:,}건' if quantity is not None else '참고 총액 배분',
               f"추가 방문 목표 × {e.get('pilot_share_pct',1):g}% 올림\n참여량 배분 가정 · 전환율 아님" if quantity is not None else '사용자가 지정한 금액으로 조정',1091,484,403)
    text(slide,'monthly-formula','월 목표 = 월 기준 전망 × (1 + 최종월 목표율 × 경과월/전체월). 방문 합계는 3개월 고유 인원과 다릅니다.',106,695,1388,38,20,SLATE)
    rect(slide,'budget-band',106,752,1388,101,PALE)
    items=e.get('items') or []
    if e.get('subtotal_krw') and items:
        benefit=items[0]['amount'];other=e['subtotal_krw']-benefit
        parts=[('직접 혜택',benefit),('운영·시스템·홍보·평가',other),('예비비 10%',e['reserve_krw']),('견적 총액',e['total_krw'])]
        for i,(label,value) in enumerate(parts):
            x=125+i*352
            text(slide,f'budget-label-{i}',label,x,766,307,30,20,BLUE,True)
            text(slide,f'budget-value-{i}',f'{value/10000:,.1f}만 원',x,802,307,40,28,BLUE,True)
            if i<3:text(slide,f'budget-sign-{i}','=' if i==2 else '+',x+306,788,43,42,30,CYAN,True)
    else:text(slide,'budget-custom',f"참고 견적 총액 {e.get('total_krw',0):,}원 · 지정한 총액을 항목 비중으로 배분",126,774,1348,61,28,BLUE,True)
    text(slide,'budget-assumption','단가·인력 처리량은 기획 가정입니다. 항목별 곱셈 산식은 바로 앞 견적표에 제시합니다.',106,860,1388,29,18,SLATE)


def ml_to_plan(slide,report):
    b=calculation_basis(report)
    header(slide,'산출 근거 ② 7개 전망은 어떻게 기획에 쓰이나')
    text(slide,'ml-period',f"공식 월별 데이터 {b['source_period']}  →  지표별 저장 모델  →  사업기간의 전망",106,211,1388,42,25,SLATE)
    rect(slide,'ml-two',106,283,628,219,PALE)
    rect(slide,'ml-five',792,283,702,219,'EDF2FA')
    text(slide,'two-heading','2개 · 수치 기준선',126,301,580,43,29,BLUE,True)
    text(slide,'two-metrics','방문자 수  /  관광소비액',126,357,580,44,31,BLUE,True)
    text(slide,'two-use','전망 그래프 → 추가 목표 인원·소비액 계산\n방문·소비 전망은 후보 비교에도 함께 전달',126,417,580,71,23,SLATE)
    text(slide,'five-heading','5개 · 관광 흐름 진단',812,301,662,43,29,BLUE,True)
    text(slide,'five-metrics','체류시간 · 숙박일수 · 숙박방문 비율\n내비게이션 검색 · 숙박 목적지 검색',812,357,662,76,27,BLUE,True)
    text(slide,'five-use','관심 → 방문 → 체류·숙박의 흐름을 살필 참고 입력',812,454,662,38,22,SLATE)
    text(slide,'ml-arrow-left','↓',382,507,100,55,37,CYAN,True)
    text(slide,'ml-arrow-right','↓',1080,507,100,55,37,CYAN,True)
    text(slide,'handoff','서버가 7개 전망·전년 대비 변화·모델 평가를 근거 묶음으로 전달',106,568,1388,43,29,BLUE,True)
    stages=[('공식 사례',f"저장 {b['case_count']}건\n운영 방식·출처 확인"),
            ('Qwen 후보 비교',f"설계 후보 {b['candidate_count']}개\n지역 조건 + 사례 판단"),
            ('Gemma 본문', '선정 사업·근거를\n실행 계획으로 작성'),
            ('검수·출력', '코드·로컬 검수\n웹 · Word · PPT')]
    for i,(title,body) in enumerate(stages):
        x=106+i*359
        text(slide,f'flow-title-{i}',title,x,644,305,42,27,BLUE,True)
        text(slide,f'flow-body-{i}',body,x,701,305,75,25,SLATE)
        if i<3:arrow(slide,f'flow-arrow-{i}',x+301,688,58)
    rect(slide,'ml-boundary-rule',106,800,1388,2,CYAN)
    seasonal=[key for key,value in b['models'].items() if value=='전년 동월 기준모델']
    note=f"이 보고서: {len(seasonal)}개 지표는 전년 동월 기준모델을 사용. " if seasonal else ''
    text(slide,'ml-boundary',note+'ML은 관광지표를 예측하고, 사례·사업의 최종 선택은 문서와 LLM 판단으로 수행합니다.\n7개 값으로 학습한 별도 사업 추천 모델은 아닙니다. 입력을 읽었다는 사실과 판단의 타당성은 구분합니다.',106,823,1388,65,21,SLATE)
