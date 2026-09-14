"""Audit an immutable local team snapshot and stage a catalog without activating untrained regions."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from dataclasses import asdict
from collections import Counter
from .data_inventory import build_inventory
from .build_region_code_reference import resolve_region_mapping, read_csv, write_csv
from ai_server.ml.region_catalog import list_region_data_catalog, RegionDataCatalogEntry, PROJECT_ROOT
from ai_server.ml.regional_datalab_data import StandardDatalabRegion, load_standard_datalab_monthly_demand
from ai_server.ml.gangnam_forecast import data_fingerprint


def prepare(snapshot: Path, output: Path):
    snapshot=snapshot.resolve()
    allowed=(PROJECT_ROOT/'data/source_snapshots').resolve()
    if allowed not in snapshot.parents:
        raise ValueError('SNAPSHOT_MUST_BE_LOCAL')
    output.mkdir(parents=True,exist_ok=True)
    inventory=output/'inventory'
    print('Inventory started',flush=True)
    summary=build_inventory(snapshot,inventory)
    print('Inventory',summary['region_count'],summary['archive_count'],flush=True)
    official_path=PROJECT_ROOT/'data/processed/nationwide/materialized_region_reference/official_municipality_codes.csv'
    official=read_csv(official_path)
    official_codes={row['region_code']:row for row in official}
    candidates=read_csv(inventory/'region_code_candidates.csv')
    mapped=resolve_region_mapping(candidates,official)
    # Internal codes alone are not sufficient: a known code AND official full name must agree.
    for row in mapped:
        code=row.get('official_region_code')
        ref=official_codes.get(code)
        hierarchy=str(row.get('local_hierarchy_name') or '').replace('_',' ')
        province={'강원도':'강원특별자치도','전라북도':'전북특별자치도'}.get(row.get('province_name'),row.get('province_name'))
        if not ref or ref['province_name']!=province or ref['municipality_name']!=hierarchy:
            row['mapping_status']='needs_review'
            row['mapping_method']='official_code_name_not_confirmed'
    write_csv(output/'region_mapping_validated.csv',list(mapped[0]) if mapped else [],mapped)
    current=list(list_region_data_catalog(enabled_only=False))
    by_code={entry.region_code:entry for entry in current}
    staged=dict(by_code)
    decisions=[]
    for row in mapped:
        code=str(row.get('official_region_code') or '')
        result={'region_folder':row['region_folder'],'region_code':code}
        if row['mapping_status'] not in {'validated_from_datalab','validated_from_mois'}:
            decisions.append({**result,'status':'held_code_mapping'})
            continue
        ref=official_codes[code]
        path=snapshot/row['region_folder']
        entry=RegionDataCatalogEntry(code,ref['official_full_name'],row['municipality_name'],path.relative_to(PROJECT_ROOT).as_posix(),'standard_datalab_archive','한국관광 데이터랩','https://datalab.visitkorea.or.kr/','2026-09-11','needs_exact_download_url',True)
        try:
            monthly=load_standard_datalab_monthly_demand(StandardDatalabRegion(code,entry.region_name,entry.short_name,path))
            if len(monthly)<30: raise ValueError('LESS_THAN_30_MONTHS')
            fingerprint=data_fingerprint(monthly)
            prior=by_code.get(code)
            metadata_path=PROJECT_ROOT/'artifacts/ml'/code/'demand_model.metadata.json'
            metadata=json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
            if prior and prior.adapter_type not in {'standard_datalab_csv','standard_datalab_archive'}:
                status='preserved_special_adapter'
            elif prior and metadata.get('data_fingerprint') and metadata['data_fingerprint']!=fingerprint:
                # Do not silently substitute revised or shorter historical observations.
                status='held_changed_observations'
            else:
                staged[code]=entry
                status='reuse_model' if prior and metadata.get('data_fingerprint')==fingerprint else 'train_required'
                monthly.to_csv(output/f'monthly_{code}.csv',index=False,encoding='utf-8-sig')
            decisions.append({**result,'status':status,'fingerprint':fingerprint,'months':len(monthly),'start':str(monthly.year_month.iloc[0]),'end':str(monthly.year_month.iloc[-1]),'prior_path':prior.raw_relative_path if prior else None})
        except (ValueError,FileNotFoundError,KeyError) as exc:
            decisions.append({**result,'status':'held_data_validation','reason':str(exc)})
        print(code,decisions[-1]['status'],flush=True)
    fields=list(asdict(current[0]))
    def save(path,entries):
        with path.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for entry in entries:
                values=asdict(entry);values['enabled']=str(values['enabled']).lower();writer.writerow(values)
    save(output/'catalog_before.csv',current)
    save(output/'catalog_proposed.csv',staged.values())
    result={'inventory':summary,'status_counts':dict(Counter(row['status'] for row in decisions)),'current_catalog_count':len(current),'proposed_catalog_count':len(staged),'regions':decisions}
    (output/'preparation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['status_counts']),flush=True)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.snapshot,args.output)
