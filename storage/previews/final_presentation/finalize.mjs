import {finalizePresentation} from 'file:///C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations/container_tools/artifact_tool_utils.mjs';
const root='C:/Users/Admin/mbca/TP2-3';
const skill='C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const result=await finalizePresentation({
 workspaceDir:root,candidatePath:root+'/storage/previews/final_presentation/candidate.pptx',
 finalPath:root+'/output/presentation/OLIGO-K_프로젝트발표_최종본.pptx',
 pythonExecutable:root+'/backend/.venv/Scripts/python.exe',
 integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',
 layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[6,9,14,16,19,21,22,26,29].flatMap(n=>['--require-native-table-slide',String(n)])],
 explicitTotalSlideCount:30,requiredNativeTableOwnerSlides:[6,9,14,16,19,21,22,26,29],requiredNativeChartOwnerSlides:[11],
 materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Malgun Gothic']},
 verifyArtifactToolImport:true,receiptPath:root+'/storage/previews/final_presentation/validation_final.json'
});
console.log(JSON.stringify(result));

