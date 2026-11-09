# G9 search-profile compatibility and VA impact record

Date: 2026-11-09  
Change: `build-reproducible-simulation-foundation`  
Scope: G9 Tasks 2.6, 2.7, 6.6 repair and regression. Task 7.2 / VB-C, G8 and later work are excluded.

## Status and decision boundary

The earlier record stated **Task 6.6 impact PASS, limited to exercised obligations**, based on 317 passing tests. Subsequent review found a multi-file reference binding bug, Ruff/mypy failures, missing 1.4.0 boundary coverage and stale planning text. That earlier statement alone is insufficient for G9 completion.

The repair implements the user's approved one-file constraint and adds explicit boundary checks. Automated contract regression and technical inspection results are recorded below. **Following the subsequent null-reference repair, renewed verification snapshot and human confirmation, G9 Tasks 2.6/2.7/6.6 are complete.** No old aggregate VA verdict is upgraded, and existing VB INCONCLUSIVE / Task 7.2 incomplete status is preserved. The impact determination is independent of VB execution; it is not a separately isolated reviewer verdict.

## Approved constraint and implementation

Each recorded Workspace reference resolves to exactly one full Workspace path plus one or more inclusive line ranges. These examples are accepted when the file and bounds exist:

- `a.ts:1`
- `a.ts:1-5,8-10`
- `eslintServer.ts:692-700,823-827`

`a.ts:1,b.ts:2` and `a.ts:1-3,b.ts:5-7` are rejected with `multiple-workspace-reference-paths`, the reference's evidence field location and an explicit one-file reason. The parser does not adopt the last file, reassign previous ranges or return partial results. Repeated names resolving to the same full path remain valid. Legacy 1.0–1.3 validation is unchanged. Supporting multiple files is a future specification change, not part of G9.

`world/search_profile.py` owns pure scope/reference validation. `world/scenario.py` applies it during input validation; `simulation/local_loader.py` checks against the G1-verified Workspace. `simulation/local_reducer.py` searches current bytes in scope and filters bound, non-audit, non-invalidated references. `local_projector.py` exposes only a common scope limitation. No Policy priority or candidate catalog was changed.

The initial G9 implementation also removed `search_profile` from the 1.4.0 `stable_run_id` input, preserving full Scenario content identity in execution provenance and saved `scenario.json`. Same-result profile differences therefore preserve public identifiers. Older versions retain their ID construction. Distinct input identities can share that observation-facing run ID, so comparisons must use separate save roots; this record does not claim same-root coexistence.

## Requirement → design → implementation → test evidence

All test names below are methods of `SearchProfileContractTests` in `tests/test_search_profile_contract.py`, unless qualified otherwise. Their individual results are in `g9-validation/unittest.log`.

| Requirements / design / task | Implementation | Verification |
|---|---|---|
| WD02/WD16, D14, 2.6 | `world/search_profile.py`, `world/scenario.py`, `simulation/local_loader.py` | `test_single_file_reference_examples_keep_ranges`, `test_multiple_file_reference_rejected_with_explicit_reason`: exact accepted/rejected examples, reason/location, same-path aliases, loader rejection, legacy validation |
| WD02/WD14–16, D3/D14, 2.6 | Version-gated Scenario validation | `test_profile_has_strict_shape_path_and_set_semantics`, `test_omitted_profile_and_nonempty_partial_scope_load_after_g1`, `test_reference_source_ambiguity_and_line_ranges_are_rejected`, `test_search_scope_cannot_resolve_a_reference_from_another_source`, `test_old_scenario_versions_reject_search_profile`, `test_patch_target_requirement_is_versioned_without_changing_legacy_meaning`, `test_1_4_initial_knowledge_source_limits_are_inherited`, `test_1_4_inherits_required_claims_patch_ids_and_tool_availability` |
| SE06/SE14/SE20/SE23–25, D4/D6/D14, 2.7 | Current-Workspace search in `local_reducer.py` | `test_current_version_search_scope_and_replay_are_deterministic`, `test_profile_and_reference_order_do_not_change_search_results`: scoped hits, bound reference IDs, repeated search, no-hit semantics, input-order invariance, live/Replay equality |
| SE06/SE20/SE23–25, D6/D14, 2.7 | Version and availability checks; invalidated/audit-reference exclusions | `test_scoped_search_uses_patched_bytes_excludes_invalidated_and_audit_refs`, `test_unavailable_scoped_search_is_not_no_match_and_replays`: changed-byte oracle differs from B0, repeated overlay search, stale-version rejection without state change, forged Replay rejection, unavailable distinct from no-match |
| SE03/SE14/SE20, EP04/EP06/EP11/EP14, D8/D10/D14, 6.6 | `local_model.py` identity, public projection and existing evidence boundary | `test_equal_observations_across_different_profiles_keep_actor_and_public_outputs`: pre-search observations/candidates/choice and package/public bytes; same-result package/public bytes including IDs/digests/counts; unknown-role error equality; independent repeated execution and Replay; save/retrieve; re-hashed public-log and final-state mutation rejection; injected persistence failure |
| WD03, SE14–18/SE20–22, D10/D14, 6.6 | Existing compatibility, canonical persistence and CF0 paths | `test_pinned_g6_evidence_bytes_remain_unchanged`; `test_g7_repair.G6CompatibilityTests.test_actual_g6_artifacts_validate_and_return_only_current_projection`; `test_g6_closure`; `test_walking_skeleton.WalkingSkeletonTests.test_cf0_runs_from_policy_to_valid_incomplete_result`; all legacy regressions in full suite |

