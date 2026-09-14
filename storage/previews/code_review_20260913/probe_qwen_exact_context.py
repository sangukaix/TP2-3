"""Diagnostic only: native strict-context execution of the captured original input.

Ollama 0.34 supports truncate=false and shift=false. This isolated probe lets
the server's tokenizer decide fit instead of weakening the production estimate.
No source omission, paid provider, report store, or retries are used.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

import httpx
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ai_server.app.runtime_env import load_project_env


def main():
    source = Path(__file__).with_name('qwen_candidate_exact_input_20260914.json')
    original = source.read_bytes()
    captured = json.loads(original.decode('utf8'))
    env = load_project_env(ROOT)
    base = env['LOCAL_LLM_BASE_URL'].rstrip('/')
    folder = ROOT / 'storage/previews/case_research_diagnostics' / (
        datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_28237_native_strict_context')
    folder.mkdir(parents=True)
    result = {'status': 'prepared', 'report_approved': False, 'paid_calls': 0,
              'source_file': str(source.relative_to(ROOT)),
              'source_sha256': hashlib.sha256(original).hexdigest(),
              'production_estimator_changed': False}

    def save():
        (folder / 'diagnostic.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')

    body = {'model': env['OLLAMA_QWEN_MODEL'], 'messages': captured['messages'],
            'format': captured['schema'], 'think': False, 'stream': False,
            'truncate': False, 'shift': False, 'keep_alive': '15m',
            'options': {'num_ctx': 40960, 'num_predict': captured['max_output_tokens'],
                        'temperature': 0.15}}
    result['request_options'] = {key: body[key] for key in ('model', 'options', 'truncate', 'shift', 'think')}
    save()
    start = time.monotonic()
    try:
        with httpx.Client(timeout=1800) as client:
            version = client.get(base + '/api/version')
            version.raise_for_status()
            result['ollama_version'] = version.json()['version']
            if not result['ollama_version'].startswith('0.34.'):
                raise RuntimeError('Strict context semantics only verified against Ollama 0.34 source')
            print('Qwen exact original input; native truncate=false, shift=false; no paid calls', flush=True)
            response = client.post(base + '/api/chat', json=body)
            result['http_status'] = response.status_code
            result['response'] = response.json()
            response.raise_for_status()
            payload = result['response']
            result['loaded_models'] = client.get(base + '/api/ps').json()
            if not payload.get('done') or payload.get('done_reason') == 'length':
                raise RuntimeError('Incomplete response; not accepted')
            decision = json.loads(payload['message']['content'])
            Draft202012Validator(captured['schema']).validate(decision)
            result['raw_decision'] = decision
            result['schema_valid'] = True
            result['status'] = 'completed_unapproved_diagnostic'
    except Exception as exc:
        result['status'] = 'failed'
        result['error_type'] = type(exc).__name__
    finally:
        result['duration_seconds'] = round(time.monotonic() - start, 3)
        result['source_unchanged'] = source.read_bytes() == original
        save()
        print(json.dumps({'status': result['status'], 'output': str(folder),
                          'seconds': result['duration_seconds']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
