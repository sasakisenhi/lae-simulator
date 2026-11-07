# G6 終了・正準Replay・保存閉包

対象: build-reproducible-simulation-foundation / Task5.1、5.2、5.3。
開始基準はG5完了13/25。G5の記録はg5-collaboration.md。
開始時の既存差分はcanonical_store.pyの例外時cleanupとtest_g6_storage_failures.py。
これらを保持して拡張した。G7以降、外部送信、commit/push/deploy/archiveは対象外。

## 不変条件と所有者

- 終了結果はReducerが決め、Store/Projectorは同じ履歴から検証する。
- SUBMITTEDは選択・時間予約・消費・仮想提出・直後の対応終了の因果列を必要とする。
  提出後に編集して古い提出を使うことも、提出を飛ばして終了することも拒否する。
- 提出には現行の差分、説明、確認範囲、未検証事項、提出先へのcreate権限が必要。
  全CheckのPASSやC11/C12の実行を要求しない。確認しない場合はunverifiedを明示できる。
  Checkを根拠にする場合は観測イベントID・現行版を照合し、coverageはmodeledに限る。
  未観測のAI成果はWorkspaceへ統合できず、権限・版条件は既存G5のReducerが検証する。
- 提出先は固定入力のローカル資源。外部URLを受理しない。記録は仮想PR ID、exercise IDと
  参照用source_issue_refsを分離し、external_send=falseを保持する。時間は論理tickで、
  資料の2024年日時を2026年演習の実行日時へ流用しない。
- INCOMPLETEは有効な業務結果。deadline、情報・承認待ち、本人の保留を内部失敗と区別する。
  理由、残依存、未処理予約、Workspace版はclosure記録で正準状態へ結び付ける。
- CANCELLEDは本人のrun.defer能力と明示理由を必要とするrun全体の終了。
  個別予約取消は別イベントで、run終了を意味しない。終了後は全遷移を拒否する。
- 提出完了10直後の終了はその効果として原子的に記録し、後続の同tick予約を未処理として保持する。
  期限や割り込みの順序・generationを別系統で判定しない。
- Replayは全実装済みイベント族を共通transitionとドメイン純粋Reducerへ渡す。
  Policy・外部adapterを呼ばず、型・ID・因果・時計・予約・版・認識・権限・終了を検査する。
- 保存状態、Queue、認識、公開投影、検証記録は正準履歴と照合するキャッシュである。
  無効な部分結果を保存成功・有効公開へ変換しない。

## 構造

local_outcomes.py: 提出・終了の純粋な前提検査と終了概要。
local_validation.py: 初期状態・イベントbytes・Replay・最終状態・公開投影・資源会計の照合。
local_engine.py: 共通begin/completeを用いた仮想提出とrun取消の要求。
local_reducer.py: payload型検査、提出終了の連続性、状態更新の権威。
local_store.py: serialization、G6 closure.jsonとmanifestの結合・再取得時照合。
canonical_store.py: 共通artifact bundleの原子的rename、例外cleanup、内容digest、artifact集合検査。
新しいQueue・Replay実装・業務ルールのStore側再実装は追加していない。

## 保存・互換性

G6は既存schema1.0へ任意のclosure_contract=g6-closure-1を追加する。
この契約のrunはclosure.jsonを必須とし、全artifact digestと再計算結果を照合する。
closureには終了理由・正準末尾の明示理由、残依存・Q、資源会計、仮想PR、固定入力ID、
イベント数、妥当性、保存時の環境・正規化規則を記録する。
新形式は未知の派生状態フィールドもcanonical再serialization照合で拒否する。

旧CF0と旧G3/G4/G5は従来のartifact構成で読める。旧G3観測欄のない形式はReplayから
派生状態を復元して照合する。旧形式テストはG6契約とclosureを取り除いて旧形式を再構成する。
旧形式にG6契約を偽装した欠落artifactを許すための互換分岐は設けない。

一時ディレクトリへ全てを書き、完成先へrenameする。シリアライズ・書込み失敗時にはcleanupし、
完成済みrunを上書きしない。読込み時はディレクトリ名、Manifest、固定入力、digest、
Replay、派生情報を再検証する。失敗は既存の独立FailureRecordを持つPersistenceErrorで返し、
壊れた保存先への失敗報告書込み成功を要求しない。

## 受入証拠

| タスク | 条件 | 対応テスト |
| --- | --- | --- |
| 5.1 | 有効な提出・FAILとの分離・未実施明示 | submission_is_not_check_pass、no_checks_may_be_declared_unverified |
| 5.1 | 不正提出・stale提出・虚偽executed | forged_submitted、missing_description、direct_submission_cannot_become_stale、submission_cannot_claim_executed |
| 5.1 | 取消・終了後拒否・同tick | cancel_is_run_scoped、submission_completion_keeps_later_same_tick_timeout |
| 5.1 | 期限・応答/承認待ち | 既存G4/G5のdeadline・timeout・approval・horizon縦断テスト |
| 5.2 | 撤回・改変・型・Policy非実行 | revert_check_incomplete、optional_payload_type_errors、replay_does_not_invoke_policy_or_adapter |
| 5.2 | 観測・非同期・generation・承認統合 | 既存G3〜G5全回帰、approval_ai_integration_submission_round_trip |
| 5.3 | 保存再取得・派生不一致・改変 | stored_state_and_projection、rehashed_closure_report、manifest_audit_metadata、missing_closure、missing_artifact |
| 5.3 | 保存失敗と独立報告 | test_g6_storage_failuresの2件、storage_failure_has_independent_failure_record |
| 5.3 | 独立プロセスの保存物一致 | stored_bytes_independent_of_python_hash_seed |

検証入口はdocs/development-workflow.md。件数だけを受入根拠にしない。
旧CF0実保存物の再取得も独立して実行する。旧G3は再構成した互換保存物で検証する。

## レビュー・保証範囲

独立の別コンテキストで編集なしのレビューを実施した。OS権限の分離ではない。
stale提出、虚偽executed、同tick提出、最低Check数の過剰制約、終了理由、payload型、
Manifest監査情報の指摘を修正し、反例を追加した。

Manifestの歴史的なPython/OS情報を現在の環境と同一とは要求しない。
closureとの一致は保存物の整合性保証であり、第三者署名による真正性保証ではない。
全artifactを矛盾なく再生成できる攻撃者の来歴を認証する機能は含まない。
atomic renameはプロセスから見た公開境界であり、電源断に対する永続化保証は追加していない。
外部AI・GitHub送信・実チェック実行・人間による経験的妥当性評価は未実施。

最終結果: 全unittest205件成功（G6関連21件）。Ruff、mypy strict60ファイル、compileall、
uv lock整合性、OpenSpec strict validation、git diff --check成功。
独立レビューはG6関連19件・全203件を実行し、未修正の重大指摘なし。
その後追加した承認AI提出保存と独立FailureRecordの2件も含め、親で205件を再検証した。
旧CF0実保存物は8イベント・公開3件・valid。旧G3互換形式の再取得も成功。
Task5.1/5.2/5.3を完了更新し、進捗16/25。G7以降へは進んでいない。
