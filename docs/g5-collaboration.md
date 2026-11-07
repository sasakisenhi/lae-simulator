# G5 非同期協働・AI成果統合

対象は `build-reproducible-simulation-foundation` の Task3.2、3.3、4.2。
G6の終了条件拡張・保存閉包、G7以降の証拠検索・インタビューは実装しない。
不変条件の事前記録は [g5-invariants.md](g5-invariants.md)。

## 実行・状態・因果

CF0と同じ `canonical.start_execution / transition / replay_history / project_verified`
を維持し、G3/G4のLocalSession/LocalEvent/LocalStateを拡張した。
別の時計、Queue、Replay方式、保存器は追加していない。

`CollaborationDefinition` は協働者の既知claim、証拠、共有可能入力、承認範囲、
可用性変更、容量と、版付き固定応答規則を保持する。可用性回復は失効したAI世代を復活させない。
`CollaborationState` は依頼の各generation、通知段階、現在grant、作業区間、
中断文脈を保持する。予約予定はReducerが発生させる次イベントの義務であり、
実行対象の正準Queueは既存SchedulerState.pendingだけである。
Engineは義務をEventScheduledとして記録し、Queue先頭を消費して効果を要求する。
Reducerが予約値・投入連番・原因・消費・効果の対応を照合する。

質問／委任の本人操作も既存の時間モデルで予約・消費する。
依頼は選択イベントから一意に識別され、同一依頼の再委任はgenerationを増加させる。
応答・承認・通知・統合は依頼IDとgenerationを参照する。
古い応答は旧世代への到着として保存し、新世代を完了させない。
取消、timeout、棄却、競合後の成果を成功として復活させない。

## 時間と資源

全順序はG4の `(tick, priority, insertion_sequence, scheduled_id)`。
10=本人作業完了、20=応答・可用性変更、30=通知配送、90=期限を使用する。
同tickで低いphaseへ戻る新規予約は次tickへ送る。
同tickの完了10は取消作用20より先に成立し、後続取消は対象なしとして記録する。
同tickの応答20は依頼timeout90より先に成立する。
Hでは先に投入した全体期限90の後の依頼timeout90を未処理Queueへ残す。
H以後の応答内容は本人の経験へ入らない。

本人の能動作業は1件のみ。待機中の直接再開を含めReducerで重複割当を拒否する。
割り込みは完了予約を失効させ、候補・版・残作業・原因をpaused_tasksへ保存する。
独立作業をしても中断文脈を失わず、新世代の予約で残作業だけを再開する。
世代が異なる古い割り込みはstale-generationとして無作用になる。

WorkIntervalはactive / wait / resumeを区別する。AIは依頼ごとの独立資源を使い、
協働者の容量で開始を制約する。不能・容量不足・承認／入力不足の待機を
AIの能動実行時間へ置き換えない。
`local_resources.resource_intervals` は開いた区間を観測tickで閉じる純粋な投影、
`human_time` は本人の重複しない区間の和集合から経過・能動・純待機を返す。
AI並列時間は本人の純待機へ加算しない。

`activity_transitions` は画面移動(view)と候補変更(task)を別々に追跡する。
画面移動に要する時間は実際のRead/Search/Navigateの区間に含め、抽象的な切替料金を加えない。
再開前の読み直しも明示的なRead/Searchの履歴・時間として残す。
元の目標は固定候補、基準版と残作業は中断文脈、再開は失効イベントへの因果参照で照合できる。
resume区間へ汎用の再開係数を上乗せしない。

## 通知・認識・許可

到着は環境状態、配送は通知の存在、acknowledgeは存在認知、observe_responseは内容閲覧。
観測後にのみ本人claimをACQUIREDへ追加する。AIの推測をCONFIRMEDや管理用真実へ昇格させない。
観測の本文・結果・tick・Workspace基準版・イベントIDを不変のLocalObservationRecordへ保存する。
過去のtimeoutを後日の回答へ上書きせず、過去のCheck/Search履歴も保持する。
Policyには本人の通知状態・観測済み内容だけを渡し、応答予定時刻・未到着本文・他者知識・管理原因は渡さない。

