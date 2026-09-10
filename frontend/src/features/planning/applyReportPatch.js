/** 수정 가능한 본문만 적용합니다. SQL·ML·근거는 보존하며 목표와 임시 견적만 별도로 조정합니다. */
export function applyReportPatch(report, patch) {
  if (!report?.strategies?.length || !patch || typeof patch !== 'object') return report
  const updated = { ...report.strategies[0] }
  for (const key of ['problem_to_solve', 'comparison_analysis', 'solution', 'expected_effect']) {
    if (typeof patch[key] === 'string' && patch[key].trim()) updated[key] = patch[key].trim()
  }
  if (typeof patch.strategy_title === 'string' && patch.strategy_title.trim()) updated.title = patch.strategy_title.trim()
  const steps = patch.implementation_steps
  if (Array.isArray(steps) && steps.length >= 3 && steps.length <= 5 && steps.every((step) =>
    Number.isInteger(step.step) && ['schedule', 'task', 'deliverable'].every((key) => typeof step[key] === 'string' && step[key].trim()))) {
    updated.implementation_steps = steps.map(({ schedule, task, deliverable }, index) => ({ step: index + 1, schedule, task, deliverable }))
  }
  const targets = patch.execution_scenario
  const numericUpdates = {}
  if (targets && Number.isFinite(targets.visitor_target_pct) && targets.visitor_target_pct >= 0 && targets.visitor_target_pct <= 20
      && Number.isFinite(targets.spending_target_pct) && targets.spending_target_pct >= 0 && targets.spending_target_pct <= 30) {
    numericUpdates.target_proposal_basis = undefined
    numericUpdates.execution_scenario = { visitor_target_pct: targets.visitor_target_pct, spending_target_pct: targets.spending_target_pct }
  }
  const estimate = patch.reference_estimate
  if (estimate?.status === 'planning_assumption_not_quote' && Array.isArray(estimate.items)
      && estimate.items.length > 0 && estimate.items.every((row) => Number.isSafeInteger(row.amount) && row.amount >= 0)
      && estimate.items.reduce((sum, row) => sum + row.amount, 0) === estimate.total_krw) {
    numericUpdates.reference_estimate = estimate
  }
  return { ...report, ...numericUpdates,
    summary: typeof patch.summary === 'string' && patch.summary.trim() ? patch.summary.trim() : report.summary,
    strategies: [updated, ...report.strategies.slice(1)],
    quality_review: { ...report.quality_review, approved: false, review_stale: true },
  }
}
