# G4 Scheduler contract and acceptance evidence

Scope: Task 3.1 only. The scheduler is a pure component of the existing modular
monolith; it does not implement AI collaboration, task resumption, or integration.

## Authority and execution

`simulation/scheduler.py` owns reservation ordering and lifecycle operations.
CF0's reducer adapts its existing persisted queue fields to this kernel. Timed G3
uses `SchedulerState` directly. Neither Engine maintains a second mutable queue.
The existing `canonical.start_execution`, `transition`, `replay_history`, and
verified publication boundary remain the entry points for both families.
`local_timing.py` owns scenario-specific reservation, time-model, and control
validation; `local_reducer.py` owns the business operation and its effects.
Engines construct commands/events and dispatch the next canonical reservation.

The effective queue key is `(tick, priority, insertion_sequence, reservation_id)`.
Tick, priority and sequence are integers. Sequences strictly increase and are not
reused, so an ID tie-break never overrides an actual semantic ordering. IDs are
unique references, not a way to obtain priority. Classification follows D5:
completion10, external20, notification30, decision40, deadline90. No event may
advance the clock except consuming the next pending reservation. A reservation
cannot be inserted behind the current consumed cursor.

## Cancellation, invalidation, and deadline

Cancellation/invalidation is an immediate effect of its consumed cause, recorded
as a separate canonical event before another slot can be consumed. It has no
independent queue priority. Timed conformance controls have explicit source
priority20 (external) or40 (decision), a candidate target, a reason and generation1.
The reducer verifies the fixed control, its actual consumed cause, its target and
generation; the kernel verifies pending status and queue order. Generation1 is
sufficient for uniquely identified reservations here. Resumption and later task
generations are G5 work, not silently implemented by this profile.

At the same tick, completion10 precedes an external control20. A late control is
recorded as no-pending-target and does not undo completed effects. An earlier
same-priority slot can invalidate a later slot, using its earlier insertion key.
Retired IDs cannot be reused or consumed. Pending lifecycle is replay-derived.
The legacy CF0 cancellation API remains limited to cancellation before due; its
old input has no external control plans. Both adapters use the same kernel.

The fixed study deadline uses priority90. Permitted completion at H is applied
before the deadline. Once the deadline is consumed, only RunEnded is permitted.
Operations due after H remain pending and do not apply effects. Individual AI or
peer timeout business rules are outside G4; this profile does not invent them.
Explicit early incomplete termination from the existing G3 API is retained, but
cannot conceal an unresolved consumed operation/control or current-tick work.

## Fixed timing input

`fixtures/g2/scenario-timed.json` is a separate input derived from the original G2
catalog. `timing-review.txt` records its synthetic assumptions and digest. It
resolves all original TM IDs, adds the existing revert capability as T10-REVERT
with TM-REVERT, and declares [0,30], seed0, and a same-tick consumption limit100.
TM-NAV is0 ticks; other default models are1 tick. These are not measured LAE work.
Missing IDs, incompatible operation scopes, malformed numeric fields, absent
source/uncertainty, and unsupported provenance are rejected. The initial profile
accepts synthetic assumptions only; measured/documented input requires an
explicit evidence contract rather than relabelling an unsupported value.

A duration is checked at reservation creation and the business preconditions are
checked again at completion. Effects apply only after the matching reservation
has been consumed. A zero-duration completion is permitted. If its priority10
would reenter a phase already passed at the current tick, D5's next-tick rule is
used; that scheduling delay does not change the declared active-work duration.

The fixed same-tick event limit bounds zero-time cycles. It is a safety limit,
not a claim to prove every semantic cycle. The error identifies the consumption
and `same-tick-event-limit`; the session cannot turn that failure into a valid
incomplete result. Replay applies the same bound. Finite zero-time work within
the bound remains valid. CF0's legacy positive duration models and finite,
nonrepeatable candidate selection retain their existing behavior.

## Random duration audit

Default constant models use no draws. Optional `jitter_ticks` defines
`duration = ticks + raw % (jitter_ticks + 1)` without claiming exact statistical
uniformity or empirical calibration. `raw` is the existing SHA-256 v1 unsigned
64-bit result keyed by `(seed, operation-duration, actor_id, candidate_id,
model_id, occurrence)`. The occurrence is derived from that candidate's accepted
reservations, including cancelled attempts. Unrelated candidates or draw calls
do not consume a shared stream. The reservation records raw, due tick, candidate
and cause; fixed input and replay state determine every other key component.
Replay verifies the digest mapping and consumes no stochastic random stream.
The manifest records engine/algorithm version, seed, window, bound and draw usage.

