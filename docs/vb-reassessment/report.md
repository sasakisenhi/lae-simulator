# VB 評価ハーネス修復・再評価

対象: build-reproducible-simulation-foundation / Task7.2。進捗20/25、未チェックを維持。
総合受入は **INCONCLUSIVE**。新ハーネスの機械判定は **NOT EVALUATED / exit 2**（必須条件3件の未評価を含む）。
本体仕様を変更しなければ閉じられないモデル上の選択が残るため、当該実装には進まない。

## 評価対象・履歴保持

基準commit `21b570355304bf89a8b07b82c5470a6564164d35` と既存未コミット・未追跡成果物を含む。
最終実行の固定一覧はrun-3/manifest.json。SHA-256は `30e4cdefad1b31b6d810004ed53fa05921ecf302ea154361ab025b3c20bcedd9`。
コード・入力ファイル別SHA-256、Git状態、seed0、Python、依存一覧、schema1.2.0、scheduler canonical-scheduler-1.0、固定応答版g5-fixed-v1を記録。
各runのscenario.json、manifest.jsonに内容識別値・モデル全値・source revisionも保存する。
新評価出力は固定一覧から除外、事前計画plan.jsonは明示的に含め、循環を避けた。終了時の固定対象再照合PASS。

旧docs/vb-evidence、docs/vb-acceptance.mdは変更していない。元の2スクリプトもhistory/へbyte単位で退避した。
history-recheck.jsonで旧証拠一覧に対するdigest一致を確認した。旧32run・入力拒否2件・旧計画・INCONCLUSIVE判定は維持する。
新結果を旧試験のPASSとして扱わない。run-1/2はハーネス検証の試行、最終判定対象はrun-3。
計画は実行前にplan.jsonへ保存。期待候補・操作数・失敗基準・未成立条件を結果観測前に固定した。
試行後の変更は対照条件比較の明示的集計、壊れたsummaryの拒否、型検査修正であり、条件・期待結果は変更していない。

## ハーネス修復

scripts/vb_acceptance.pyを修復した。
- 全workerの終了コード・標準出力・標準エラー・候補列をresults.jsonへ集計する。
- replay_equalとstored_equalは厳密なboolean Trueを必須とする。欠落・False・型不一致をFAIL。
- 両ディレクトリの相対ファイル集合と全内容digestを比較。片側追加・欠落・内容差をFAIL。
- 出力rootは新規作成のみ。既存summaryによるスキップを廃止し、既存rootを再使用すると失敗する。
- 固定Manifestを実行前に作り、終了後に再照合する。
- worker失敗、期待候補不一致、再現比較失敗、対照比較失敗はFAIL/exit1。未評価ありはNOT EVALUATED/exit2。全必須検証PASSのみexit0。
- 対照条件のシナリオを比較し、宣言した権限1件の差以外がないことを機械検査する。

自動故障テストtests/test_vb_harness.pyは5件。False Replay、False stored、必須値欠落、worker exit7、片側追加ファイル、内容改変、既存summary付きrootの再使用、空判定列を拒否する。
workerが同じ偽summaryを2回返してファイル比較だけなら一致する場合でも、Replay Falseにより総合FAIL/exit1となることを確認した。
これらは意図的な故障を検出してテストが成功するもので、VBをPASSにする試験ではない。

## 既存契約の調査・未充足

### ツール

world/scenario.pyの_validate_candidatesは全候補のoperationをparticipant capabilitiesの部分集合として要求する。
local_policy.pyのtool.searchはcode.search capabilityの有無そのものを返す。独立した実行時のツール可用性入力はない。
同じ候補集合のままcode.searchだけを除去するペアは入力不正になる。候補T03も除去すれば受理できる可能性はあるが、候補集合も変わるため今回の単一要因の成功とはしない。
対応タスク: 2.2（候補・入力契約）、2.4（ツール操作）、設計D3/D4/D11、SE19。
選択肢: (a) capabilityと別のruntime tool availabilityを設計する、(b) capabilityと候補の整合的変更を一つの意味的介入として扱う契約を承認する。
双方とも今回勝手に採用しない。必須ツール試験NOT EVALUATED。

### 初期知識

旧PEER-NOTE追加に対応するPolicy判断条件はなかった。select_local_candidateは取得文書の有無、検索結果、チェックFAIL、Workspace版と候補を使うが、claim内容を直接参照しない。
local_loader.pyではrequired_claims=()を固定している。現候補のknowledge.locationsは検索結果から生じ、初期claimの追加では初期化されない。
knowledge.countは存在するが、現T09は未対応work.compareかつadmin.expected条件を持ち、本人候補として利用できない。
既存の取得済文書・検索結果・チェック履歴を初期知識だけから注入する入力契約も見つからなかった。
対応タスク: 2.5（認識・Policy）、必要なら2.2（知識前提の入力契約）、D3/D4/D11。
選択肢: (a) 型付きの初期認識状態を設計する、(b) 知識前提を候補へ結び、Policyが本人知識で選択できる設計を承認する。
今回Policyの選好や候補を追加して差を作らない。初期知識の必須行動分岐はNOT EVALUATED。

