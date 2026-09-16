"""Use dated launch steps for operating capacity, without changing forecast facts."""
import re


def is_launch_step(step):
    task = str(step.get('task') or '')
    return bool(re.search(r'시범\s*운영|본격\s*운영|축제\s*실행|사업\s*개시|운영\s*개시', task)
                and not re.search(r'(?:계획|준비|구성|매뉴얼).{0,6}(?:수립|작성|검토)', task))


def operating_schedule(rows, strategy):
    months = [r['month'] for r in rows]
    starts = []
    for step in strategy.get('implementation_steps') or []:
        # A dated actual launch differs from writing an operating plan or
        # training staff. Undated/freeform schedules retain the declared window.
        if not is_launch_step(step):
            continue
        found = re.findall(r'(20\d{2})[-./년]\s*(0?[1-9]|1[0-2])(?:월|\b)', str(step.get('schedule') or ''))
        starts.extend(f'{y}{int(m):02d}' for y, m in found if f'{y}{int(m):02d}' in months)
    start = min(starts) if starts else (months[0] if months else '')
    active = [m for m in months if m >= start]
    weights = [(active.index(m) + 1) / len(active) if m in active else 0 for m in months]
    return {'active_months': active, 'monthly_weights': weights,
            'schedule_basis': 'dated_launch_step' if starts else 'declared_business_window'}
