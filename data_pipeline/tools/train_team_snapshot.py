"""Stage missing regional models; never train in a web request or overwrite existing artifacts."""
import argparse
import csv
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


def train_one(task):
    code,name,workspace=task
    import pandas as pd
    from ai_server.ml.gangnam_forecast import RegionForecastSettings, train_region_models, predict_region_future_months
    output=Path(workspace)
    monthly=pd.read_csv(output/f'monthly_{code}.csv',dtype={'region_code':str,'year_month':str},float_precision='round_trip')
    from ai_server.ml.validation import data_fingerprint
    preparation=json.loads((output/'preparation.json').read_text(encoding='utf-8'))
    expected=next(row['fingerprint'] for row in preparation['regions'] if row['region_code']==code and row['status']=='train_required')
    if data_fingerprint(monthly)!=expected:
        raise ValueError('Staged CSV differs from validated source observations')
    def read(): return monthly.copy()
    settings=RegionForecastSettings(code,name,read,read,output/'models'/code,'regional-demand-v3.1')
    metadata=train_region_models(settings)
    predicted=predict_region_future_months(settings,6)
    return {'region_code':code,'status':'trained','targets':list(metadata['target']),'source_period':metadata['source_period'],'data_fingerprint':metadata['data_fingerprint'],'forecast_valid':bool(predicted)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    info=json.loads((args.workspace/'preparation.json').read_text(encoding='utf-8'))
    with (args.workspace/'catalog_proposed.csv').open(encoding='utf-8-sig',newline='') as stream:catalog={row['region_code']:row for row in csv.DictReader(stream)}
    codes=sorted({row['region_code'] for row in info['regions'] if row['status']=='train_required'})
    tasks=[(code,catalog[code]['region_name'],str(args.workspace.resolve())) for code in codes]
    results=[]
    with ProcessPoolExecutor(max_workers=max(1,min(4,args.workers))) as pool:
        futures={pool.submit(train_one,task):task[0] for task in tasks}
        for future in as_completed(futures):
            code=futures[future]
            try: result=future.result()
            except Exception as exc:result={'region_code':code,'status':'failed','error':str(exc)}
            results.append(result)
            (args.workspace/'training.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(len(results),len(tasks),code,result['status'],flush=True)
    if any(row['status']=='failed' for row in results):raise SystemExit(2)

if __name__=='__main__':main()
