# VB最小契約の具体化・実装と再評価

対象change: build-reproducible-simulation-foundation。Task7.2は未チェック、20/25を維持。
A/Bの実装・独立介入はPASS。Cは情報差のみで行動分岐を示さず、VB総合はINCONCLUSIVE。
評価器の機械結果はNOT EVALUATED/exit2。実行失敗や期待結果違反のFAILではなく、Cの必須行動証拠不足を表す。

## 採用した契約

WD09、SE03/06/19、Design D3/D4の具体化として、実装前にProposal・Design・Specs・Tasksへ追記した。
追加した義務はWD14（固定可用性）、WD15（知識入力検証）、SE23（観測後の可用性反映）、SE24（知識前提一致）。Task7.2とSE19の正式受入条件は変更していない。

Scenario1.3.0:
- rootの任意tool_availability={"code.search": boolean}はWorldの固定実状態。未指定と旧版は従来どおり利用可能。
- Candidateの任意required_claimsは既存LocalCandidate.required_claimsへ接続する。未指定は空。
- 全必要claimの存在・非管理区分・非空かつ検証済み出典・非audit-only出典を検査する。1.3.0の初期知識にも同じ出典上限を適用する。
- 本人保持がINITIAL/ACQUIRED/TENTATIVE/CONFIRMEDなら充足、欠落/WITHDRAWNなら不充足。本人の保持と世界の真実を混同しない。

Policyの優先順位、特定Issueの分岐、正解ラベルは変更していない。候補カタログと静的capabilityを維持する。
検索可用性の実値は固定scenario.jsonから純粋に参照し、Policyや本人パッケージへ転記しない。
検索失敗は既存Searchイベントのobserved_result=tool-unavailableとして正準記録する。observed_messagesのtool-unavailable:code.searchが本人の認識となる。
Policy/Reducerのtool.search条件は、capabilityとこの観測だけを使う。未観測の障害では候補が消えない。
失敗検索は通常の開始・予約・消費・完了を経て資源を解放し、検索結果・claim・架空閲覧を生成しない。有効な業務失敗であり内部INVALIDではない。
動的障害・復旧・通知・再試行・generation・新検索プロファイルは追加していない。

## 実装と不変条件

本体変更: world/scenario.py、simulation/local_loader.py、local_policy.py、local_engine.py、local_reducer.py、新しい純粋helper tool_availability.py。
元から存在したG7差分は保持し、今回local_model/projector/store/employee_evidenceへ追加変更はしていない。

1. 静的能力と実可用性は独立。
2. 隠れた可用性だけでは本人観測・Policy選択・本人package bytesは変わらない。
3. 実可用性falseで成功を偽造した履歴、trueで障害を偽造した履歴はReplayで拒否する。
4. required_claimsは同じ既存前提関数をPolicyとReducerで検査し、撤回後の強制選択を拒否する。
5. 初期知識はclaimだけを初期化し、取得文書・検索結果・過去エピソードを生成しない。
6. 新フィールドは1.3.0だけで受理する。旧1.0/1.1/1.2の入力・イベント・保存artifact構成は維持。
7. 正準履歴、Scheduler、Reducer、Replayは既存経路を共用。Domain Coreに外部I/Oは追加しない。

新保存形式・イベント族・状態schemaは増やしていない。新定義はschema1.3.0と入力content IDで区別する。
旧入力へ新機能を暗黙付与しない。実G6保存物3種の読込みと安全なG7再投影も再検証した。
新しい可用性helperは固定World解釈に責務を限定し、既存の大きなLoaderへ検索処理やI/Oを持ち込んでいない。

## 評価対象の固定

基準commit: 21b570355304bf89a8b07b82c5470a6564164d35。
manifest.jsonに未コミット・未追跡成果物を含むファイル別SHA-256、Git状態、Python3.14.8、依存一覧、Scenario版、seed0、実行コマンドを固定。
Manifest SHA-256: b26af24463e3d5cce6708454396defb3bb2a57bd429b8f8a0ba4f95f0b1663b6。
出力自身を除外し、実行前plan.jsonを明示的に固定対象へ含めた。target-recheck.jsonで変更なし。
旧VBの証拠745ファイルはhistory-recheck.jsonで変更なし。旧VAと旧VBは上書きしていない。
各runのmanifest/scenarioにsource revision、内容識別値、固定時間・応答条件を保持する。

事前計画: plan.json。コマンド: uv run --locked python -m scripts.vb_contract_acceptance。
既存テストhelperを使わず、同じEngineから3ケース×2条件×独立2プロセス=12runを新規生成した。
PYTHONHASHSEED2/71、別出力先・別一時入力ディレクトリ。意味的seed0、固定時間、乱数消費なし。
全12worker成功、6組で両側全ファイル集合・bytes一致、全runでReplay・保存再取得一致。
pair-audit.jsonで各対の非介入入力とWorkspace digest一致を検査した。

## A/Bの独立実験