## Storage and information boundaries

Legacy CF0 JSON/JSONL codecs remain supported, including reconstruction and
comparison of newly derived causal metadata. Legacy untimed G3 retains its
original run identity, initial state and event serialization. Scheduler-only
fields are emitted only when present. Timed runs use the separate g4-local-1.0
identity/state profile and canonical-scheduler-1.0 engine metadata. Fixed timing
is part of the canonical scenario content, so changed assumptions identify a
separate run. Initial states, events, queue, derived final state and public
projection are replay-checked at save/load. There is no Replay-only relaxation.

Reservations, control payloads/reasons, raw draws and the future queue are absent
from Policy input and the public allowlist. Elapsed logical time and experienced
operation results remain visible. Observation snapshots are preserved at their
actual completion tick and workspace version. Unapplied future work does not
create participant knowledge. Patch apply and revert both use timed consumption;
revert cites the applied patch event and releases its completion token.

## Test correspondence

| Invariant | Evidence |
|---|---|
| Tick/priority/sequence order, direct clock bypass | test_scheduler.py; walking-skeleton forged scheduling and unscheduled-time tests |
| Same-tick completion/control/deadline, retirement | test_scheduler.py collision traces; test_timed_local.py control-before/same-tick cases |
| IDs, repeated consumption and reuse | scheduler lifecycle tests; walking-skeleton cancellation/reuse tests |
| Timing definitions, zero durations, missing references | test_timing.py; test_timed_local.py zero-time limit and fixed scope validation |
| Causal links, generation and raw-draw tampering | walking-skeleton causal tests; timed control-generation and duration-draw replay rejection |
| Search/Patch/Check/revert, snapshots, versions | timed local end-to-end and timed revert tests; original G3 regression suite |
| H boundary and pending future work | timed deadline retention test; core completion-before-deadline test |
| Hash-seed and draw independence | test_scheduler_randomness.py; timed independent process comparison |
| Save/load/publication and legacy codecs | original CF0/G3 store tests; timed controls/end-to-end/deadline store tests; old CF0 artifact retrieval |

Independent review identified and verified fixes for direct kernel clock rewind,
deadline-consumption interleaving, and the missing timed revert/cleanup path.
Final test and review results are reported with Task 3.1 completion; static
checks alone are not acceptance evidence.

## Final G4 verification

Task 3.1 requirements WD04/WD10/SE14/SE15/SE21 and D4/D5/D10 were checked against
the implementation and the cases above. Final unittest run:134 passed. The focused
new modules contain6 scheduler tests,2 keyed-randomness tests,2 timing-input tests,
and10 timed-local tests, in addition to CF0/G1/G2/G3 regressions and CF0 anomaly
cases. Ruff, mypy strict (47 source/test files), compileall, uv lock --check,
OpenSpec strict validation, and git diff --check passed. The uv cache was redirected
to /tmp to keep checks offline under the restricted filesystem profile.

The saved CF0 artifact produced by the pre-change HEAD implementation was retrieved
as valid (8 canonical events,3 public records). Old G3/legacy snapshot tests and
new timed save/retrieve tests passed. Hash-seed subprocess tests compared canonical
events, final state, public projections and purpose-keyed draws.

Independent review re-ran the134-test suite during final review. Its final follow-up
re-ran the10 timed-local cases after the last fix. Reported defects were repaired:
direct kernel clock rewind; deadline interleaving; timed revert/cleanup; CF0 false
deadline consumption; and simultaneous canonical JSON/runtime timing substitution
under an unchanged content identifier. The last substitution now fails SHA-256
binding validation. No further concrete major finding remained in the reviewed
paths. Review is not a proof over every possible input.

Remaining limits are explicit: timing values are uncalibrated synthetic assumptions;
the finite same-tick bound can reject workloads exceeding its declared budget;
this initial control profile uses generation1; G5 task resumption, peer/AI reply
business rules and individual collaboration timeout rules are not implemented.
Legacy CF0 has no new external control input family. Its existing input/API stays
supported through the same kernel and existing codec adapter. No claim of measured
performance, OSS execution, or complete MVP acceptance follows from G4 acceptance.
