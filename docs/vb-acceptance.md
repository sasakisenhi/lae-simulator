# VB 行動反応性受入 B

対象: build-reproducible-simulation-foundation / Task 7.2。
総合判定: **INCONCLUSIVE（未充足の受入証拠あり）**。Task7.2は未完了、進捗20/25を維持する。
VAのPASS、VCやLLMの結果は本判定の前提としていない。

## 固定と事前計画

基準commitは `21b570355304bf89a8b07b82c5470a6564164d35`。
既存の未コミット・未追跡ファイルを保持した。`vb-evidence/target-manifest.json` にファイル別SHA-256、Git状態、Python/依存一覧を保存した。
Manifest SHA-256: `6c77a7ccfae032368826176259fc79d36af2e499f723bce088b20fc4e1904af0`。
評価出力docs/vb-evidenceを除外し、報告書と結果解析器は実行後作成物として分けた。主評価器scripts/vb_acceptance.pyは固定対象である。
実行後target-recheck.jsonのchanged_filesは空。評価条件は事前のplan.jsonから変更していない。
主入力fixtures/g2/scenario-collaboration.json、schema1.2.0、seed0、scheduler canonical-scheduler-1.0、全時間モデル定数、乱数消費なし。
Python3.14.8、アプリ0.1.0、ランタイム外部依存なし、uv.lock固定。
各runのscenario.json、manifest.jsonには個別内容識別値、時間仮定、固定応答版g5-fixed-v1、出典revisionを保持する。
各条件の正確な内容識別値は保存Manifestのdefinition_idを参照する。

実行コマンド:
- `uv run --locked python scripts/vb_acceptance.py`
- `uv run --locked python scripts/vb_compare.py`

既存単体テストのhelperはimportしていない。評価器から共通LocalSession/Policy/Storeを直接呼ぶ。
各条件2回を別プロセス・別一時入力ディレクトリ・別出力先・PYTHONHASHSEED=2/71で実行。
成功32run、入力拒否2件。成功16条件は全保存ファイルとsummaryが繰返しbyte一致し、全runでReplayと保存再取得が一致した。
最初の評価器はPolicy計測でselect_by_policyを二度呼び、重複選択として拒否された。計測を読み取り専用select_local_candidateに直した。
次の試行でツール介入が入力拒否されたため、評価器の停止処理を失敗記録・継続へ変更した。本体・Policy・条件・期待値は変えていない。
これらはpreliminary/および初回ログに残し、最終評価器を再固定して全条件を新規実行し直した。

## 事前定義した介入・期待と実測

差分の全フィールドはcontrasts.json、全候補・本人観測・Policyの選択は各summary.jsonに保存した。

| 要因 | 介入（他条件固定）・事前期待 | 観測・結果 | 判定 |
|---|---|---|---|
| 初期知識 | PEER-NOTEを初期既知claimへ追加。契約上の2つのmirrorを同時更新。本人へ届くが未使用なら選択差を強制しない | 時刻0でclaim差。双方T01。正準履歴はrun_id以外同じ | 情報到達PASS、関連する行動分岐の証拠はNOT EVALUATED |
| 取得情報 | 検索語metadata→存在しない固定語。入力シナリオは同一。ヒットがある時だけT04利用可能 | 時刻2でPolicyはT04→T03。最初のイベント差は9番目のquery。検索結果差から候補差を説明可能 | PASS |
| アクセス | D02 read権限だけ除去。C01 FAIL観測後に別文書へ向かう | 時刻2でT02→T05。T02候補消失。Policyが読み取り専用なのでこの判断自体は正準イベントにならない | 候補・判断分岐PASS、判断後の自律操作実行はNOT EVALUATED |
| ツール機能 | code.search capabilityだけ除去。T03が消え別文書選択を期待 | LoaderがT03のunavailable-operationとして拒否。実行・本人観測へ到達せず | NOT EVALUATED |
| 同僚応答時間 | PEER-ANSWER delay2→45のみ。早期観測対期限切れを期待 | 最初の予約due_tick4→47、最終時刻5→8。早期応答対timeoutで観測が異なる。Policyは双方T03 | 待機・情報到達分岐PASS |
| AI応答時間 | AI-PROPOSAL delay3→45のみ。早期観測後のみT12候補を期待 | 最初の予約due_tick5→47、最終時刻6→10。応答/timeoutとT12候補に差。Policyは双方T03 | 待機・候補分岐PASS |
| 負の対照 | 同時刻・同観測で未観測T15選択イベントを追加 | Policyは双方T01。内部イベント列だけが変わった | PASS |

