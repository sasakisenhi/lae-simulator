# VA 技術的整合性受入 A

対象 change: build-reproducible-simulation-foundation / Task 7.1。判定: **PASS**。
G1〜G7の固定された実装に対する受入であり、G8・VB・VC・VFの判定ではない。

## 評価対象の固定

基準 commit: `21b570355304bf89a8b07b82c5470a6564164d35`。
`va-evidence/target-manifest.json` は既存未コミット差分・未追跡ファイルを含むファイル別SHA-256、Git状態、Python、依存一覧を保持する。
Manifest自体のSHA-256は `56114162e977db0a3febd998f89fe7e69989ea92d3c9acde65a753ebcb9a83e4`。
前回の一時一覧のdigestも同Manifestに保存した。既存差分は `baseline.diff` に保持した。
評価出力 `docs/va-evidence/**` を対象ハッシュから除外することで循環を避けた。
評価スクリプト自身は固定対象に含む。Task完了チェックは評価後の管理変更として区別する。
本体コードは変更していない。実行後に固定一覧との一致を別途確認した。

主入力は `fixtures/g2/scenario-collaboration.json`、契約1.2.0。
検証済内容識別値は `sha256:ec5b181a37b9733d2cb14f3f83290ccfa847405031fbbb08c413791e47dacc4c`。
seed=0、deadline=30 tick、max_same_tick_events=100、scheduler=`canonical-scheduler-1.0`。
乱数方式はlae-keyed-sha256-v1だが本試験では乱数消費なし。
時間モデル・AI固定応答・出典revisionは保存された scenario.json と manifest.json に全値を保持する。
Pythonは3.14.8、アプリ0.1.0、ランタイム外部依存なし（uv.lock固定）。

## 方法と証拠

実行: `uv run --locked python scripts/va_acceptance.py`。
スクリプトは既存テストをimportせず、直接APIから本人の閲覧、同僚要求と取消、反復検索、P2適用、C04 modeled FAIL、INCOMPLETE終了を新規生成する。
別プロセス、別出力先、別TMPDIR、PYTHONHASHSEED=2/71で実施し、`run-a/` と `run-b/` を保存した。
全10ファイル（正準列、初期・最終状態、公開ログ、本人パッケージ、公開証拠、監査対応表、closure、scenario、Manifest）がbyte単位で一致した。比較から除外したフィールドはない。
一時パスや壁時計値は意味内容へ入っていない。各ファイルの保存digestと環境情報も一致した。
`results.json` にケース別期待値・実測値、イベント種別、Queue、Manifest、比較結果を保持し、`execution.log` に実行結果を保存した。
`attempt1-*`、`attempt2-*` は評価ドライバ開発中の試行保存物で、最終判定はrun-a/bとresults.jsonによる。
最初の試行では管理用public_evidenceのHistoryValidationErrorをドライバが捕捉しなかった。SimulationErrorを拒否として扱うよう評価ドライバだけを修正した。本体の修復ではない。

予約については要求取消を含む主経路の全状態（Queue・retired・資源区間を含む）をReplayと比較した。
追加の固定合成入力3つでtick=0の取消、tick=0の失効、tick=1の完了と失効競合を実行した。
前二者は観測なし、同tickでは完了優先で観測ありとなった。全状態・公開投影を含む保存再取得結果が通常実行と一致した。
各入力・全保存物を `control-*` に保持した。管理制御の理由を現実の割込み頻度とは扱わない。

## 故障注入

| ケース | 期待 | 実際 |
|---|---|---|
| 正準イベントcaused_by偽造 | 読込拒否・公開なし | PASS |
| 正準イベント削除・順序交換 | 同上 | 各PASS |
| 最終状態に不正フィールド | 同上 | PASS |
| 公開投影の対象偽造 | 同上 | PASS |
| 本人パッケージ・監査対応表改変 | 同上 | 各PASS |
| Manifest definition_id偽造 | 同上 | PASS |
| 必須closure欠落 | 同上 | PASS |
| 3回目のファイル書込でOSError | 独立internal-error、完成物・一時物なし | PASS |
| 不正履歴をカタログ・本人・公開証拠APIへ直接渡す | 出力拒否 | 各PASS |
| D07取得・未知admin役割 | unavailable/取得拒否 | 各PASS |
| audit-only出典claimをactor-privateへ再ラベル | 本人出力拒否、公開カタログに秘密なし | 各PASS |

イベント・状態・投影・本人・監査の改変ではartifact digestも更新した。単なるdigest検査の成功で意味的改変が通ることはなかった。
壊れた保存物をloadしてから公開取得する経路はloadで停止した。別途、壊れたin-memory runの公開入口も拒否を確認した。

本人パッケージは保存後の正準再構成とbyte一致し、反復観測を維持した。LEV内部IDは含まれなかった。
観測されない選択イベント1件だけを挿入して正準番号を変えても、本人パッケージと公開証拠（識別子を含む）は不変だった。
管理出典を私的既知claimとして偽装する反例は本人入口で拒否された。
旧G6の実保存物cancelled/repeated/submittedを現実装で読込み、現在の公開証拠へ旧LEV IDを出さないことも独立スクリプトで確認した。

## 正式条件の判定

Task 7.1、Tasks VA節、Design D10/D13、SE14–18/20–22、EP01/06/11/17に基づく。前回報告の6項目を以下の判定単位とする。

| 条件 | 判定 | 今回の独立証拠 |
|---|---|---|
| 同一条件の独立2実行で正準列・最終状態・決定的投影一致 | PASS | independent-all-artifacts、run-a/b |
| 予約取消を含むReplay一致 | PASS | replay-state-queue-resources、control 3経路 |
| 状態・派生不一致を検出 | PASS | rehashed final-state/public-log/package/audit改変拒否 |
| 改変・保存障害・不正公開設定で無効公開停止 | PASS | 故障表、直接API拒否、出典再ラベル拒否 |
| 固定本人パッケージと投影の比較 | PASS | 再構成byte一致、内部イベント挿入不変、LEVなし |
| LLM・B/Cに依存しない独立判定 | PASS | テストhelper非依存評価スクリプト、固定応答のみ、B/C結果の参照なし |

評価スクリプトは本体のReducer・検証APIを利用するため、完全に別実装された意味論オラクルではない。独立プロセスと独立した反例生成による受入であり、OS権限を分離した別評価者レビューではない。Cのブラインド評価とは異なる。
既存243テストは補足証拠で、VAの判定は上記実行物・比較・故障注入による。

## 検査と範囲

全unittest: 243件、46.993秒、OK、終了コード0。ログはunittest.log。
Ruff、mypy strict（src/tests 67ファイル）、compileall、uv lock --check、OpenSpec strict validation、git diff --checkは全て終了コード0。各log/exitを同ディレクトリに保存した。
mypyの標準対象はsrc/testsで、評価スクリプトはRuff・compileall・実実行で検証した。

今回の独立28ケースで確認した本体不具合はない。P2/C04のFAILは期待された教材結果で、内部不整合ではない。
全入力・全経路の網羅的証明、実機C11/C12、合成データの現実妥当性、実利用者効果、電源断耐久、第三者署名による真正性はOUT OF SCOPE。
自然言語インタビュー、B/Cの受入、MVP全体完成は未評価。本試験の必須6条件に未評価は残さない。
Task7.1を完了可能と判定する。進捗は20/25となる。G8/VBは個別の指定後に着手可能だが、この報告では実施していない。
