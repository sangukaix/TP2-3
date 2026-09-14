import sys, unittest, json, contextlib, socket
from pathlib import Path
out = Path('storage/previews/code_review_20260913')
blocked=[]
def guard(event,args):
    if event not in ('socket.connect','socket.getaddrinfo'): return
    frame=sys._getframe()
    while frame:
        if frame.f_code is socket.socketpair.__code__: return
        frame=frame.f_back
    blocked.append(event)
    raise OSError('OFFLINE_REVIEW: network disabled')
sys.addaudithook(guard)
with (out/'python_tests.log').open('w',encoding='utf-8') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    suite=unittest.TestSuite()
    loader=unittest.TestLoader()
    for path in sorted(Path('ai_server').glob('test_*.py')):
        suite.addTests(loader.loadTestsFromName('ai_server.'+path.stem))
    suite.addTests(loader.discover('tests/nationwide_pipeline'))
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
summary={'tests':result.testsRun,'failures':[str(t) for t,_ in result.failures],'errors':[str(t) for t,_ in result.errors],'skipped':[str(t) for t,_ in result.skipped],'blocked_network_attempts':len(blocked)}
(out/'python_test_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
