# VB 行動反応性の再受入（Scenario 1.4.0）

2026-11-09。対象change: `build-reproducible-simulation-foundation` / Task 7.2。
最終判定は **PASS**。新C（`VB-C-search-profile-1`）も独立に **PASS**。
対象は今回固定した決定的合成モデルの反応性であり、VA・VCの合格、ライブLLM、実利用者の評価を前提にしない。
旧VBのINCONCLUSIVE、coverage予備実験、失敗試行は過去の判定として保持する。

## 実行前固定と再現

最終試験は `run-2/`。事前登録は承認済みDesign D14で、同節の新C部分を
`run-2/preregistered-design.json`へ全文・digest付きで固定した。
実行前に新Cと補助試験の入力全値、ファイル別hash、Policyを含む本体・評価器・テスト、
依存lock、Python/platform/依存一覧、検索規則版・有効範囲digest・Workspace digestを
`run-2/manifest.json`へ保存した。arm名はexercise_idや本人情報へ埋め込まない。
評価器・専用テストの実ファイルも `run-2/evaluator.py` / `evaluator-tests.py`へ保存した。

- 基準commit: `c33813662a3146639f939b69831f49d88442731c` と既存未コミット成果物。
- manifest SHA-256: `45d8b7a37be8a9fa99d2e600f4f6fd34afce5b5682d4a777b97f4f2f03f16117`。
- Python 3.14.8、Scenario 1.4.0、意味的seed0、既存の定数時間モデルと固定応答規則。
- 実行: `uv run --locked python -m scripts.vb_search_profile_acceptance --plan docs/vb-search-profile-plan-v2.json --output docs/vb-search-profile-evidence/run-2`（exit0）。
- 各条件を別プロセス・別一時入力・別保存先、PYTHONHASHSEED=2/71で2回ずつ生成。
- 新C 8run、補助一変数対20run、別デモ6runの計34runがexit0。全runでReplay・保存再取得が厳密にTrue。
- 17条件すべてで、両側の全artifact集合・全bytes一致。片側の追加・欠落を見落とす比較ではない。
- 7対の入力監査で宣言した一要因以外は一致。新Cの全Workspaceパス・実バイト・digestも一致。
- 実行後のtarget/input/plan/事前登録文/評価器snapshot/旧VA・VB・G9証拠の再照合はPASS。
- C1とN0も独立生成し、case/armという管理ラベル以外のsummaryと本人・公開bytesが一致。

評価器はproductionの `LocalSession` / `select_by_policy` / Reducer / Storeを呼び、
既存単体テストの実行helperをimportしない。権限分離した別レビュアーや別エンジン実装による証明とは主張しない。

## 新C: 取得情報から関連する操作完了まで

全armで共通準備としてT01でD01を閲覧した。この準備は自律選択の証拠へ数えない。
以降2回の選択は既存 `select_by_policy` に任せ、パラメータだけを事前の共通規則で束縛した。
T03は現在版の`metadata`検索、T04は観測済み検索結果の先頭への移動である。

| arm | 固定検索対象 | 初回取得情報 | Policy選択と完了操作 | 終了 |
|---|---|---|---|---|
| C0 | is.ts | 空 | T03検索 → T03再検索 | tick3、有効INCOMPLETE |
| C1 | is.ts + eslint.ts | 21行ヒット + R01/R02/R06 | T03検索 → T04でR01へ移動 | tick2、有効INCOMPLETE |
| N0 | C1と同じ | C1と同じ | T03検索 → T04でR01へ移動 | tick2、有効INCOMPLETE |
| N1 | N0 + README.md | N0と同じ | N0と同じ | tick2、有効INCOMPLETE |

表のパスはすべてserver/src配下（README.mdを除く）。正確な完全パス・入力は各inputsを参照。
独立に計算した固定バイト・検証済み参照範囲のオラクルと、各検索結果の完全一致を確認した。
結果配列・正解参照をエンジンへ入力せず、入力差はsearch_profile.pathsだけである。

