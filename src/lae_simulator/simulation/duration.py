"""Pure keyed duration evaluation, also used to verify recorded draw evidence."""
from __future__ import annotations

import hashlib
import json

from lae_simulator.simulation.local_model import ScenarioExecution
from lae_simulator.simulation.randomness import RandomKey, draw_u64
from lae_simulator.world.collaboration import collaboration_scopes, load_collaboration
from lae_simulator.world.timing import DurationModel, load_timing


def validate_timing_binding(execution: ScenarioExecution) -> None:
    if "sha256:" + hashlib.sha256(execution.canonical_bytes).hexdigest() != execution.content_id:
        raise ValueError("timing canonical input identifier mismatch")
    source = json.loads(execution.canonical_bytes)
    if "collaboration" in source:
        expected_collaboration = load_collaboration(
            source['collaboration'], *collaboration_scopes(source, dict(execution.source_classifications)),
            {row['id'] for row in source['patches']})
        profile = source['participant_profile']
        permissions = tuple(sorted((row['resource_id'], row['action']) for row in profile['permissions']))
        if (execution.collaboration != expected_collaboration or execution.permissions != permissions
                or execution.ai_allowed != profile['ai']['allowed']
                or execution.ai_can_edit != profile['ai']['can_edit']):
            raise ValueError('runtime collaboration differs from canonical input')
    elif execution.collaboration is not None:
        raise ValueError('runtime collaboration is absent from canonical input')
    if "timing" not in source:
        if execution.timing is not None:
            raise ValueError("runtime timing is absent from canonical input")
        return
    expected = load_timing(source["timing"], {row["duration_model"] for row in source["candidates"]})
    bindings = tuple((row["id"], row["operation"], row["duration_model"]) for row in source["candidates"])
    actual = tuple((row.id, row.operation, row.duration_model_id) for row in execution.candidates)
    if (execution.timing != expected or actual != bindings
            or execution.actor_id != source["participant_profile"]["actor_id"]):
        raise ValueError("runtime timing differs from canonical input")


def duration_ticks(model: DurationModel, seed: int, actor_id: str,
                   candidate_id: str, occurrence: int) -> tuple[int, int | None]:
    if model.jitter_ticks == 0:
        return model.ticks, None
    raw = draw_u64(seed, RandomKey("operation-duration", actor_id, candidate_id,
                                  model.id, occurrence))
    return model.ticks + raw % (model.jitter_ticks + 1), raw