初期知識は介入不達ではなく、現Policyの判断規則に使われないclaimである。これだけからモデル欠陥とは判定しない。
ツールは能力変更と候補参照の入力整合性制約により介入不達である。候補を削除して結果を作る追加変更は実施していない。
アクセスでは世界の権限制約が本人の利用可能候補へ反映された。正準列に操作差がない点を行動実行の成功と扱わない。
AI/同僚では期限切れと認知可能な応答の差で、同じPolicy選択でも待機分岐は存在する。
本人は未到着の45tick応答の内容を知識として先取りしていない。時間数値は未校正の合成仮定である。

## 別扱いの経路デモ

共通エンジンから以下を生成、各2回の一致とReplayを確認した。
- normal: P1→C01→仮想提出、4tick、SUBMITTED。
- mistake: P3→C02→撤回→P1→C01→仮想提出、7tick、SUBMITTED。
- no-ai: Issue閲覧、AI呼出しなし、1tick、INCOMPLETE。

これらは固定API操作手順による許容経路のデモで、Policyが自律的にP1を発見した証拠ではない。
正常・誤判断と撤回・AI未使用・未完了が共通エンジンで可能という証拠であり、一変数試験の代替ではない。

## 正式受入条件

Task7.2、Tasks VB節、SE19、SE03–13、WD06、EP17、Design D11/D13から抽出した。

| 必須条件 | 判定 | 証拠・不足 |
|---|---|---|
| 決定的主試験（乱数無効、時間/応答定数） | PASS | 全固定シナリオ・保存Manifest、randomness_used=false |
| 知識/取得情報/アクセス/AI/同僚/ツールの一変数対 | NOT EVALUATED | 5要因を実行、ツール介入は入力拒否で未成立 |
| 他入力同一、変更要因に対応する最初の候補・判断・待機分岐 | NOT EVALUATED | information/access/AI/peerは説明可能。knowledgeの関連行動分岐・tool実行は証拠不足 |
| 正常・誤判断/撤回・AI未使用・未完了を共通エンジンから生成 | PASS | 3つの別扱いデモ保存物 |
| デモと一変数試験の分離、A/Cに依存しない判定 | PASS | 本計画・報告・独立評価器 |
| 同条件再現・Replay・保存再取得・隠れ内部変更への不変性 | PASS | repeat-comparison.json、全32run、negative対 |
| 追加確率試験の抽選対応 | OUT OF SCOPE | 実施なし、主試験で乱数なし |

観測された本体要件違反としてのFAILは確定していない。VB総合は証拠不足のINCONCLUSIVEとする。必要な試験を全て満たしたと見せるための本体修復や条件変更は行っていない。
Task7.2はチェックしない。G2〜G6の既存完了を、入力拒否だけを根拠に取り消してはいない。

## 検査・限界・次の判断

全unittest 243件、46.274秒、OK、終了コード0。
Ruff、mypy strict（src/tests）、compileall、uv lock --check、OpenSpec strict validation、git diff --checkのログと終了コードをvb-evidenceに保存した。
主評価器・解析器はRuffとcompileallの対象で、mypy標準対象はsrc/testsである。

今回追加したのは評価スクリプト・計画・保存物・報告のみ。新schema/イベント/CLI入口やDomain CoreのI/Oは追加していない。
依存方向は評価器→既存API。本体コードを変更していない。
評価は同じReducer/Storeを利用する独立実行であり、別実装オラクルやOS権限分離レビューではない。
初期知識を使用する妥当な既存候補条件、およびツール能力を変えても入力契約を満たす事前試験設計が必要。
現在の証拠だけではTask7.2を完了できない。結果に合わせた事後のケース差替えはしない。
実際の開発者への効果・外的妥当性・確率的頑健性は主張しない。
G8の実装依存はG7で、VBのPASSを前提にしていないため、別途指定により進行可能。ただしVB未完了は残る。今回G8・VC・VFへは着手していない。