AI入力は観測済みかつ相手へ共有可能なIDに限定し、さらに本人AI設定のinput_classificationsを検査する。
協働者の知識・証拠・承認範囲は明示し、所属や役割名から権限を推定しない。
情報不足はQuestionRequiredに相当するquestion応答、追加scope不足はapproval-requiredとなる。
承認依頼は観測した対象・世代・scope・承認者に限定し、承認前にはoverlayを利用できない。
承認到着時に環境grantを記録し、本人の確認後の新世代だけが利用できる。
固定背景や初期許可は書き換えない。拒否・不能・無応答・timeoutを区別する。

## 固定AI応答と統合

`adapters.collaboration.ResponseAdapter` が取得境界。
既定のFixedResponseAdapterは検証済み入力の固定／準備済み生成応答だけを取得する。
実行中のライブLLM・外部SDK・ネットワーク呼出しはない（Design D5）。
prepared-generatedは準備段階の由来を表し、ライブ生成の実行証拠ではない。

ResponseArtifactは依頼、世代、基準版、証拠ID、取得方式、生成器／応答版、本文、SHA-256を結ぶ。
入力条件と利用範囲は正準依頼・規則・固定シナリオへ追跡する。
Reducerはdigestだけでなく固定応答との内容一致も照合し、再hashした改変も拒否する。
Replayはadapterを呼ばず、保存された応答を同じ規則で検証する。

AI成果は固定Patchを基準版の別overlayとして保持し、人間側への統合時に再検査する。
統合イベントは入力版・出力版・Patch ID・計算結果を必須照合する。
一致版かつ現行権限があれば統合、古い版やbefore不一致は無変更のconflict、
権限不足は無変更のpermission-denied。棄却・新基準版への再委任も正準履歴へ残る。
合成P2の統合成功は正しさを意味せず、C04のmodeled:FAILで反証できる。

## 互換性・境界

新しい演習入力は `fixtures/g2/scenario-collaboration.json`。
元のAI無効シナリオは変更せず、別のEX03/EX04合成仮定として相談役・容量・承認・時間を固定した。
これらはLAEの実測値・実運用上の権限・実AI応答時間ではない。

旧CF0/G3/G4のAPI、保存schema、JSONLに不要なフィールドを追加しない。
G5だけstate profileをg5-local-1.0、manifestへ任意のcollaboration監査情報を追加する。
保存・再取得とも共通artifact bundleとReplay/投影照合を使用し、派生状態は正解としない。
公開投影は操作・通知・待機・統合の最小メタデータを追加し、応答本文・未来予約・管理理由は公開しない。
G7以降の詳細な証拠公開・本人パッケージ生成へ範囲を広げない。

## 受入証拠

`tests/test_async_collaboration.py` の46件と `test_collaboration.py` の4件。

| 要求／Task | 主な反例・縦断テスト |
| --- | --- |
| SE02/SE09/SE21、3.2 | interrupt_independent_work_resume、interrupted_task_can_cancel、old_control_generation、direct_resume_cannot_overlap_wait、same_tick_completion |
| SE10、3.2 | ai_parallel_interval、no_response_timeout_and_pure_wait、explicit_rereading、account_time単体の重複区間拒否 |
| SE07、3.3 | approval_blocks_edit、approval_denied、undefined_approval_scope、approver_cannot_inherit_authority、missing_input、capacity_rejection、peer_availability_change |
| SE08、3.3 | reply_arrival_and_delivery_do_not_imply_observation、unarrived_response、duplicate_response、hidden_future_response、late_reply_does_not_rewrite |
| generation・同tick・H | reply_timeout_same_tick、horizon_timeout_tie、late_old_generation、zero_delay_reply、cancelled_request_cannot_wait |
| SE07/SE11、4.2 | integration_deadline、integration_cancellation、interrupted_integration_resumes、ai_overlay_integrates、stale_ai_overlay_conflict、discard_retains_artifact、human_integration_permission_denial、ai_suggestion_is_acquired |
| 固定・監査・情報境界 | frozen_adapter_only_used_in_execution、prepared_frozen_response、rehashed_forged_response、response_provenance、ai_shared_classification、unobserved_and_management_input |
| 保存・決定性 | g5_saved_run、storage_rejects_modified_response_even_after_manifest_rehashed、causal_and_reservation_metadata、public_projection、hash_seed_independent_processes |

