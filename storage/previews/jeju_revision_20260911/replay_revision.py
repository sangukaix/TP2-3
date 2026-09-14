"""Local-only Jeju revision diagnostic, saved facts; never saves a report."""
import sys,json,asyncio
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from ai_server.app.main import build_region_snapshot,REPORT_SCHEMA
from ai_server.app.agents.planner_agent import PlannerAgent
from ai_server.app.agents.decision_facts import build_decision_facts
from ai_server.app.llm.router import LLMRouter
from ai_server.app.runtime_env import load_project_env
from ai_server.app.llm.errors import LLMProviderError
from ai_server.app.llm.evidence_tools import EvidenceTools
from ai_server.app.llm.local_agent import _prefetch_required_evidence

async def run():
    out=Path(__file__).parent;r=json.loads((out/'original.json').read_text(encoding='utf-8'))
    snapshot=build_region_snapshot(r['region_name']);snapshot['ml_analysis']=r['ml_analysis'];snapshot['decision_facts']=build_decision_facts(snapshot)
    pack={'region_code':'50110','region_name':r['region_name'],'period':r['period'],'snapshot':snapshot,
          'planning_brief':r['planning_brief'],'transfer_assessment':r['planning_decision'],
          'sources':r['evidence_sources'],'benchmark_cases':[s for s in r['evidence_sources'] if s.get('source_type')=='benchmark_case'],
          'quality_contract_version':'execution-evidence-v1','research_gaps':r['research_gaps']}
    draft={key:r[key] for key in REPORT_SCHEMA['properties'] if key in r}
    router=LLMRouter(project_root=ROOT,env_values=load_project_env(ROOT));router.config['mode']='student_budget'
    async def deny(*a,**kw):raise LLMProviderError('PAID_BLOCKED','Diagnostic')
    router.providers['openai'].generate=deny
    result=await PlannerAgent(api_key='',model='',report_schema=REPORT_SCHEMA,llm_router=router).write(pack,revision_feedback=r['quality_review'],previous_draft=draft)
    (out/'revision_result.json').write_text(json.dumps({'report':result,'trace':router.consume_trace(),'saved_report_modified':False},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Local revision completed',flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(run())
