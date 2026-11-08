"""Run with Python 3.14 and args: isolated G6 source root, output directory.

This script imports only the supplied old source. It does not use the new
compatibility projector to generate the expected artifacts.
"""
import sys
from pathlib import Path

old_root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(old_root / 'src'))

from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_scenario_execution,
    save_local_run,
)

execution = load_scenario_execution(old_root / 'fixtures/g2/scenario-collaboration.json')
for case in ('cancelled', 'repeated', 'submitted'):
    session = LocalSession.start(execution)
    if case == 'cancelled':
        session.cancel('G6-PRIVATE-CANCELLATION')
    elif case == 'repeated':
        for _ in range(2):
            session.select('T03')
            session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='metadata', input_version='B0')
            session.select('T11')
            session.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C01', input_version='B0')
    else:
        session.select('T10')
        session.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1', input_version='B0')
        session.select('T11')
        check = session.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C01', input_version=session.state.workspace_version)
        session.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='Bounded result',
                       check_event_ids=(check.id,), coverage='modeled', limitations='G6-PRIVATE-LIMITATION')
    save_local_run(execution, session.finish(), output / case)
