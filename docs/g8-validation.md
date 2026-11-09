# G8 実装・検証記録（2026-11-08）

対象changeは`build-reproducible-simulation-foundation`、schemaはspec-driven。
開始時の基準commitは`dc53444`。最新のタスク数は20/28完了で、従来の20/25から
Scenario 1.4.0の追加3件（2.6/2.7/6.6）が未完了として増えていた。
今回の範囲は6.3/6.5だけ。既存の未コミット仕様改訂・skills・インタビュー下書きを保持して作業した。
6.3/6.5の完了チェックは付けていない。

## 実装と受入の区別

| 対象 | 実装・オフライン検証 | 受入 |
|---|---|---|
| FixedResponseGenerator | 決定的応答、UNKNOWN、棄却/不能を維持 | 自動試験用。実モデル接続の代替ではない |
| GeminiInterviewGenerator | 公式SDK/JSON Schema、使用量/障害/停止をモック検証 | NOT READY（ライブ未実施） |
| OpenAIInterviewGenerator | Responses/strict JSON Schema、使用量/障害/停止をモック検証 | NOT READY（ライブ未実施） |
| Phase 1/2 | 単独実行・同一入力での独立比較、両Provider承認、共通予算 | 実測の品質比較は未実施 |
| Phase 3 | Fallback/Generator-Verifierは未実装・設定拒否 | 運用方式の選択は実測後 |
| 6.3 | アダプター/根拠/5検査/監査/公開分離を実装 | NOT READY。自由文の意味評価はINCONCLUSIVE |
| 6.5 | #1955の実行→保存→Replay→証拠取得→質問をCLIで検証、CF0維持 | NOT READY（依存6.3未充足） |

APIキー、承認trueのライブ用grant、実Actor情報の外部送信、課金API呼出しはない。
公式文書とパッケージレジストリの読取りは行った。
commit/push/deploy/archive、VB/VC/VFの受入更新は行っていない。
既存VA/VB報告・証拠、G6保存fixture、CF0は`git diff --exit-code`で変更なしを確認した。

## 検証結果

| 検査 | 結果・証拠 |
|---|---|
| uv sync --locked | 成功。`g8-evidence/sync.log` |
| uv lock --check | 成功。`g8-evidence/lock.log` |
| unittest全件 | 306件成功。`g8-evidence/unittest.log` |
| Ruff 0.17.4 全体 | 成功。`g8-evidence/ruff.log` |
| mypy 2.4.1 --strict src tests | 81ファイル成功。`g8-evidence/mypy.log` |
| compileall src tests | 成功。`g8-evidence/compileall.log` |
| OpenSpec strict | 成功（形式検査）。`g8-evidence/openspec.log` |
| git diff --check | 成功。`g8-evidence/diff.log` |
| 新モジュールimport依存検査 | 循環なし。`g8-evidence/dependencies.json` |
| 独立2プロセスによるVA再実行 | 28/28 PASS。`g8-evidence/va-results.json` |
| 実API接続/実モデル意味評価 | 未実施。NOT READY/INCONCLUSIVEを維持 |

VAは既存`scripts/va_acceptance.py`のOUTだけを新しい一時ディレクトリへ変更し、
同じ検査器で独立実行/Replay/保存再取得/再ハッシュした改変/失敗注入/G7遮断/
G6旧保存互換を再確認した。既存VA証拠は上書きしていない。
これは既存Scenario対象の回帰確認であり、未実装Scenario 1.4.0の新VAやTask6.6ではない。
VB総合は既存INCONCLUSIVE、VC/VFは未着手のまま。

新規・拡張テストの対応:

- 正当な根拠、通常/誘導/新事実、未知の原因、固定誤認、曖昧な固定記憶、明示推測、
  UNKNOWN/記憶なし、空回答、言い換えの不整合、無効ID、私的ID、偽のepisode。
- 引用を含む自由文に新事実が付加されてもPASSにしない。unknownラベルだけでも通さない。
- 棄却を最初の記憶へ固定しない。公開履歴に棄却文を入れず、試行監査に残す。
- 同じ観測に複数項目が含まれる時、項目不明/異topicを誤って矛盾FAILにしない。
- 不正JSON/型/未知フィールド/重複キー、認証不足、SDK不足、401/403/429/5xx、
  タイムアウト・再試行、拒否/不完全応答、モデル差替え、価格失効、usage欠落。
