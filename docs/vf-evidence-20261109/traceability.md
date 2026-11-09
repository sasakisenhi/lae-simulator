# VF 要件追跡表

状態は内容照合に基づく作成者の集約判断。テスト件数・ファイル存在だけによる自動受入ではない。各証拠文書の条件・テスト名・限界まで参照する。EP18と7.4は人間最終承認に基づきPASS（human-approval.json）。

| Requirement | Design | Tasks | 判定 | 試験 | 条件・受入証拠 |
|---|---|---|---|---|---|
| WD01 | D1/D3/D12 | 1.2, 1.3 | PASS | [tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/input-contract.md](../../docs/input-contract.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| WD02 | D1/D3/D12/D14 | 1.2, 1.3, 2.6 | PASS | [tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/input-contract.md](../../docs/input-contract.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| WD03 | D2/D10/D12/D14 | 1.2, 1.3, 2.6, 5.3 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/input-contract.md](../../docs/input-contract.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| WD04 | D5/D12 | 1.2, 1.3, 3.1 | PASS | [tests/test_scheduler.py](../../tests/test_scheduler.py)<br>[tests/test_scheduler_randomness.py](../../tests/test_scheduler_randomness.py)<br>[tests/test_timing.py](../../tests/test_timing.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/g4-scheduler.md](../../docs/g4-scheduler.md)<br>[docs/input-contract.md](../../docs/input-contract.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| WD05 | D2/D12 | 1.2, 2.1 | PASS | [tests/test_provenance.py](../../tests/test_provenance.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/fixed-materials.md](../../docs/fixed-materials.md)<br>[docs/input-contract.md](../../docs/input-contract.md) |
| WD06 | D3/D11 | 2.2, 7.2, 7.3 | PASS | [tests/test_intervention_contract.py](../../tests/test_intervention_contract.py)<br>[tests/test_scenario_contract.py](../../tests/test_scenario_contract.py)<br>[tests/test_vb_search_profile_harness.py](../../tests/test_vb_search_profile_harness.py)<br>[tests/test_vc_harness.py](../../tests/test_vc_harness.py) | [docs/scenario-contract.md](../../docs/scenario-contract.md)<br>[docs/vb-search-profile-evidence/report.md](../../docs/vb-search-profile-evidence/report.md)<br>[docs/vc-evidence-20261109-repeat-1/report.md](../../docs/vc-evidence-20261109-repeat-1/report.md) |
| WD07 | D2 | 2.1 | PASS | [tests/test_provenance.py](../../tests/test_provenance.py) | [docs/fixed-materials.md](../../docs/fixed-materials.md) |
| WD08 | D3/D6/D7 | 2.2, 2.3 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_scenario_contract.py](../../tests/test_scenario_contract.py) | [docs/scenario-contract.md](../../docs/scenario-contract.md) |
| WD09 | D3/D4 | 1.2, 2.5 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/input-contract.md](../../docs/input-contract.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| WD10 | D5 | 3.1 | PASS | [tests/test_scheduler.py](../../tests/test_scheduler.py)<br>[tests/test_scheduler_randomness.py](../../tests/test_scheduler_randomness.py)<br>[tests/test_timing.py](../../tests/test_timing.py) | [docs/g4-scheduler.md](../../docs/g4-scheduler.md) |
| WD11 | D2/D3 | 1.2, 2.4 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/input-contract.md](../../docs/input-contract.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| WD12 | D1/D3/D6/D7/D12 | 1.2, 1.3, 2.2, 2.4, 4.1 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_scenario_contract.py](../../tests/test_scenario_contract.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/input-contract.md](../../docs/input-contract.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| WD13 | D2/D3 | 1.2, 2.4 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_world_contract.py](../../tests/test_world_contract.py) | [docs/input-contract.md](../../docs/input-contract.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| WD14 | D3/D4/D14 | 2.2, 2.4, 2.6 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_scenario_contract.py](../../tests/test_scenario_contract.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| WD15 | D3/D4/D14 | 2.2, 2.5, 2.6 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_scenario_contract.py](../../tests/test_scenario_contract.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| WD16 | D3/D6/D14 | 2.6 | PASS | [tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md) |
| SE01 | D10 | 5.1 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py) | [docs/g6-closure.md](../../docs/g6-closure.md) |
| SE02 | D5 | 3.2, 3.3 | PASS | [tests/test_async_collaboration.py](../../tests/test_async_collaboration.py)<br>[tests/test_collaboration.py](../../tests/test_collaboration.py)<br>[tests/test_timed_local.py](../../tests/test_timed_local.py) | [docs/g4-scheduler.md](../../docs/g4-scheduler.md)<br>[docs/g5-collaboration.md](../../docs/g5-collaboration.md) |
| SE03 | D3/D4/D11/D14 | 2.5, 2.7, 6.6, 7.2 | PASS | [tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_intervention_contract.py](../../tests/test_intervention_contract.py)<br>[tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_vb_search_profile_harness.py](../../tests/test_vb_search_profile_harness.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md)<br>[docs/vb-search-profile-evidence/report.md](../../docs/vb-search-profile-evidence/report.md) |
| SE04 | D3/D4 | 2.4 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py) | [docs/scenario-contract.md](../../docs/scenario-contract.md) |
| SE05 | D4 | 2.5 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py) | [docs/scenario-contract.md](../../docs/scenario-contract.md) |
| SE06 | D3/D4/D6/D12/D14 | 1.3, 2.4, 2.7, 7.2 | PASS | [tests/test_intervention_contract.py](../../tests/test_intervention_contract.py)<br>[tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_vb_search_profile_harness.py](../../tests/test_vb_search_profile_harness.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md)<br>[docs/vb-search-profile-evidence/report.md](../../docs/vb-search-profile-evidence/report.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE07 | D5 | 3.3, 4.2 | PASS | [tests/test_async_collaboration.py](../../tests/test_async_collaboration.py)<br>[tests/test_collaboration.py](../../tests/test_collaboration.py) | [docs/g5-collaboration.md](../../docs/g5-collaboration.md) |
| SE08 | D5 | 3.3 | PASS | [tests/test_async_collaboration.py](../../tests/test_async_collaboration.py)<br>[tests/test_collaboration.py](../../tests/test_collaboration.py) | [docs/g5-collaboration.md](../../docs/g5-collaboration.md) |
| SE09 | D4/D5 | 3.2 | PASS | [tests/test_timed_local.py](../../tests/test_timed_local.py) | [docs/g4-scheduler.md](../../docs/g4-scheduler.md) |
| SE10 | D5 | 3.2 | PASS | [tests/test_timed_local.py](../../tests/test_timed_local.py) | [docs/g4-scheduler.md](../../docs/g4-scheduler.md) |
| SE11 | D6 | 2.3, 2.4, 4.2 | PASS | [tests/test_collaboration.py](../../tests/test_collaboration.py)<br>[tests/test_local_work_model.py](../../tests/test_local_work_model.py) | [docs/g5-collaboration.md](../../docs/g5-collaboration.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| SE12 | D7 | 2.3, 4.1 | PASS | [tests/test_local_work_model.py](../../tests/test_local_work_model.py) | [docs/scenario-contract.md](../../docs/scenario-contract.md) |
| SE13 | D10/D12 | 1.3, 5.1 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE14 | D5/D10/D12/D14 | 1.1, 1.3, 3.1, 6.6, 7.1 | PASS | [tests/test_cli.py](../../tests/test_cli.py)<br>[tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_scheduler.py](../../tests/test_scheduler.py)<br>[tests/test_scheduler_randomness.py](../../tests/test_scheduler_randomness.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_timing.py](../../tests/test_timing.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/architecture/foundation.md](../../docs/architecture/foundation.md)<br>[docs/g4-scheduler.md](../../docs/g4-scheduler.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/va-acceptance.md](../../docs/va-acceptance.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE15 | D10/D12/D14 | 1.1, 1.3, 3.1, 5.3, 6.6 | PASS | [tests/test_cli.py](../../tests/test_cli.py)<br>[tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_scheduler.py](../../tests/test_scheduler.py)<br>[tests/test_scheduler_randomness.py](../../tests/test_scheduler_randomness.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_timing.py](../../tests/test_timing.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/architecture/foundation.md](../../docs/architecture/foundation.md)<br>[docs/g4-scheduler.md](../../docs/g4-scheduler.md)<br>[docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE16 | D7/D10/D12 | 1.3, 5.2 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE17 | D8/D9/D10/D12 | 1.3, 5.3, 7.1 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/va-acceptance.md](../../docs/va-acceptance.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE18 | D10/D12 | 1.3, 5.3 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE19 | D11/D13/D14 | 7.2 | PASS | [tests/test_intervention_contract.py](../../tests/test_intervention_contract.py)<br>[tests/test_vb_search_profile_harness.py](../../tests/test_vb_search_profile_harness.py) | [docs/vb-search-profile-evidence/report.md](../../docs/vb-search-profile-evidence/report.md) |
| SE20 | D4/D10/D12/D14 | 1.3, 2.7, 5.2, 5.3, 6.6 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE21 | D4/D5/D12 | 1.3, 3.1, 3.2, 5.2 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_scheduler.py](../../tests/test_scheduler.py)<br>[tests/test_scheduler_randomness.py](../../tests/test_scheduler_randomness.py)<br>[tests/test_timed_local.py](../../tests/test_timed_local.py)<br>[tests/test_timing.py](../../tests/test_timing.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g4-scheduler.md](../../docs/g4-scheduler.md)<br>[docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE22 | D10/D12 | 1.3, 5.3 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g6-closure.md](../../docs/g6-closure.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| SE23 | D4/D14 | 2.4, 2.7, 6.6 | PASS | [tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| SE24 | D3/D4/D14 | 2.5, 2.7, 6.6 | PASS | [tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_local_work_model.py](../../tests/test_local_work_model.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/scenario-contract.md](../../docs/scenario-contract.md) |
| SE25 | D4/D6/D14 | 2.7, 6.6, 7.2 | PASS | [tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_intervention_contract.py](../../tests/test_intervention_contract.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_vb_search_profile_harness.py](../../tests/test_vb_search_profile_harness.py) | [docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/vb-search-profile-evidence/report.md](../../docs/vb-search-profile-evidence/report.md) |
| EP01 | D8/D12 | 1.3, 6.1 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| EP02 | D8/D12 | 1.3, 6.1, 6.5 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_g8_cli.py](../../tests/test_g8_cli.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/g8-acceptance.md](../../docs/g8-acceptance.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| EP03 | D8/D12 | 1.3, 6.1 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| EP04 | D8/D9 | 6.2 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md) |
| EP05 | D9 | 6.2 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md) |
| EP06 | D8/D9/D12/D14 | 1.3, 6.1, 6.3, 6.4, 6.6 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_g8_offline_repair.py](../../tests/test_g8_offline_repair.py)<br>[tests/test_interview.py](../../tests/test_interview.py)<br>[tests/test_interview_remote.py](../../tests/test_interview_remote.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_walking_skeleton.py](../../tests/test_walking_skeleton.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/g8-acceptance.md](../../docs/g8-acceptance.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/walking-skeleton.md](../../docs/walking-skeleton.md) |
| EP07 | D8 | 6.4 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md) |
| EP08 | D9 | 6.3, 6.5 | PASS | [tests/test_g8_cli.py](../../tests/test_g8_cli.py)<br>[tests/test_g8_offline_repair.py](../../tests/test_g8_offline_repair.py)<br>[tests/test_interview.py](../../tests/test_interview.py)<br>[tests/test_interview_remote.py](../../tests/test_interview_remote.py) | [docs/g8-acceptance.md](../../docs/g8-acceptance.md) |
| EP09 | D9 | 6.3 | PASS | [tests/test_g8_offline_repair.py](../../tests/test_g8_offline_repair.py)<br>[tests/test_interview.py](../../tests/test_interview.py)<br>[tests/test_interview_remote.py](../../tests/test_interview_remote.py) | [docs/g8-acceptance.md](../../docs/g8-acceptance.md) |
| EP10 | D9 | 6.3 | PASS | [tests/test_g8_offline_repair.py](../../tests/test_g8_offline_repair.py)<br>[tests/test_interview.py](../../tests/test_interview.py)<br>[tests/test_interview_remote.py](../../tests/test_interview_remote.py) | [docs/g8-acceptance.md](../../docs/g8-acceptance.md) |
| EP11 | D7/D8/D14 | 6.1, 6.6, 7.1 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/va-acceptance.md](../../docs/va-acceptance.md) |
| EP12 | D8 | 6.4, 6.5 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g8_cli.py](../../tests/test_g8_cli.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/g8-acceptance.md](../../docs/g8-acceptance.md) |
| EP13 | D13 | 7.3 | PASS | [tests/test_vc_harness.py](../../tests/test_vc_harness.py) | [docs/vc-evidence-20261109-repeat-1/report.md](../../docs/vc-evidence-20261109-repeat-1/report.md) |
| EP14 | D8/D14 | 6.1, 6.4, 6.6, 7.3 | PASS | [tests/test_fixed_evidence.py](../../tests/test_fixed_evidence.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_g7_repair.py](../../tests/test_g7_repair.py)<br>[tests/test_search_profile_contract.py](../../tests/test_search_profile_contract.py)<br>[tests/test_vc_harness.py](../../tests/test_vc_harness.py) | [docs/g7-reacceptance.md](../../docs/g7-reacceptance.md)<br>[docs/g9-search-profile-impact.md](../../docs/g9-search-profile-impact.md)<br>[docs/vc-evidence-20261109-repeat-1/report.md](../../docs/vc-evidence-20261109-repeat-1/report.md) |
| EP15 | D9 | 6.3 | PASS | [tests/test_g8_offline_repair.py](../../tests/test_g8_offline_repair.py)<br>[tests/test_interview.py](../../tests/test_interview.py)<br>[tests/test_interview_remote.py](../../tests/test_interview_remote.py) | [docs/g8-acceptance.md](../../docs/g8-acceptance.md) |
| EP16 | D9 | 6.3 | PASS | [tests/test_g8_offline_repair.py](../../tests/test_g8_offline_repair.py)<br>[tests/test_interview.py](../../tests/test_interview.py)<br>[tests/test_interview_remote.py](../../tests/test_interview_remote.py) | [docs/g8-acceptance.md](../../docs/g8-acceptance.md) |
| EP17 | D13 | 7.1, 7.2, 7.3, 7.4 | PASS | [tests/test_g6_closure.py](../../tests/test_g6_closure.py)<br>[tests/test_g6_storage_failures.py](../../tests/test_g6_storage_failures.py)<br>[tests/test_g7_privacy.py](../../tests/test_g7_privacy.py)<br>[tests/test_intervention_contract.py](../../tests/test_intervention_contract.py)<br>[tests/test_vb_search_profile_harness.py](../../tests/test_vb_search_profile_harness.py)<br>[tests/test_vc_harness.py](../../tests/test_vc_harness.py) | [docs/va-acceptance.md](../../docs/va-acceptance.md)<br>[docs/vb-search-profile-evidence/report.md](../../docs/vb-search-profile-evidence/report.md)<br>[docs/vc-evidence-20261109-repeat-1/report.md](../../docs/vc-evidence-20261109-repeat-1/report.md) |
| EP18 | D13 | 7.4 | PASS | [tests/test_vf_harness.py](../../tests/test_vf_harness.py) | [docs/vf-evidence-20261109/report.md](../../docs/vf-evidence-20261109/report.md) |

