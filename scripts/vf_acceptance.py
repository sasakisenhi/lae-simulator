"""Read-only VF traceability checks; never grants human approval or edits evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGE = ROOT / 'openspec/changes/build-reproducible-simulation-foundation'
OUT = ROOT / 'docs/vf-evidence-20261109'


def completion_gate(required: list[str], tasks: list[str], acceptance: list[str], *,
                    human_approved: bool) -> str:
    """Unknown, empty, failed, or unapproved obligations cannot yield PASS."""
    return 'PASS' if (human_approved and required and tasks and len(acceptance) == 3
                      and all(value == 'PASS' for value in required + tasks + acceptance)) else 'NOT READY'


def verify() -> dict[str, object]:
    data = json.loads((OUT / 'traceability.json').read_text())
    specs = '\n'.join(p.read_text() for p in sorted((CHANGE / 'specs').glob('*/spec.md')))
    expected = re.findall(r'^### Requirement: ((?:WD|SE|EP)\d+)', specs, re.MULTILINE)
    rows = data['requirements']
    actual = [row['id'] for row in rows]
    # Keep the task ID as the key (many tasks share the same checkbox state).
    task_source = {task: state for state, task in re.findall(
        r'^- \[([ x])\] (\d+\.\d+) ', (CHANGE / 'tasks.md').read_text(), re.MULTILINE)}
    canonical_links = {rid: (design.strip(), task_ids.strip().split(', '))
                       for rid, design, task_ids in re.findall(
                           r'^\| ((?:WD|SE|EP)\d+) \| ([^|]+) \| ([^|]+) \|$',
                           (CHANGE / 'design.md').read_text(), re.MULTILINE)}
    expected_scenarios = re.findall(r'^#### Scenario: (.+)$', specs, re.MULTILINE)
    tasks = data['tasks']
    approval_path = OUT / 'human-approval.json'
    approval = json.loads(approval_path.read_text()) if approval_path.is_file() else {}
    reviewed = ROOT / approval.get('reviewed_manifest', 'missing-reviewed-manifest')
    human_approved = (approval.get('approved') is True and bool(approval.get('user_statement'))
                      and reviewed.is_file() and hashlib.sha256(reviewed.read_bytes()).hexdigest()
                      == approval.get('reviewed_manifest_sha256'))
    checks = {
        'all_requirements_once': len(actual) == len(set(actual)) and set(actual) == set(expected),
        'all_tasks_once': len(tasks) == len(task_source) and {r['id'] for r in tasks} == set(task_source),
        'design_and_task_links': all(r['design'] and r['tasks'] and set(r['tasks']) <= set(task_source) for r in rows),
        'canonical_links_match': all(canonical_links.get(r['id']) == (r['design'], r['tasks']) for r in rows),
        'all_scenarios': sorted(r['name'] for r in data['scenarios']) == sorted(expected_scenarios)
                         and all(r['requirement'] in actual for r in data['scenarios']),
        'independent_verdicts': [r['id'] for r in data['acceptance']] == ['A', 'B', 'C'],
        'excluded_unknown_separate': all(r['status'] == 'UNKNOWN' and r['mandatory'] is False for r in data['excluded']),
        'evidence_paths_exist': all(r['evidence'] and all((ROOT / p).is_file() for p in r['evidence']) for r in rows + tasks),
        'test_paths_exist': all(r['tests'] and all((ROOT / p).is_file() for p in r['tests']) for r in rows + tasks),
        'task_states_match': all((task_source[r['id']] == 'x') == (r['status'] == 'PASS') for r in tasks),
    }
    return {'checks': checks, 'traceability': 'PASS' if all(checks.values()) else 'FAIL',
            'requirement_count': len(rows), 'task_count': len(tasks),
            'mvp': completion_gate([r['status'] for r in rows], [r['status'] for r in tasks],
                                   [r['status'] for r in data['acceptance']],
                                   human_approved=human_approved and all(checks.values())),
            'human_approved': human_approved,
            'limitation': 'Structural checks do not establish semantic requirement satisfaction. Human approval is recorded separately.'}


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['traceability'] == 'PASS' else 1)