- 回数/1件token/累積token/費用上限、送信前・送信後の台帳保存失敗、秘密を含む例外の遮断。
- Provider別かつ評価run別の承認、retrieved混入拒否、オフラインとライブ証拠の区別。
- 同じ固定本人/質問を両モデルに渡し、回答・履歴を共有せず、共通予算を超えない。
- CLIからの固定実行、保存物の改変/他Actor/非公開取得の拒否、CF0回帰、
  インタビュー前後のシミュレーション全artifact不変、0700/0600、sidecar上書き拒否。

全体Ruffでは開始時から存在した`test_async_collaboration.py`の3違反も検出した。
import順・重複import・使わない代入だけを修正し、テストの操作とassertは維持した。
全体unittestログ中の二つの`status:FAIL` JSONは、既存VB harnessの失敗報告経路を
assertする負の試験による標準出力であり、unittest失敗やVB新判定ではない。

## 独立レビュー

ユーザーが依頼した追加テストの独立レビューを別エージェントで実施した。
親と同じ権限を継承するためOSレベルのread-only隔離を保証するセッションではないが、
レビュアーは編集せず、外部送信・実API呼出しなしでコード/テストを確認した。
VCのブラインド評価や生成器の意味監査を代替するものではない。

初回・再レビューの所見と対応:

1. 逐語引用が矛盾フラグを上書きする: episodeと引用の対応を検査し、矛盾FAILを優先。
2. 共有根拠だけで異項目を矛盾とする: topic欠落/異topicは項目同一性UNKNOWNへ。
3. claim等の私的aliasの引用漏洩: 固定パッケージから構造的にIDを収集して検査。
4. 別評価runへの承認再利用、任意retrieved追加: evaluation_id束縛とcatalog完全一致。
5. 送信前予約をライブ証拠とする: sdk/injected、Provider応答の有無を分離しNOT READYを保持。
6. 送信後台帳保存障害で回答/usageを失う: 取得済み応答とusageを失敗監査へ保持。
7. 拒否・SDK障害・上記境界の試験不足: 実SDKはモックし、対応する回帰試験を追加。

最終レビューで既報所見の解消と新たな重大所見なしを確認した。
最新のインタビュー36テスト、CLI9テスト、4種類の設定読込みが確認された。
SDKのautomatic_continuation停止とstore=Falseの対応もインストール実装から確認した。

## 責務・要求との対応と残る判断

アダプター設定・通信・料金はadapters、JSON/主張検査はsimulation/interview系、
CLI/永続sidecar/比較集計はapplication側に置いた。新しいschema/保存形式/CLI入口の
責務に従って分離し、既存world/loaderやEngineへの外部I/O追加、Issue固有分岐はない。
新モジュールのimportは下位の純粋な契約・検査へ向かい、循環を追加していない。

EP06/08/09: G7本人入力だけ、質問を根拠化せず、不明/誤認を維持。
EP10: 入力/根拠/モデル/設定/プロンプト/検査器/実SDK版/応答/usage/失敗の追跡。
EP15: 棄却・保留の公開停止を、試行記録の保存と別に検査。
EP16: 採用履歴と固定根拠を比較し、棄却で本人記憶や世界を変更しない。
WD01/SE15/EP02/12: 既存runの読込み/実行/保存/Replayと役割別取得をCLIへ接続。
テストPASSはこれら限定動作の証拠で、実モデルの要件充足を意味しない。

残余リスクは自由文の意味・質問適合性・時点や主張項目の正規化・日本語品質、
実接続/実usage・実請求の違い、将来の価格/モデル/SDK変更。
予算制御は一回の評価runの保守的推定で、アカウント請求の厳密上限ではない。
これらは`g8-interviews.md`と`evaluation.json`で未検証・人間評価対象として明示する。

次の人間判断は送信する固定データ・質問・各Provider/モデル・費用上限の確認と
限定ライブ評価の明示承認。その後に独立した意味評価を行い、6.3、依存する6.5の順で
受入判定する。比較前にFallback/VerifierやVB/VC/VFを自動で進めない。