旧CF0の保存物はG4以前の実物 `/tmp/lae-old-cf0-runs` を再取得する。
旧G3の有効な保存形式は既存 `test_legacy_local_snapshot_is_upgraded_by_replay` で確認する。
全CF0/G1/G2/G3/G4回帰も実行する。個々の結果と独立レビュー所見は完了報告で区別する。

## レビューと残る範囲

独立コンテキストのレビューで入力分類迂回、統合版偽装、bool世代、不能時間計上、
取消後待機、旧世代割り込み、待機中直接再開、統合中の期限・取消・中断の反例を検出し、修正と回帰テストを追加した。
サブエージェントは編集しない運用でレビューしたが、OS権限で分離した別セッションではない。

固定応答の意味内容・合成時間の現実妥当性は自動検査では保証しない。
実AIの速度、外部サービス、実人間の経験的評価は未実施。
G6以降は未実装のままとし、G5完了後も自動進行しない。

## 最終検証結果

- 全unittest: **184件成功**。G5追加分は非同期縦断46件・値型／会計4件の計50件。
- Ruff全体: 成功。mypy strict: 56ファイル成功。
- compileall、`uv lock --check --offline`、OpenSpec strict validation、`git diff --check`: 成功。
- 異なるPYTHONHASHSEEDの独立プロセスでイベント・状態・認識・本人投影・公開投影が一致。
- 旧CF0実保存物: 8イベント・公開3件でvalid。旧G3は旧形式を再構成した保存物の再取得試験が成功。
- 最終独立レビュー: 184件再実行、統合の期限反例を手動で再検証、未修正の重大指摘なし。
- Task3.2/3.3/4.2の各完了条件を照合してチェック更新。全体進捗13/25。
  G6以降は未着手。コミット、push、deploy、archiveは行わない。

## G5で追加・変更したファイル

| 責務 | ファイル |
| --- | --- |
| 固定協働定義と入力検証 | `world/collaboration.py`、`world/scenario.py`、`simulation/local_loader.py`、`simulation/duration.py` |
| 値型・依頼／通知遷移 | `simulation/collaboration_model.py`、`simulation/local_collaboration.py`、`simulation/local_model.py`、`simulation/local_reducer.py` |
| 実行調停・共通Scheduler接続 | `simulation/local_engine.py`、`simulation/local_timing.py` |
| 版付き統合・資源会計 | `simulation/local_ai.py`、`simulation/local_resources.py` |
| 取得adapter | `adapters/__init__.py`、`adapters/collaboration.py` |
| 本人・公開投影と保存 | `simulation/local_policy.py`、`simulation/local_projector.py`、`simulation/local_store.py` |
| 合成適合入力 | `fixtures/g2/scenario-collaboration.json`、`fixtures/g2/collaboration-review.txt` |
| 受入反例 | `tests/test_async_collaboration.py`、`tests/test_collaboration.py` |
| 記録 | `docs/g5-invariants.md`、本書、対象changeの`tasks.md` |

ソースの相対パスは `src/lae_simulator/` 以下。
G3/G4以前の未コミット変更は保持した。上表は今回G5で扱ったファイルであり、
作業ツリー全体の既存差分を今回の新規変更として数えていない。
