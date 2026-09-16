"""Local festival observations -> transparent research shortlist -> cited case cards.

This is a rule-based shortlist, not a trained recommender or a business-effect model.
No web/LLM call, raw-share access, participation-rate estimation, or ML retraining.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from pathlib import Path

from .case_scope import _location_parts
from .case_research_plan import build_case_research_plan
from .nationwide_context_store import _connect

VERSION = 'festival-shortlist-v1'
RELATIVE = Path('data/processed/festival_cases')


def comparison_festival_ids(cases: list[dict], brief: dict | None = None) -> list[str]:
    """Eligible external observations to assess, never a forced winning case."""
    from .case_recommendation import allowed_operation
    return [c['source_id'] for c in cases if c.get('source_id') and c.get('festival_statistics')
            and (c.get('retrieval_basis') or {}).get('kind') == 'external_benchmark'
            and allowed_operation(c, brief or {})]


def dataset_fingerprint(root: Path) -> str:
    path = root / RELATIVE / 'summary.json'
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else 'not_imported'


def load_catalog(root: Path, env: dict) -> tuple[list[dict], dict]:
    folder = root / RELATIVE
    if not (folder/'summary.json').is_file():
        return [], {'status':'not_imported','version':VERSION}
    try:
        summary = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        digest = summary['dataset_hash']
        status = {'version':VERSION,'dataset_hash':digest,'catalog_count':summary['festival_count']}
    except (OSError, ValueError, KeyError, TypeError):
        return [], {'version':VERSION,'status':'unavailable','error':'invalid_summary'}
    try:
        with _connect(env) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT payload_json FROM festival_case_catalog WHERE dataset_hash=%s ORDER BY festival_id',(digest,))
                rows = cursor.fetchall()
        if len(rows) != summary['festival_count']:
            raise ValueError('Festival catalog revision is incomplete')
        return [json.loads(r['payload_json']) if isinstance(r['payload_json'],str) else r['payload_json'] for r in rows], {**status,'status':'mysql'}
    except Exception as exc:
        # Same hashed processed snapshot; no invented data or substitute database.
        try:
            raw = (folder/'catalog.json').read_bytes()
            if sha256(raw).hexdigest() != digest:
                return [], {**status,'status':'unavailable','error':'snapshot_hash_mismatch'}
            return json.loads(raw)['festivals'], {**status,'status':'local_snapshot','mysql_error':type(exc).__name__}
        except (OSError, ValueError, KeyError, TypeError):
            return [], {**status,'status':'unavailable','error':'invalid_snapshot'}


def theme(name: str) -> str:
    for label, words in (
        ('식음·특산물',('커피','김치','젓갈','인삼','딸기','고추','치맥','다향','장류','송이','오곡','대게','쌀','치즈','한우','사과','홍삼','야생차')),
        ('공연·문화',('풍물','마임','록','음악','카니발','아리랑','탈춤','국악','흥타령','문화제','입춘','품바','만화')),
        ('자연·야외',('머드','뱃놀이','트레킹','산천어','송어','갯골','반딧불','대나무','장미','눈축제','억새','물축제','바닷길','나비')),
        ('역사·공예',('청자','도자기','찻사발','한지','옹기','모시','구석기','읍성','역사','시간여행','강감찬')),
    ):
        if any(w in name for w in words):
            return label
    return '지역문화'


def shortlist(catalog: list[dict], snapshot: dict, brief: dict | None = None, limit: int = 4) -> list[dict]:
    selected = str(snapshot.get('region_code') or '')
    province = _location_parts(snapshot.get('region_name'))[0]
    comparison = snapshot.get('nationwide_comparison') or {}
    peers = {str(r['region_code']) for r in comparison.get('peer_regions',[]) if comparison.get('available') and r.get('region_code')}
    groups = build_case_research_plan(snapshot)['signal_groups']
    priority = next((r['id'] for r in groups if r['search_priority_change_pct'] is not None), None)
    raw_resources = json.dumps(brief or {},ensure_ascii=False)
    resource_themes = [label for label, words in (
        ('자연·야외',('자연','생태','야외','수변')),('공연·문화',('공연','문화','공공시설')),
        ('식음·특산물',('시장','상권','음식')),('역사·공예',('역사','공예','문화유산')))
        if any(w in raw_resources for w in words)]
    candidates=[]
    years = re.findall(r'20\d{2}', str((snapshot.get('ml_analysis') or {}).get('latest_observed_month') or snapshot.get('period') or ''))
    cutoff = max(map(int, years)) if years else 9999
    for item in catalog:
        if not item.get('eligible'):
            continue
        item=deepcopy(item)
        item['annual']=[r for r in item['annual'] if r['year']<=cutoff]
        item['comparisons']=[r for r in item['comparisons'] if r['after_year']<=cutoff]
        if not item['annual']:
            continue
        last=item['annual'][-1]
        latest = next((c for c in reversed(item['comparisons']) if c['after_year']==last['year']),None)
        own=item['region_code']==selected
        # Keep local context even when declining. External success candidates need
        # increasing total AND external daily visits; totals alone reward longer events.
        good=bool(latest and all((latest[k]['change_pct'] or 0)>0 for k in ('daily','outside_daily')))
        if not own and not good:
            continue
        points={}
        if item['region_code'] in peers: points['동일 기간 관광지표 비교지역']=30
        if _location_parts(item['region_name'])[0]==province: points['같은 시도 조사 맥락']=10
        label=theme(item['name'])
        if label in resource_themes: points['선택한 자원과 축제명 주제 연결']=20
        if priority=='visit' and good: points['방문 전망 조사: 외지인·일평균 동반 증가']=15
        if priority=='spend' and label in ('식음·특산물','역사·공예'): points['소비 전망 조사: 상품·상권 연계 주제']=15
        if priority=='stay' and last['days']>=2: points['체류 전망 조사: 복수일 행사 운영 참고']=5
        points['최근 개최연도']=max(0,last['year']-2022)*2
        if good: points['방문 실적 비교 가능']=10
        item['retrieval_basis']={'kind':'local_context' if own else 'external_benchmark','score':sum(points.values()),
            'components':points,'theme':label,'priority_signal':priority,
            'rule':'함수 기반 조사 우선순위. 사업효과·인구/환경 유사도 점수가 아니며 소비·체류 개선은 조사 가설이다.'}
        candidates.append(item)
    candidates.sort(key=lambda r:(-r['retrieval_basis']['score'],r['festival_id']))
    own=next((r for r in candidates if r['region_code']==selected),None)
    result=[own] if own else []
    external=[r for r in candidates if r['region_code']!=selected]
    # Reserve different themes/regions, rather than choosing the largest growth outlier.
    for distinct in (True,False):
        for r in external:
            if len(result)>=limit: break
            if r in result: continue
            if distinct and any(x['region_code']==r['region_code'] or x['retrieval_basis']['theme']==r['retrieval_basis']['theme'] for x in result if x is not own): continue
            result.append(r)
    return result


def as_case(item: dict, dataset_hash: str) -> dict:
    last=item['annual'][-1]
    previous=next((r for r in item['annual'] if r['year']==last['year']-1),None)
    compare=next((c for c in item['comparisons'] if c['after_year']==last['year']),None)
    annual_source=item['sources']['annual']
    text=f"{last['year']}년 {last['days']}일, 전체 방문 {last['total']:,.0f}명, 외지인 {last['outside']:,.0f}명."
    if compare:
        growth=compare['total']['change_pct']
        daily=compare['daily']['change_pct']
        outside=compare['outside']['change_pct']
        if all(v is not None for v in (growth,daily,outside)):
            text=(f"{previous['year']}→{last['year']}년 전체 {previous['total']:,.0f}→{last['total']:,.0f}명 ({growth:+.2f}%). "
                  f"개최 {previous['days']}→{last['days']}일, 일평균 {daily:+.2f}%, 외지인 {outside:+.2f}%.")
    role='선택 지역의 기존 축제 현황' if item['retrieval_basis']['kind']=='local_context' else '타지역 축제 방문 실적 참고'
    basis=item['retrieval_basis']
    sources=list(item['sources'].values())
    return {'source_id':item['festival_id'],'document_type':'case_study','evidence_kind':'festival_statistics',
        'retrieval_method':'datalab_festival_table','region_code':item['region_code'],'region_name':item['region_name'],
        'case_region':item['region_name'],'intervention':item['name'],
        'problem_addressed':role+' · '+basis['theme'],'target_group':'축제 관측구역 방문자(현지인·외지인·외국인 구분)',
        'operating_model':f"{item['name']}를 {last['year']}년 {last['days']}일 개최한 문화관광축제 운영 사례. 세부 프로그램·예약·혜택은 이 CSV에 기록되어 있지 않으며 새로운 운영안은 제안으로 구분한다.",
        'duration':f"{last['year']}년 {last['days']}일",'public_budget':'CSV에 사업비 없음',
        'observed_result':text,'measurement_period':f"{item['annual'][0]['year']}~{last['year']}년 각 축제 개최기간",
        'evidence_strength':'medium','quantitative_result_approved':True,
        'operating_statistics':[],
        'transfer_conditions':['지역 지표와 자원에 맞춰 행사 콘텐츠·운영일·참여처를 새로 설계한다.',
                               '개최 일수는 사례 실적이며 우리 지역의 월 운영일·회차·정원으로 복사하지 않는다.'],
        'risks':['행사 전후 방문 차이는 사업 단독 효과·도시 순증 방문이 아니다.',
                 '관광소비 지표값은 원화·성장률로 변환하지 않는다. 정원·참여율·실측 객단가 자료는 없다.'],
        'source_title':'한국관광 데이터랩 · '+item['name']+' 방문자 추이',
        'source_url':annual_source['source_url'],'published_or_updated_at':'2026-08-20',
        'dataset_hash':dataset_hash,'source_files':sources,'retrieval_basis':basis,
        'festival_statistics':{'name':item['name'],'annual':item['annual'],'comparison':compare,'scope':item['scope'],
            'region_basis':item['region_basis'], 'source_file':annual_source,
            'indicator_values':[r for r in item['indicators'] if int(r['개최년도'])==last['year']],
            'indicator_rule':'원본 지표값만 보존. 산식·단위 미확인으로 성장률/원화/정원/참여율 변환 금지.',
            'audience':item['audience'], 'audience_period':'다운로드 CSV에 연도 열 없음; 최신 개최연도와 자동 결합하지 않음',
            'destination_examples':[{k:r.get(k) for k in ('구분','순위','목적지명','도로명주소','카테고리')} for r in item['destinations'][:3]],
            'destination_period':'다운로드 CSV에 연도 열 없음; 주변 검색 후보이며 제휴·실제 방문 증거 아님'}}


def collect_festival_cases(root: Path, env: dict, snapshot: dict, brief: dict | None = None) -> tuple[list[dict],dict]:
    catalog,status=load_catalog(root,env)
    chosen=shortlist(catalog,snapshot,brief)
    cards=[as_case(r,status['dataset_hash']) for r in chosen]
    return cards,{**status,'selected_count':len(cards),'selected_source_ids':[c['source_id'] for c in cards]}


def attach_festival_statistics(cases: list[dict]) -> list[dict]:
    """Bind numbers only to the exact named festival and its full region.

    The official operating document retains its ID/URL. The separate CSV file
    provenance is preserved; neither a regional match nor a keyword is enough.
    """
    statistical=[c for c in cases if c.get('retrieval_method')=='datalab_festival_table']
    replaced=set()
    result=[]
    for source in cases:
        if source in statistical:
            continue
        card=deepcopy(source)
        title=str(card.get('intervention') or '').replace(' ','')
        match=next((s for s in statistical
                    if s['intervention'].replace(' ','') in title
                    and _location_parts(s['case_region'])==_location_parts(card.get('case_region'))),None)
        if match:
            for key in ('festival_statistics','retrieval_basis','source_files','dataset_hash','observed_result','quantitative_result_approved'):
                card[key]=deepcopy(match[key])
            card['evidence_kind']='festival_document_and_statistics'
            replaced.add(match['source_id'])
        result.append(card)
    return result+[c for c in statistical if c['source_id'] not in replaced]
