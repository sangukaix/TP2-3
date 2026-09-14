"""Audit registered regions without LLM calls, training or SQL writes."""
import json
import argparse
import httpx
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
from ai_server.app.scripts.check_generation_readiness import inspect_region
from ai_server.ml.region_catalog import list_region_data_catalog
from ai_server.app.region_readiness_audit import AUDIT_PATH, file_signature, sql_signatures
from ai_server.app.report_projection import execution_target,select_report_forecast

def inspect(entry,reports):
    row={'region_code':entry.region_code,'region_name':entry.region_name,'verified':False,'data_ready':False,'issues':[]}
    try:
        before = file_signature(entry)
        data=inspect_region(entry.region_code)
        row['details']=data
        from ai_server.app.main import assess_data_freshness
        fresh=assess_data_freshness(data['latest_observed_month'])
        checks={'fresh':fresh.can_generate,'ml':data['ml_status']=='available',
                'targets':{'visitors','spending_krw','lodging_rate_pct','lodging_nights','stay_minutes','navigation_searches','lodging_searches'}.issubset(data['targets']),'sql_comparison':data['nationwide_available'],
                'peers':data['peer_count']>0,'cases':data['official_cases_allowed']>=4}
        row['checks']=checks;row['data_ready']=all(checks.values())
        row['issues']=[k for k,v in checks.items() if not v]
        after = file_signature(entry)
        if before != after:
            row['data_ready'] = False
            row['issues'].append('점검 도중 입력 파일 변경')
        row['input_signature'] = after
        matching=[r for r in reports if r['regionCode']==entry.region_code]
        if not matching:row['issues'].append('기획안 실생성·목표·출력 미검증')
        else:
            response=httpx.get('http://127.0.0.1:8112/ai/v1/strategy-reports/'+matching[0]['entryId'],timeout=30)
            response.raise_for_status();report=response.json()
            if execution_target(report) is None:row['issues'].append('방문자·소비 목표값 미저장')
            if not select_report_forecast(report)['complete']:row['issues'].append('사업기간 전망 누락')
            if not (report.get('quality_review') or {}).get('approved'):row['issues'].append('기획안 품질검수 미통과')
            if (report.get('quality_review') or {}).get('review_stale'):row['issues'].append('수정된 기획안 재검수 필요')
            if report.get('generation_mode') == 'offline_sample':row['issues'].append('실제 생성이 아닌 오프라인 샘플')
            ml=report.get('ml_analysis') or {}
            if ml.get('source_period')!=data['training_source_period']:row['issues'].append('저장 기획안의 학습기간 불일치')
            if not row['issues']:
                from ai_server.app.proposal_presentation import create_strategy_proposal_presentation
                from ai_server.app.proposal_document import create_strategy_proposal_document
                create_strategy_proposal_presentation(report)
                create_strategy_proposal_document(report)
                row['verified']=True
        # Never promote solely on file existence or old generation records.
    except Exception as exc:row['issues'].append('데이터 조회 실패: '+type(exc).__name__)
    return row

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-only', action='store_true', help='서버 실행 없이 생성 입력을 점검합니다. 실생성 승인을 부여하지 않습니다.')
    args=parser.parse_args()
    if args.data_only:
        reports=[]
    else:
        response=httpx.get('http://127.0.0.1:8112/ai/v1/strategy-reports',timeout=30)
        response.raise_for_status();reports=response.json()
    entries=list(list_region_data_catalog(enabled_only=True));rows=[]
    sql_before = sql_signatures()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(inspect,e,reports) for e in entries]
        for f in as_completed(jobs):
            r=f.result();rows.append(r);print(f"{len(rows)}/{len(entries)} {r['region_code']} data={r['data_ready']}",flush=True)
    sql_after = sql_signatures()
    for row in rows:
        code = row['region_code']
        row['sql_signature'] = sql_after.get(code)
        if not sql_after.get(code) or sql_before.get(code) != sql_after[code]:
            row['data_ready'] = False
            row['issues'].append('SQL 자료 점검 도중 변경 또는 누락')
    payload={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'completed','scope':'generation_inputs' if args.data_only else 'generation_inputs_and_saved_reports','regions':sorted(rows,key=lambda r:r['region_code'])}
    temporary=AUDIT_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(AUDIT_PATH)
    print('TOTAL',len(rows),'DATA_READY',sum(r['data_ready'] for r in rows),'VERIFIED',sum(r['verified'] for r in rows))

if __name__=='__main__':main()
