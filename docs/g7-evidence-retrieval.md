# G7 evidence retrieval (local)

The fixed evidence API is read-only and operates on a verified local run:

```python
from lae_simulator.simulation.fixed_evidence import (
    get_evidence, related_evidence, search_evidence,
)

records = search_evidence(execution, run, role="researcher", issue="I1955",
                          tick=0, through_tick=20, target="D01",
                          operation="search")
record = get_evidence(execution, run, role="researcher",
                      evidence_id="public:<event-id>")
related = related_evidence(execution, run, role="researcher",
                           evidence_id="document:D01")
```

All filters are optional. `tick` and `through_tick` form an inclusive logical-time
range. `operation` matches the public event kind or a fixed reference relation.
Issue, target, and public ID are exact identifiers. Search results include only
records already present in the public evidence catalog. Related retrieval follows
only IDs and targets in that same catalog; inaccessible, missing, and unknown
records are omitted. Direct retrieval uses the same `unavailable` response for
unknown roles and unavailable IDs.

This local adapter retains verified public event projections, available fixed
public source documents, and references to those documents. It applies no rolling
12-week cutoff. A missing/uncaptured detail is not reconstructed, and an empty
search only describes this fixed catalog, not whether an event happened outside
it. Repeated and reordered retrieval is derived from the same validated run and
does not append events or alter simulation state. Administrative records and
audit-only comments are not included in the researcher catalog.

The participant package uses explicit `EmployeePerception` and
`EmployeeObservation` types. Policy model fields are never copied wholesale.
Search/check knowledge, predictions, and observed requests have participant
identifiers independent of canonical event numbering. Observed time, content,
version, repeated observations, and corrections remain available. Request aliases
are assigned when first observed and remain stable if responses are read in a
different order. Audit-only source claims cannot be declassified by changing a
claim's label; such a participant projection is unavailable.

`audit-mapping.json` is an administrative artifact mapping public/participant IDs
to canonical events. It is digest-checked and compared with replay on load, but
is absent from the researcher catalog. `load_local_run`, its manifest, and its
canonical result are administrative APIs, not researcher exports. The role-bound
retrieval functions are the researcher boundary; OS access to administrative
files is outside the isolation guarantee.

For G6 bundles without G7 version tags, the store checks the original LEV-based
projection using frozen G6 rules, then returns a freshly generated G7 projection.
There is no legacy-mode option on the public projector or retrieval APIs. Mixed,
missing, or unknown G7 contract/version tags are rejected. Old source-generated
compatibility fixtures and their provenance are in `tests/fixtures/g6/`.
