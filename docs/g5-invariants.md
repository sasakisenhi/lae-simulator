# G5 implementation invariants

- G5 extends LocalEvent/LocalState and the existing canonical entry, reducer,
  Scheduler and Store. No second clock, queue, replay engine or live generator
  is introduced. Domain reducers perform no external I/O.
- Reply arrival20 changes environmental request/dependency state only. Delivery30
  exposes notification presence. Explicit observation records participant claims
  and an immutable response snapshot. Undelivered/private contents do not enter
  Policy input.
- A request owns its generation. Response, notification, completion and overlay
  refer to that request/generation. Older arrivals may be recorded but cannot
  satisfy a newer generation. Consumption, completion and resumption are unique.
- Internal request expiry is deadline90. External rejection/unavailability is a
  reply20. At equal tick below H, reply20 precedes expiry90. At H, fixed study
  deadline90 was inserted first: later local90 slots remain pending with unresolved
  requests. End validation rejects pending keys before the consumed horizon key,
  rather than rejecting every later slot merely because its tick equals H.
- One human active resource is permitted; AI uses its declared independent
  capacity. Interrupts close an active interval, retire its completion and retain
  goal/base/remaining work. Resumption creates a new generation and never restores
  an old completion ID. Explicit rereading is active work, with no extra blanket
  resumption charge. Time totals use interval unions, not parallel duration sums.
- Approvals are scoped, explicit and tied to a request. Fixed background
  permissions are immutable; current grants are separate. Unknown contacts,
  unavailable peers, denial, no response and expiry are distinct outcomes.
- Response artifacts bind request, generation, base version, provenance revision,
  permitted evidence and content digest. Only fixed/prepared response records are
  used during simulation. No SDK, network request or generation occurs in Replay.
- AI overlay integration requires the recorded base and current permission.
  Stale/conflicting content is retained without modifying the Workspace and may
  be rejected or redelegated; no automatic merge is invented.

Individual assertions and fixtures are implementation evidence only after their
canonical execution, replay, storage and information-boundary tests pass.
Task3.2/3.3/4.2 acceptance evidence and final completion assessment are recorded
in [g5-collaboration.md](g5-collaboration.md).