A: 同じD01閲覧後、隠れた可用性だけを変えた両条件で同じT03を選び、同じmetadata検索を実行した。
- available: 検索成功→Policy T04→R01へ実移動。
- unavailable: 正当なtool-unavailable観測→Policy T02→D02を実閲覧。
- 操作前の本人観測は一致。単なるイベント列差ではなく、観測後の候補・選択・実操作の分岐を確認。

B: 両条件に、metadataという検索語を構成できるという合成の本人知識QUERY-KNOWNと、T03の知識前提を共通定義した。正解・修正案の知識ではない。
初期保持の有無（契約上2つのmirror配列）だけを変更。
- 保持あり: T03が候補となりPolicyが選択、実検索。
- 保持なし: T03が候補にならずPolicy T02、D02を実閲覧。
- 初期取得文書・検索結果は両条件とも空。候補の実行可能性と、実選択・操作を別々に記録。
これは今回の合成前提の下での反応性であり、PEER-NOTEの追加一般や現実の知識効果を証明しない。

## C: 既存coverageの予備実験

Workspace=B0、全ファイルbytes、クエリmetadata、候補・capability・Policy・時間を固定。
R02のrecorded+target_idとunrecorded（target_idなし）だけを意味的な参照収録介入とした。
- 対照だけが検索結果にR02を含む。
- 実テキスト行ヒットは同じ。
- 本人の検索観測には情報差がある。
- Policyは両条件ともT03→T04。実操作も検索→R01移動で一致。

予備実験の期待結果は満たしたが、行動反応性のPASSではない。現Policyは検索結果の非空性を利用し、R02だけの情報差はこの場面の選択を変えない。
この結果から全coverage介入で行動差が不可能とまでは断定しない。事後に参照・クエリを差し替えて成功例へ作り替えていない。

追加設計の最小候補は、固定Worldに検索対象パス集合とdigestを持たせ、結果を実バイトから計算する検索収録プロファイル。
同じB0・同じクエリで対象情報が索引に入る/入らない条件を表せる。返却値上書きはせず、未収録を不存在としない。
旧版は全Workspace検索、新版の検索対象はWorkspace digest+profile digestで識別し、隠れたprofile digestを本人IDへ混ぜない設計が必要。
今回それは未承認の追加契約として実装せず停止する。代替は関連情報を判断に使う既存参照経路の新しい事前実験だが、優先順位や正解規則の変更は行わない。

## VAへの影響と再検証

影響はLoader・候補前提・Search結果意味論・認識更新。旧VAのPASSは旧固定対象の履歴として保持した。
今回、新出力先va/へ旧VA独立評価器を再実行した（OUTだけ変更し元証拠は不変）。独立2生成、全保存物比較、取消/失効/同tick経路、semantic改変、保存途中失敗、直接公開拒否、出典再ラベル拒否、実G6互換の28ケースが全PASS。
追加の1.3.0にはtests/test_intervention_contract.pyの9試験と新独立12runを対応させた。
隠れた可用性で本人package不変、偽造失敗/偽造成功の拒否、保存とpackage再構成、required_claims欠落・撤回・解釈・確認、管理出典・監査出典・未知/空/不正出典、旧版新フィールド拒否を確認。
したがって今回変更の影響範囲のVA条件は充足と判定する。将来の検索プロファイルや動的障害にまでこの判定を拡張しない。

## VB正式条件に対する判定

| 条件 | 今回の判定 |
|---|---|
| 決定的時間・乱数無効、他入力同一 | PASS |
| ツール条件の最初の観測後分岐 | PASS（A） |
| 初期知識の候補・実行分岐 | PASS（B） |
| 取得情報による関連行動分岐 | NOT EVALUATED（Cは情報差のみ） |
| 再現性・保存/Replay・未観測情報非干渉 | PASS |
| アクセス・AI/同僚一変数対 | 旧証拠を保持、今回新対象での独立受入はNOT EVALUATED |
| 正常・誤判断/撤回・AI未使用・未完了の別デモ | 旧証拠を保持、今回独立デモ再実行はNOT EVALUATED |
| A/Cに依存しない判定 | PASS |
| 追加確率試験・現実妥当性 | OUT OF SCOPE |

必要な全条件は揃っていないためTask7.2を完了にしない。今回のC未分岐を本体不具合として黙って修復していない。

## 品質検査

- 全unittest: 257件、49.871秒、OK、exit0（G7、旧Scenario/実G6、ハーネス故障試験を含む）。
- 新契約試験: 9件、OK、exit0。
- Ruff全体: exit0。
- mypy strict src/tests: 70ファイル、exit0。
- compileall src/tests/新評価器: exit0。
- uv lock --check、OpenSpec strict validation、git diff --check: すべてexit0。
- 新VB評価器: exit2（上記の受入未評価を通知）。新VA評価器: exit0、28ケースPASS。

各log/exitを同ディレクトリに保存。unittest末尾のJSON FAIL行はハーネス故障注入テストが期待どおりFAILを検出した出力で、unittest自体はOKである。
G8・VC・VF、commit/push/deploy/archiveは行っていない。
