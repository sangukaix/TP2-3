"""Read-only regional growth comparison from fingerprint-matched saved ML.

No population adjustment, model training, LLM, SQL writes, or raw-data changes.
Regional growth-rate mean is not growth of a deduplicated national tourist count.
"""
import hashlib
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'artifacts' / 'ml' / 'comparison'
VERSION = 'regional-yoy-v1'
LOCK = RLock()


def period_months(report):
    from .report_projection import select_report_forecast
    rows = select_report_forecast(report)['rows']
    return [str(r['month']).replace('-', '') for r in rows]


def rank(values, selected):
    # Competition rank; exact ties share a position.
    return 1 + sum(v > selected + 1e-9 for v in values)


def _inventory():
    import csv
    with (ROOT / 'data/catalog/region_data_registry.csv').open(encoding='utf-8-sig') as f:
        catalog = [r for r in csv.DictReader(f) if r['enabled'].lower() == 'true']
    entries = []
    for row in catalog:
        # Do not count a city and its administrative districts twice.
        if any(r['region_name'].startswith(row['region_name']+' ') for r in catalog):
            continue
        code = row['region_code']
        paths = [ROOT/f'artifacts/ml/{code}/demand_model.joblib',
                 ROOT/f'artifacts/ml/{code}/demand_model.metadata.json',
                 ROOT/f'data/processed/ml/{code}/monthly_demand.csv']
        if code == '11680' and not paths[2].exists():
            paths[2] = ROOT/'data/processed/gangnam_monthly_demand.csv'
        entries.append((row, paths))
    return entries


def snapshot(months, origin):
    import joblib
    import pandas as pd
    from ai_server.ml.validation import validate_monthly_data, data_fingerprint
    from ai_server.ml.gangnam_forecast import _recursive_forecasts
    months = list(months)
    entries = _inventory()
    signature = hashlib.sha256(json.dumps([
        VERSION, months, origin,
        [(r['region_code'], [(str(p), p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else (str(p), None) for p in paths])
         for r, paths in entries]], sort_keys=True).encode()).hexdigest()
    path = CACHE / (signature+'.json')
    with LOCK:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))

        def calculate(entry):
            row, paths = entry
            code = row['region_code']
            try:
                if not all(p.is_file() for p in paths): raise ValueError('missing_artifact')
                history = pd.read_csv(paths[2], dtype={'region_code':str, 'year_month':str})
                validate_monthly_data(history, code)
                artifact = joblib.load(paths[0])
                meta = json.loads(paths[1].read_text(encoding='utf-8'))
                fingerprint = data_fingerprint(history)
                if fingerprint != artifact.get('data_fingerprint') or fingerprint != meta.get('data_fingerprint'):
                    raise ValueError('fingerprint_mismatch')
                last = str(history.iloc[-1].year_month)
                if last != origin: raise ValueError('different_observation_cutoff')
                horizon = (int(months[-1][:4])-int(last[:4]))*12+int(months[-1][4:])-int(last[4:])
                if not 1 <= horizon <= 24: raise ValueError('outside_forecast_window')
                forecast = {r['month']:r for r in _recursive_forecasts(artifact, history, horizon)}
                previous = history.set_index('year_month')
                metrics = {}
                for key in ('visitors','spending_krw'):
                    values = [forecast[m][key] for m in months]
                    actual = [float(previous.loc[str(int(m)-100),key]) for m in months]
                    if any(v <= 0 for v in actual): raise ValueError('nonpositive_yoy_denominator')
                    metrics[key] = {'forecast':values, 'previous':actual,
                                    'growth_pct':(sum(values)/sum(actual)-1)*100}
                return {'region_code':code, 'region_name':row['region_name'], 'metrics':metrics,
                        'fingerprint':fingerprint, 'model_version':meta.get('version')}, None
            except Exception as exc:
                return None, {'region_code':code, 'reason':str(exc) if isinstance(exc,(ValueError,KeyError,FileNotFoundError)) else type(exc).__name__}

        rows, excluded = [], []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for row, error in pool.map(calculate, entries):
                (excluded if error else rows).append(error or row)
        result = {'version':VERSION,'months':months,'origin':origin,'rows':rows,'excluded':excluded,
                  'signature':signature,'population_adjusted':False,
                  'mean_method':'equal-weight mean of each region quarterly YoY growth',
                  'region_scope':'non-overlapping catalog regions with identical observation cutoff and valid saved model/history'}
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        os.replace(tmp,path)
        return result


def comparison(report):
    from .proposal_presentation_v4 import _scenario_for_display
    scenario, demo = _scenario_for_display(report)
    if not scenario or demo: return None
    months = period_months(report)
    if len(months) != 3: return None
    code = str(report.get('region_code') or (report.get('ml_analysis') or {}).get('region_code') or '')
    meta_path = ROOT/f'artifacts/ml/{code}/demand_model.metadata.json'
    if not meta_path.exists(): return None
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    ml = report.get('ml_analysis') or {}
    if not ml.get('data_fingerprint') or ml['data_fingerprint'] != meta.get('data_fingerprint'):
        return None
    origin = str(ml.get('latest_observed_month') or meta.get('source_period','').split('~')[-1]).replace('-', '')
    data = snapshot(months,origin)
    if len(data['rows']) < 20 or len({r['region_name'].split()[0] for r in data['rows']}) < 5:
        return None  # A lone cutoff-compatible region is not a national comparison.
    selected = next((r for r in data['rows'] if r['region_code']==code),None)
    if not selected: return None
    result = {'count':len(data['rows']),'months':months,'origin':origin,
              'signature':data['signature'],'region_code':code,'metrics':{},
              'population_adjusted':False,
              'cohort':[{'region_code':r['region_code'],'region_name':r['region_name'],
                         'visitors_yoy_pct':r['metrics']['visitors']['growth_pct'],
                         'spending_yoy_pct':r['metrics']['spending_krw']['growth_pct']} for r in data['rows']]}
    for key, short in [('visitors','visitors'),('spending_krw','spending')]:
        row = selected['metrics'][key]
        if any(not math.isclose(a,b,abs_tol=1,rel_tol=1e-8) for a,b in zip(row['forecast'],scenario['baseline_'+short])):
            return None  # Never mix a stale saved report with a newer national run.
        growth = [r['metrics'][key]['growth_pct'] for r in data['rows']]
        mean = sum(growth)/len(growth)
        target = scenario['target_'+short] if scenario.get('has_target') else None
        target_growth = (sum(target)/sum(row['previous'])-1)*100 if target else None
        others = [r['metrics'][key]['growth_pct'] for r in data['rows'] if r['region_code']!=code]
        result['metrics'][short] = {**row,'national_mean_pct':mean,'gap_pp':row['growth_pct']-mean,
            'rank':rank(growth,row['growth_pct']),'target_growth_pct':target_growth,
            'target_rank':rank(others,target_growth) if target else None,
            'target':target,'additional':sum(target)-sum(row['forecast']) if target else None}
    return result
