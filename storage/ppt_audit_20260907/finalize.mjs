import {finalizePresentation} from 'file:///C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.904.11930/skills/presentations/container_tools/artifact_tool_utils.mjs';
const root='C:/Users/Admin/mbca/TP2-3';
process.env.RUNTIME_NODE_MODULES='C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const skill='C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.904.11930/skills/presentations';
const result=await finalizePresentation({
 workspaceDir:root,
 candidatePath:`${root}/storage/previews/원주시_기획서_v9_목표비교_예시.pptx`,
 finalPath:`${root}/storage/previews/원주시_기획서_최종_v9.pptx`,
 pythonExecutable:'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
 integrityValidatorPath:`${skill}/container_tools/inspect_presentation_package_integrity.py`,
 layoutValidatorPath:`${skill}/container_tools/inspect_presentation_layout_geometry.py`,
 layoutArgs:['--expected-slide-size-emu','15240000,8572500','--require-native-table-slide','6','--require-native-table-slide','8','--require-native-table-slide','9'],
 explicitTotalSlideCount:12,
 requiredNativeChartOwnerSlides:[4],
 requiredNativeTableOwnerSlides:[6,8,9],
 verifyArtifactToolImport:true,
 receiptPath:`${root}/storage/ppt_audit_20260907/final_validation_v9.json`
});
console.log(JSON.stringify(result));
