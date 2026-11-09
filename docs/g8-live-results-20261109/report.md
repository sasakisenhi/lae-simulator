# G8 受入試験実行結果（2026-11-09）

判定: **NOT READY**。ユーザーの外部通信許可を記録して受入用CLIを実行したが、
実行環境のGEMINI_API_KEYとOPENAI_API_KEYが未設定のため送信前に停止した。
CLI終了コードは4（not-ready）。生成回答はなく、意味評価は実施できていない。

| Provider / model | 質問試行記録 | API要求 | 原因 | 判定 |
|---|---:|---:|---|---|
| gemini / gemini-2.5-flash | 11 | 0 | missing-credentials | NOT READY |
| openai / gpt-6.1-terra | 11 | 0 | missing-credentials | NOT READY |

## 確認していただくもの

- [evaluation.json](evaluation.json): Provider別11問の結果、API使用量0、予約要求0、NOT READY判定。
- [Gemini試行監査](provider-1/attempts.jsonl) / [OpenAI試行監査](provider-2/attempts.jsonl): 全22問のmissing-credentials。回答欄は空。
- [固定本人情報](../g8-live-review/employee-package.json)と[質問11問](../g8-live-review/questions.json): 次回の送信・回答評価の基準。
- [一次評価シート](../g8-live-review/human-scorecard.csv): 今回は生成なしのため採点しない。空欄を保持。
- [承認記録](approval.json): 今回のユーザー指示に基づく送信許可。元の承認待ち資料は保持。

## 実行前・実行後の確認

送信前manifestの全files/source_hashesをSHA-256で照合し、相違0件。
元の資料・設定・コードを変更していない。
Google公式料金ページはurllibによる取得で再確認でき、Gemini 2.5 Flash標準テキスト
入力0.30 USD/100万token・出力2.50 USD/100万tokenを確認。
OpenAI公式モデルページでもTerraの入力1.00 USD・出力5.00 USDを再確認。
料金取得はドキュメント読取りであり、認証済みAPIの利用可能性検査ではない。
出典: https://ai.google.dev/gemini-api/docs/pricing および
https://developers.openai.com/api/docs/models/gpt-6.1-terra 。

今回の実行では課金API要求0件、API reported token 0、ローカル推定API費用0 USD。
請求明細の照合は未実施。監査22件すべて送信前のmissing-credentialsであり、
空回答・失敗を適切なUNKNOWNや品質PASSに数えていない。
public.jsonに生成回答がないことも確認した。

## 残る作業

認証情報をこのCLIから参照できる環境変数へ設定後、新しいevaluation出力先と
その出力先に束縛したgrantを作り、同じ固定条件で実行する。今回の証拠は上書きしない。
APIキーをチャットや評価資料へ記載する必要はない。今回の送信許可は維持する。
生成後、ユーザーの一次意味評価と、別評価者によるモデル名を伏せた独立評価が必要。
一次・独立評価者の採点をエージェントの自己評価で代替しない。
Task6.3/6.5は未完了を維持。VB/VC/VF、commit/push/deploy/archiveは実施していない。
全体テスト・Ruff・mypy・OpenSpec strictは本試行では再実行していない。
コード変更はなく、本試行の検証対象は承認・CLI失敗分類・監査・公開停止である。