最初の本人観測差は初回Search完了時点（tick2）にある。それ以前の全正準prefixで、
検索の予約・消費境界も含め同時刻のActorObservationが一致した。
本人packageと公開bytesは初期・共通準備後・検索選択後・検索開始後の同じ合法prefixを
別コピーで閉じて比較し、一致を確認した。live試験は変更していない。
主試験の異なる最終時刻のpackageを検索前比較へ使っていない。

Search完了後の結果・版・本人観測・claim状態と根拠・候補一覧を各summaryへ保存した。
C0ではT04が候補に入らず、C1ではT04が利用可能になる。その下流でT03/T04選択と
再検索/R01移動が実際に完了した。selection_event_idから開始・予約・消費・完了の
IDとcaused_byを機械検査しており、候補差や選択だけを実行成功とはしていない。

N0/N1は取得情報、本人認識、候補、選択、操作、本人packageと公開bytesが一致した。
入力content IDと管理用profile digestの差を、本人観測や最初の行動分岐として数えていない。
主試験のtick3対tick2は、選択された再検索と移動の既存コスト差であり、時間入力への介入ではない。
有限2選択の試験であり、Issue全体の自律解決や提出を証明しない。

## 他の必須対と別デモ

補助対は旧承認計画の介入・操作窓をScenario 1.4.0で再実行した。新Cの8runとは分離する。

| 要因 | 一変数介入と確認結果 | 判定 |
|---|---|---|
| 初期知識 | 両側に同じ合成QUERY-KNOWNとT03の知識前提を置き、初期保持のmirror配列だけ変更。保持ありT03検索／なしT02でD02閲覧を完了 | PASS |
| ツール | capability・候補を共通にし、検索実可用性だけ変更。双方T03を選択、成功後T04移動／tool-unavailable観測後T02でD02閲覧を完了 | PASS |
| アクセス | D01閲覧・C01 modeled FAILの共通準備後、D02/read許可だけ除去。T02でD02閲覧×2／T05でD04閲覧×2を完了 | PASS |
| 同僚応答 | PEER-ANSWER delay2→45だけ変更。実応答確認と待機終了tick5／timeout通知確認と待機終了tick8。未到着の実応答を先取りしない | PASS |
| AI応答 | AI-PROPOSAL delay3→45だけ変更。実応答確認とT12候補ありtick6／timeout通知確認とT12なしtick10 | PASS |

応答対の依頼・待機開始は共通の固定準備である。SE19が認める最初の待機・情報到達・候補分岐を
実際の応答/期限切れ/通知確認/待機終了イベントへ追跡した。Policyによる自律依頼・統合まで実施したとは主張しない。
初期知識の前提は演習用の合成仮定で、LAEや実開発者の知識効果ではない。

別デモは同じエンジンへの固定API操作で生成し、一変数対と自律Policyの証拠へ流用しない。

- normal: D01閲覧 → P1 → C01 modeled PASS → 仮想提出、tick4、SUBMITTED。
- mistake: D01閲覧 → P3 → C02 modeled FAIL → 撤回 → P1 → C01 modeled PASS → 仮想提出、tick7、SUBMITTED。
- no-ai: D01閲覧、AI依頼なし、tick1、有効INCOMPLETE。

## 初回FAILと評価器の訂正

`run-1`は全34worker・反復・入力監査・新Cを成功させたが、応答補助対の評価器検査で
**FAIL / exit1**となった。この結果・ログ・入力・生成物・manifestは変更せず保持した。
初回評価器と専用テストもhistoryへ保存し、run-1 manifestのhashとの完全一致を確認した。

評価器が期限切れを`status=expired`、遅い側にはRESPONSE_OBSERVEDがないと誤って検査していた。
既存契約では実際には`status=timedout` / `disposition=timeout`となり、期限切れ通知の確認も
RESPONSE_OBSERVEDで記録する。これは実際の応答内容が到着したことを意味しない。