## Scenario inventory

各Scenarioは上記Requirement行の条件・証拠へ対応する。単独の網羅率や全入力の証明ではない。

- EP01: Trace related outputs
- EP02: Retrieve an issue timeline
- EP03: Synthetic focus log
- EP03: Private decision is not telemetry
- EP04: Limited notification
- EP05: No prehistory invention
- EP05: Memory is incomplete
- EP06: Interview context
- EP06: Unknown role
- EP06: Misconfigured public allowlist
- EP06: Observable causality remains available
- EP06: Hidden search profile before observation
- EP06: Irrelevant search scope change
- EP07: Earlier retained evidence
- EP07: Missing evidence
- EP08: Why was a file opened
- EP08: Leading question contains a new event
- EP09: No remembered reason
- EP09: Grounded misunderstanding
- EP10: Trace an answer attempt
- EP11: Forged experience
- EP11: Unsupported external validity
- EP11: Derived information contradicts canonical facts
- EP11: Forged scoped search evidence
- EP12: Follow an alternative hypothesis
- EP12: Retrieval crosses a protected boundary
- EP13: Evidence is inconclusive
- EP13: Blind investigation and sealed assessment
- EP14: Unmodeled GUI details
- EP14: Scoped no hit is not global absence
- EP15: Fabricated or contradictory answer
- EP16: Paraphrase changes an unsupported fact
- EP16: Fixed mistaken or uncertain memory
- EP17: Unready and inconclusive are different
- EP18: Unverified mandatory behavior remains
- SE01: Submit a virtual PR
- SE02: External interruption
- SE02: Dependency release is stale or unobserved
- SE03: Hidden cause does not guide action
- SE03: Unobserved search profile does not guide action
- SE04: Wrong but feasible edit
- SE04: Impossible edit
- SE05: Reading does not imply understanding
- SE05: Counterexample revises belief
- SE06: Search and navigation
- SE06: Tool availability changes the route
- SE06: Scoped search information reaches completed work
- SE07: Approval blocks an AI task
- SE07: Independent human work
- SE08: Delayed attention
- SE09: Resume a suspended task
- SE10: Parallel activity
- SE10: Resumption is already explicit
- SE11: Stale AI patch
- SE11: Index invalidation
- SE12: A modeled check passes
- SE12: Unsupported check
- SE13: Waiting beyond the deadline
- SE13: Submission is not correctness
- SE14: Independent repeated runs
- SE14: Simultaneous events
- SE15: Inspect a saved run
- SE16: Inject invalid history
- SE17: Queries in a different order
- SE17: Changed model
- SE18: Report a persistence failure
- SE19: Change a relevant condition
- SE19: No forced variation
- SE20: Stored state contradicts replay
- SE20: Replay preserves versioned search semantics
- SE21: Replay a cancelled completion
- SE22: Failure does not publish a valid run
- SE23: Observe search failure
- SE24: Initial knowledge changes feasibility
- SE25: Search verified paths at the current version
- SE25: No match within the search scope
- SE25: Apply and replay the same scoped search
- WD01: Inspect a minimal world
- WD02: Invalid reference
- WD02: Unsupported definition version
- WD02: Invalid fixed search profile
- WD02: Ambiguous workspace reference binding
- WD02: One file per recorded Workspace reference
- WD03: Changed preparation output
- WD03: Frozen search scope
- WD04: One issue instead of twelve weeks
- WD05: Exercise is not an LAE product
- WD06: No improvement is justified
- WD07: Exact commit cannot be verified
- WD07: Later issue discussion
- WD08: Candidate is not a scripted path
- WD09: AI is optional
- WD09: Invalid initial knowledge or capability
- WD10: Synthetic duration
- WD11: A fixed document is unavailable
- WD12: Replace a fixture
- WD13: A relationship is outside the index
- WD14: Independent fixed tool availability
- WD14: Legacy input
- WD15: Protected knowledge prerequisite
- WD16: Explicit workspace search scope
- WD16: Omitted search profile
- WD16: Search profile on legacy versions