### 取得情報

検索は固定Workspaceの実テキストを同じクエリで決定的に検索する。版・内容・クエリを固定したまま結果だけを差し替える入力/adapterはない。
旧metadata対不一致語の実験は「検索クエリへの反応性」に分類する。純粋な取得情報差を証明したと扱わない。
必要なら情報提供adapter/検索収録範囲の介入契約を別途設計するか、異なる観測機会を情報介入と認める範囲を上流で明確化する。今回の純粋情報介入はNOT EVALUATED。

これらは入力検査を緩める局所修正で解決するものではなく、受入で必要な反応性と現モデルの接続不足である。本体の実質的変更は停止した。既存G2/G3の全機能が壊れているとの断定やチェック取消はしていない。

## 自律選択から操作までの再評価

計画通り3ケース×対照/介入×独立2回=12runを新規生成した。
同条件の別プロセスはPYTHONHASHSEED2/71、別出力先、別一時入力ディレクトリ。意味的seedは両方0、乱数を使用せず時間は定数。
全12workerがexit0、Replay・保存再取得True、6組の全ファイル集合とbytes一致。

| ケース | 事前期待 | 実際 |
|---|---|---|
| autonomous | T01→T03→T04 | Issue閲覧→metadata検索→検索結果の参照移動を完了、PASS |
| access | C01 FAIL観測後、対照T02×2／D02権限除去T05×2 | Policy選択した文書を2操作ずつ閲覧完了、PASS |
| negative | 未観測T15選択を挿入してもT02×2 | 同時刻・同観測・同じ候補選択と操作、PASS |

accessの準備Issue閲覧・C01実行は固定手順で、自律操作として数えない。以降の候補はEngine.select_by_policyが選び、selection_event_idからcompleted_event_idへ追跡する。
パラメータは事前の固定マッピングで束縛する（T01→D01、T02→D02、T05→D04、T03→metadata、T04→観測済検索結果の先頭）。スクリプトは候補を選ばない。
有限2/3操作窓であり、PolicyがIssue全体を自律解決・提出したとは主張しない。全12runの業務結果は有効なINCOMPLETE。
各summaryには操作前本人観測、候補、選択イベントID、完了イベントID、操作種別、tickを保存。正準列は同じrunのevents.jsonlへ保存した。
差が出た根拠はD02権限除去→T02候補消失→既存Policyの文書優先→T05選択→D04閲覧である。
負の対照では内部番号は変わっても、本人観測・候補・実行操作は一致した。単なる履歴差を反応性の成功とはしていない。

## 正式条件判定

Task7.2、SE19、D11/D13、VB節に対する現在の証拠を判定する。

| 条件 | 判定 |
|---|---|
| 主試験の乱数無効・時間定数・固定条件 | PASS（新12run） |
| 初期知識の一変数対と関連する行動分岐 | NOT EVALUATED（契約上の不足） |
| 取得情報の一変数対 | NOT EVALUATED（旧試験はquery差） |
| アクセス一変数・最初の候補/判断/実操作分岐 | PASS（新access対） |
| AI・同僚応答の一変数待機分岐 | 旧VBの成立証拠を保持。今回再実行はNOT EVALUATED |
| ツール一変数対 | NOT EVALUATED（契約上の不足） |
| 再現・Replay・保存再取得・隠れ内部変化の負の対照 | PASS（新12run） |
| 3経路デモを共通エンジン生成、一変数試験と分離 | 旧VB証拠を保持。今回再実行はNOT EVALUATED |
| A/Cに依存しない判定・新事前登録 | PASS |
| 追加確率試験の抽選対応 | OUT OF SCOPE（確率試験なし） |

新計画の実施ケースにFAILはない。旧ハーネスが不一致を正常終了扱いできた評価基盤の欠陥は今回修復し、故障テストでFAIL/exit1を確認した。
必須条件を満たしていないためTask7.2を完了にしない。行動差から現実の開発者への効果や外的妥当性を推論しない。

## 品質検査

各コマンドのlog/exitをこのディレクトリへ保存。
`uv run --locked python -m unittest discover -s tests -v`、Ruff全体、mypy strict src/tests、compileall、uv lock --check、OpenSpec change strict validation、git diff --checkを実施した。
全unittestは248件、47.103秒、OK、終了コード0。Ruff、mypy strict（68ファイル）、compileall、lock、OpenSpec strict、diff-checkも終了コード0。本体srcへの変更はない。
G8・VC・VF、commit/push/deploy/archiveは未実施。今後必要なのは上記モデル境界に関する設計判断である。
