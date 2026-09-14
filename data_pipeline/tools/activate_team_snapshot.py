"""Validate staged forecasts against local originals, then atomically publish the regional catalog."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from ai_server.ml.region_catalog import CATALOG_PATH, PROJECT_ROOT, RegionDataCatalogEntry
from ai_server.ml.regional_datalab_data import StandardDatalabRegion, load_standard_datalab_monthly_demand
from ai_server.ml.gangnam_forecast import RegionForecastSettings, predict_region_future_months
from ai_server.ml.validation import TARGETS, data_fingerprint


def read_catalog(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return {row['region_code']: row for row in csv.DictReader(stream)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def activate(workspace: Path, *, apply: bool = False):
    workspace = workspace.resolve()
    if (PROJECT_ROOT / 'data/interim').resolve() not in workspace.parents:
        raise ValueError('Staging must be inside project data/interim')
    before = read_catalog(workspace / 'catalog_before.csv')
    proposed = read_catalog(workspace / 'catalog_proposed.csv')
    current = read_catalog(CATALOG_PATH)
    if current not in (before, proposed):
        raise ValueError('Catalog changed since preparation; preserve changes and prepare again')
    preparation = json.loads((workspace / 'preparation.json').read_text(encoding='utf-8'))
    training = {row['region_code']: row for row in json.loads((workspace / 'training.json').read_text(encoding='utf-8'))}
    checked = []
    copies = []
    for decision in preparation['regions']:
        if decision['status'] not in {'train_required', 'reuse_model'}:
            continue
        code = decision['region_code']
        row = dict(proposed[code])
        row['enabled'] = row['enabled'] == 'true'
        entry = RegionDataCatalogEntry(**row)
        spec = StandardDatalabRegion(code, entry.region_name, entry.short_name, entry.raw_path)
        monthly = load_standard_datalab_monthly_demand(spec)
        if data_fingerprint(monthly) != decision['fingerprint']:
            raise ValueError(f'Source changed after preparation: {code}')
        if decision['status'] == 'train_required':
            if training.get(code, {}).get('status') != 'trained':
                raise ValueError(f'Training incomplete: {code}')
            model_dir = workspace / 'models' / code
            for filename in ('demand_model.joblib', 'demand_model.metadata.json'):
                copies.append((model_dir / filename, PROJECT_ROOT / 'artifacts/ml' / code / filename))
            copies.append((workspace / f'monthly_{code}.csv', PROJECT_ROOT / 'data/processed/ml' / code / 'monthly_demand.csv'))
        else:
            model_dir = PROJECT_ROOT / 'artifacts/ml' / code
        settings = RegionForecastSettings(code, entry.region_name, lambda: monthly.copy(), lambda: monthly.copy(), model_dir, 'regional-demand-v3.1')
        prediction = predict_region_future_months(settings, 6)
        forecasts = prediction['forecasts']
        if len(forecasts) != 6 or any(not set(TARGETS).issubset(item) for item in forecasts):
            raise ValueError(f'Forecast contract incomplete: {code}')
        checked.append(code)
    # Validate the whole set before publishing any file. Never replace a different model.
    for source, destination in copies:
        if destination.exists() and sha(source) != sha(destination):
            raise ValueError(f'Existing artifact differs: {destination.relative_to(PROJECT_ROOT)}')
    if apply:
        for source, destination in copies:
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + '.team-import')
            shutil.copyfile(source, temporary)
            if sha(source) != sha(temporary):
                raise ValueError('Artifact copy hash mismatch')
            temporary.replace(destination)
        temporary = CATALOG_PATH.with_suffix('.team-import')
        shutil.copyfile(workspace / 'catalog_proposed.csv', temporary)
        temporary.replace(CATALOG_PATH)
    result = {'status': 'activated' if apply else 'validated', 'forecast_checked': len(set(checked)), 'catalog_count': len(proposed), 'enabled_count': sum(row['enabled'] == 'true' for row in proposed.values()), 'catalog_sha256': sha(workspace / 'catalog_proposed.csv')}
    (workspace / ('activation.json' if apply else 'activation_validation.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(activate(args.workspace, apply=args.apply)))
