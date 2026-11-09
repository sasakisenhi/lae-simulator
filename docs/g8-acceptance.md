# G8 完了判定（2026-11-09）

対象change: build-reproducible-simulation-foundation。対象Tasks: **6.3 / 6.5**。
**最終判定: PASS（選定生成器OpenAI / gpt-6.1-terraと固定されたG8対象の範囲）。**
Geminiの品質をPASSへ読み替えず、以前の失敗・欠測・INCONCLUSIVEを保持する。

## 人間裁定と判定履歴

ユーザーは既存出力の一次評価を問題なしと確認し、OpenAIだけで継続することを指定した。
追加したOpenAI単独11問は、失敗・未完了なしで全件取得できた。
新規read-only Codexセッションの独立意味評価は、26主張中24件をSUPPORTED、2件をUNCERTAINとした。
私的ID漏洩は全26主張CLEAR、Q01/Q06/Q07はNO_UNSUPPORTED_DRIFT、日本語は全11回答5/5。

Q01の確認範囲とQ04の配布前提について、ユーザーが
「2件とも私は問題ない回答だと判断します。」と明示的に裁定した。
human-adjudication.jsonに発言と対象を記録した。
Q01は検索結果における箇所確認、Q04は模擬演習の説明と合わせた不明回答として許容する。
これはレビュー担当による文脈上の裁定理由であり、ユーザーが新しい作業事実を証言したとは扱わない。
独立評価のUNCERTAINは封印原記録に残し、全評価者一致や自動意味検証成功を表示しない。

当時のevaluation.json / verification.json / report.mdに残るINCONCLUSIVEは、
人間裁定前の時点における正しい記録である。今回の最終判定は別成果物へ追記し、上書きしない。
未解決の意味確認として残っていた2点が人間裁定で解決したため、6.3の受入を完了する。
依存6.3/6.4が揃い、既存のCLI縦断・異常系の確認結果と合わせて6.5を完了する。

## 対応する要求・受入条件

| 対象 | 実装・検証・証拠 |
|---|---|
| EP06 / EP08、固定本人情報と根拠 | G7パッケージの保存再取得・Replay一致、当人帰属検査、根拠catalog完全一致、質問文を根拠化しない固定応答試験、OpenAI Q01/Q02と人間裁定 |
| EP09、認識種別・未知・誤認 | 固定誤認・曖昧な固定記憶・推測・不明・記憶なしの反例試験。選定生成器のQ03/Q05/Q08–Q11は根拠不足を創作で埋めず、Q08は誤認が存在したと補作しない |
| EP10、追跡可能な回答監査 | 入力/本人digest、質問、生成器/モデル/設定/プロンプト、応答、usage、診断、検査・公開可否を記録。独立評価・人間裁定も別記録から追跡可能 |
| EP15、監査と公開防止 | 不正ID・私的ID・根拠なし主張等を反例で検査。REJECT/NEEDS_REVIEWは非公開。人間裁定で元の自動監査やpublic.jsonを変更していない |
| EP16、再質問整合性 | 固定応答の矛盾・異topic・異episode・誤認/推測の試験。OpenAI Q01/Q06は同じ検索を述べ、Q07は異なる対象を捏造する要求に応じないと独立評価 |
| WD01 / SE15 / EP02 / EP12、6.5 | #1955の読込み→実行→検査→保存→Replay→証拠取得→固定インタビューをCLIで再確認。CF0維持。不正入力/内部失敗/取得拒否/回答不能の終了区分をテスト |

固定応答試験と実生成器試験は別の証拠である。実生成器のfixtureには固定誤認の実例がないため、
実モデルがあらゆる誤認を正しく語れるとの一般的な性能保証は行わない。
この制約を隠さず、タスクの固定応答による境界検証と選定生成器の限定的確認を合わせた判定とする。

## 実装と変更ファイル

- adapters/interview_config.py / interview_budget.py / interview_remote.py / interview_diagnostics.py:
  設定・承認・予算・SDK境界・安全な診断。429の内訳、再試行不可の課金/利用枠、終了理由・token等を扱う。
- simulation/interview_contract.py / interview.py / interview_validation.py:
  回答契約、固定応答、根拠取得、構造/権限/支持/意味/公開の分離、回答監査・再質問検査。
  日本語要約の部分文字列不一致だけでREJECTせず、意味未確認はNEEDS_REVIEWで保留する。
- interview_evaluation.py / scenario_cli.py / cli.py:
  ローカル評価・監査保存・#1955縦断入口と状態区分。
- scripts/g8_offline_reaudit.py / g8_openai_acceptance.py と関連tests:
  旧17回答の再評価、実験用65秒間隔、無制限再試行や結果上書きをしない試験入口。
- docs/g8-*配下:
  初期実装、送信資料、旧失敗、オフライン修復、独立レビュー、人間裁定を別版で保存。

本最終裁定ターンでは文書とTasksチェックだけを更新し、コード・生成指示は変更していない。
提案したv3の追試は不要とし、未実装・未送信のまま保持する。

## 検証結果

- 全342 unittest PASS。Replay、CF0、G6/G7、#1955 CLI、公開境界、SDKモック・診断反例を含む。
- Ruff全体PASS。mypy strictは87ファイルPASS。compileall PASS。
- OpenSpec strict validation / git diff --check PASS（最終チェック更新後にも実行）。
- ソースと元資料の実行前hash、独立評価の封印hashを最終裁定前に再照合し一致。
- OpenAI実API: 11/11応答・生成完了、構造11/11 PASS、429/途中終了/生成失敗0。
  報告usage基準の推定費用0.052499 USD。実請求額とは区別する。

主な証拠:

- docs/g8-openai-acceptance-20261109/report.md / validation.json / unittest.log
- 同independent-evaluation/sealed-result.json / seal.json / verification.json
- 同human-adjudication.json / final-acceptance.json
- docs/g8-resume-20261109/local-cli-check.json / g8-tests.log
- docs/g8-offline-repair-20261109/report.md / validation.json

## 残存リスク・範囲外

自由文全体の自動意味保証、モデル/SDK/価格の将来変更、quotaの正確な上限は保証しない。
独立評価は新規コンテキストのモデル支援レビューであり、実人間によるブラインド調査や
統計的独立性、実利用者への効果実証ではない。文言の2つの別解釈は残余リスクとして保持する。
実行時のNEEDS_REVIEWは引き続き公開保留され、今回の受入裁定は一般的な自動公開許可ではない。

追加の人間判断事項はG8については解消済み。VC/VF、C11/C12実機検証、経験的妥当性、
commit/push/deploy/archiveは本完了に含めず、自動実行しない。