検査を既存の型・イベント意味へ訂正した。遅い側のresponse/response_tick/response_event_idが
すべてNone、timeout通知確認と待機終了が実在することを要求し、偽の遅延応答や未確認通知を
拒否する故障テストを追加した。productionの入力・Policy・候補・遷移規則は変更していない。

元の計画は保持し、補助対の通知解釈だけをplan-v2へ明示した。run-2で新Cの事前登録文digest、
17条件の全入力bytes・scope情報がrun-1と一致することを機械確認した。
検索語・パス・遅延・時間・seed・操作窓・新Cの予測を事後変更していない。
run-2の再固定・全再実行により、訂正後評価器の成功を記録した。run-1のFAILをPASSへ書き換えない。

## 要求対応・品質検査・境界

- SE19、D11/D13/D14、Task7.2: 知識・取得情報・アクセス・AI/同僚応答・ツールの一変数監査と関連する最初の分岐、操作/待機完了、別3経路デモ。
- SE03/05、EP04/06/11/14: 新Cの検索前非干渉性、同結果の負対照、本人・公開bytes一致。
- SE14–18/20–22: 独立反復、現在版検索結果、Replay・保存再取得、完全artifact比較、worker障害のFAIL化。
- EP17: 新Cと他必須対を個別判定し、VA/VCを前提にせず新VBを集約。

`validation-final/results.json`と各logへコマンド・終了コード・log digestを保存した。
全unittestは**328件、64.089秒、OK/exit0**。
uv sync --locked、uv lock --check、Ruff全体、mypy strict src/tests（84ファイル）、
compileall src/testsおよび新評価器、OpenSpec change strict validation、git diff --checkもすべてexit0。
評価器の故障テストは入力の非宣言変更、消費/完了因果の欠落・候補不一致、空trace、
timeoutへの偽応答混入・未確認を拒否する。既存ハーネスのworker終了・偽Replay・保存・片側artifact検査も成功した。
unittest末尾のJSON FAIL行は期待どおりの故障検出出力で、テスト自体の失敗ではない。

G9では先行して更新snapshot（324テスト）と修正前snapshot履歴を固定済み。
今回追加した評価器テストはVBの固定対象であり、G9の過去snapshotへ遡って混入させていない。
新規追加は評価器・専用テスト・事前計画・証拠・報告と完了追跡のみである。
依存方向は評価器から既存APIで、新依存・Domain Coreの外部I/O・保存schema/イベント族・製品CLIは追加していない。
Task7.2はこの新対象の必要証拠に基づき完了とする。旧判定を消さず、MVP全体の完成とはしない。

実測情報、実OSSのexecutedチェック、実利用者の効果、確率的頑健性は対象外。
本試験のmodeled PASSを実コンパイルや業務上の正しさとは扱わない。
G8・VC・VF、外部サービスへの送信・公開、commit/push/deploy/archiveは実施していない。
新たな人間判断事項はないが、MVP全体の完成には残るG8・VC・VFの条件充足が必要である。

## 完了記録時の範囲外変更

最終照合時、別作業によるG8関連変更を検出した。`adapters/interview_remote.py`、
`simulation/interview.py`、`simulation/interview_validation.py`の更新時刻は12:33以降で、
本試験の終了・target再照合（12:30:40）、全328テストの終了（12:31:16）より後である。
`adapters/interview_diagnostics.py`も本試験の固定一覧にない追加ファイルとして検出した。
さらに`tests/test_interview.py`と`tests/test_interview_remote.py`の範囲外更新、`tests/test_g8_offline_repair.py`の追加も検出した。これらを本セッションから変更・破棄していない。

したがってPASSと全体品質検査はrun-2 manifestの固定対象についての判定であり、
後から変更された作業ツリー全体の再受入とはしない。完了記録の3文書以外で、
VB/G9のエンジン・評価器・関連テスト・入力・旧証拠が不変であることを
`completion-recheck.json`へ別途記録する。G8側の変更の検証・完了承認は対象外である。