The changed-Workspace test explicitly declares a synthetic test-only candidate precondition allowing known overlay versions, using the existing input expression. This does not alter the production candidate catalog or Policy. The input-order test compares search results rather than requiring identical event IDs across reordered Scenario inputs with different content identities.

## Validation evidence

`g9-validation/target-manifest.json` freezes code/test hashes, G1/G2 input hashes, dependency lock, Python/platform, baseline commit and historical evidence hashes before the final full run. `g9-validation/results.json` records exact commands, exit codes and log digests. These are developer verification artifacts, not new simulation storage artifacts or schema.

- `uv sync --locked`, `uv lock --check`: exit 0.
- `uv run --locked python -m unittest discover -s tests -v`: 324 tests, all passed. The log also contains intentional failure-fixture CLI output; unittest itself exits 0.
- `uvx --from ruff==0.17.4 ruff check .`: exit 0.
- `uvx --from mypy==2.4.1 mypy --strict src tests`: exit 0, 83 source files.
- `uv run --locked python -m compileall -q src tests`: exit 0.
- `openspec validate build-reproducible-simulation-foundation --type change --strict --no-interactive`: exit 0.
- `git diff --check`: exit 0.

The final target recheck verifies unchanged code/tests and G1/G2 inputs during verification. Historical `docs/va-evidence`, `docs/vb-evidence`, `docs/vb-reassessment`, `docs/vb-contract-evidence` and pinned G6 fixture bytes match their pre-run hashes. Old evidence was neither migrated nor rewritten. Planning documents are updated for this authorized repair stage; the VB preregistered conditions and predictions are unchanged.

## Responsibility and dependency inspection

The parser's one-file guard stays beside reference resolution; range validation and error aggregation remain local and directly unit-testable. The typed loader tuple and test narrowing fix mypy errors; import/style fixes satisfy Ruff. No dependency, event family, saved-state schema, CLI entry or external I/O was added. Domain reduction remains pure; file reads stay at the input-loading boundary. Existing Loader/Reducer responsibilities do not require a broad split for this local repair.

`g9-validation/import-check.json` compares module-scope absolute-import dependencies against HEAD: no new cycle and no World→Simulation import. Deferred function imports in the canonical dispatch layer are excluded from that static check and retain the existing architecture. This is an author inspection, not an independently isolated code review.

## Limits and human decision

### Follow-up input-validation repair (2026-11-09)

The subsequent G9 review reproduced a `TypeError` for Scenario 1.4.0 with
`references: null`. Search-profile validation now checks the array type before
iterating references, leaving the existing core validator responsible for the
structured `$.references` / `invalid-type` issue. Invalid references do not
prevent independent search-profile validation.

Regression tests cover null, boolean, number, string and object values for both
1.3.0 and 1.4.0, plus the `validate-scenario` CLI's structured invalid response
and exit code 2 for null references. The pre-follow-up snapshot is retained unchanged under
`g9-validation/history/pre-null-reference-fix/`. The refreshed top-level
manifest and logs attest the updated code/test hashes: 324 tests passed, all
recorded commands exited 0, and target/input/lock/historical-evidence and
import-boundary rechecks passed. Human confirmation authorizes G9 completion
and the separate VB evaluation. The G9 snapshot precedes VB evaluator additions.

The four requested completion checks have inspectable implementation, tests and renewed logs. The one-file restriction, traceability and final G9 completion have received human confirmation; the three task checkboxes are now complete.

This deterministic regression does not establish empirical usefulness, real-user effects, every historical format, formal VB responsiveness, or overall MVP acceptance. At the G9 snapshot boundary, Task 7.2 / new C had not been performed; the subsequent VB run is separately authorized and recorded. G8 and later work, external sending/publishing, commit, push and archive are outside this G9 record. No real OSS execution is inferred from modeled results.
