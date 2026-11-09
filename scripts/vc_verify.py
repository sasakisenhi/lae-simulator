"""Post-seal structural/provenance checks; never substitutes for meaning review."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from lae_simulator.simulation.fixed_evidence import (
    _evidence_correspondence,
    get_evidence,
    related_evidence,
    search_evidence,
)
from scripts import vc_acceptance as vc


def verify() -> dict[str, Any]:
    out = vc.OUT
    checks = {}
    manifest = json.loads((out / 'manifest.json').read_bytes())
    checks['frozen_inputs'] = all(vc.digest(vc.ROOT / name) == value for name, value in manifest['files'].items())
    for seal_name in ('stage-1-seal.json', 'retrieval-seal.json', 'stage-2-seal.json'):
        seal = json.loads((out / seal_name).read_bytes())
        checks[seal_name] = all(vc.digest(out / name) == value for name, value in seal['files'].items())
    first_seal = json.loads((out / 'stage-1-seal.json').read_bytes())
    retrieval_seal = json.loads((out / 'retrieval-seal.json').read_bytes())
    last_seal = json.loads((out / 'stage-2-seal.json').read_bytes())
    checks['seal_order'] = first_seal['sealed_at'] < retrieval_seal['sealed_at'] < last_seal['sealed_at'] < datetime.now(UTC).isoformat()
    sessions = []
    for stage in (1, 2):
        events = [json.loads(line) for line in (out / f'stage-{stage}-events.jsonl').read_text().splitlines() if line.strip()]
        checks[f'zero_tools_stage_{stage}'] = all(e['item']['type'] in {'agent_message', 'reasoning'} for e in events if e.get('type', '').startswith('item.'))
        sessions.append(next(e['thread_id'] for e in events if e['type'] == 'thread.started'))
    checks['separate_contexts'] = len(set(sessions)) == 2
    execution, run = vc.context()  # Store load already validates replay closure.
    audit = json.loads((out / 'retrieval-audit.json').read_bytes())
    first = json.loads((out / 'stage-1.json').read_bytes())
    checks['investigator_chosen_requests'] = [row['request'] for row in audit] == first['requests'] and len(audit) >= 1
    for index, row in enumerate(audit):
        request = row['request']
        if request['method'] == 'search':
            reply = search_evidence(execution, run, role='researcher', **request['args'])
        else:
            fetch = get_evidence if request['method'] == 'get' else related_evidence
            reply = fetch(execution, run, role='researcher', evidence_id=request['args']['id'])
        checks[f'public_api_response_{index}'] = json.loads(reply) == row['response']
    catalog = json.loads(search_evidence(execution, run, role='researcher'))
    ids = {row['id'] for row in catalog}
    mapping = json.loads(_evidence_correspondence(execution, run))
    checks['public_event_mapping'] = all(row['event_id'] in mapping['public_to_canonical'] for row in catalog if row['event_id'])
    checks['mapping_targets_exist'] = set(mapping['public_to_canonical'].values()) <= {event.id for event in run.events}
    last = json.loads((out / 'stage-2.json').read_bytes())
    citations = [value for row in last['claim_evidence'] for value in row['evidence_ids']]
    checks['claim_citations_exist'] = bool(citations) and set(citations) <= ids
    checks['hypothesis_reassessment'] = bool(last['hypothesis_updates']) and bool(last['additional_evidence_used'])
    checks['initial_packet_same_as_first_trial'] = vc.digest(out / 'initial-public.json') == vc.digest(vc.ROOT / 'docs/vc-evidence-20261109/initial-public.json')
    checks['initial_prompt_same_as_first_trial'] = vc.digest(out / 'stage-1-input.txt') == vc.digest(vc.ROOT / 'docs/vc-evidence-20261109/stage-1-input.txt')
    protocol = json.loads((out / 'protocol.json').read_bytes())
    old_protocol = json.loads((vc.ROOT / 'docs/vc-evidence-20261109/protocol.json').read_bytes())
    checks['criteria_unchanged'] = protocol['criteria'] == old_protocol['criteria']
    return {'verified_at': datetime.now(UTC).isoformat(), 'checks': checks, 'structural_result': 'PASS' if all(checks.values()) else 'FAIL',
            'sessions': sessions, 'model': protocol['model'], 'canonical_event_count': len(run.events), 'public_records': len(catalog),
            'additional_requests': len(audit), 'claim_citations': len(citations),
            'limitation': 'Citation existence and canonical correspondence do not establish semantic support. Separate post-seal meaning review is required.'}


if __name__ == '__main__':
    result = verify()
    vc.write(vc.OUT / 'verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['structural_result'] == 'PASS' else 1)
