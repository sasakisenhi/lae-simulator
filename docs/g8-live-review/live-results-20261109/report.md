# G8 ライブ評価結果（2026-11-09）

判定: **INCONCLUSIVE**。Task 6.3・6.5は未完了。

ユーザーの「外部通信を許可します。」に基づき、固定条件で22要求を一度ずつ試行した。再試行・補充・モデル変更なし。

保存先: `/home/sengakuhisai/dev/lae-simulator/.lae-runs/g8-live-comparison-20261109-approved`。CLI終了コード3 / not-accepted。内部クラッシュとは区別する。

| Provider | 棄却 | 意味確認保留 | 生成失敗 |
|---|---:|---:|---:|
| gemini | 4 | 3 | 4 |
| openai | 0 | 0 | 11 |

Geminiは8件のProvider応答を観測（うち1件はincomplete-output）、3件rate-limit。OpenAIは11件rate-limitで回答を得られなかった。rate-limitの原因は保存された分類だけでは特定できず、残高不足・アカウント上限等とは断定しない。

公開採用回答は0件。棄却・保留は自動検査の結果であり、モデルが創作したとの意味評価を確定するものではない。引用ID有効率と意味的支持は別指標。

Geminiの報告usage: 入力34,652 / 出力3,779 tokens、設定単価による推定$0.0198431。失敗要求のusageは不明。失敗時の保守的予約を含む台帳推定$0.2885761は実請求額ではない。22要求・推定$2上限内で終了。

送信前manifestの全資料・対象source hashを実行後も照合し一致。既存の通信0件runと旧VA/VB証拠は上書きしていない。認証値の出力混入検査も成功。

料金再確認: [OpenAI公式](https://developers.openai.com/api/docs/models/gpt-6.1-terra)、[Google公式](https://ai.google.dev/gemini-api/docs/pricing.md)。固定設定と同額。Google文書はブラウザ取得不可のためurllibで公式本文を取得した。

## 人間が確認するもの

- `answers.md`: 全質問、棄却・保留を含む全生成文、失敗分類、自動検査。管理レビュー用で、調査者への公開回答ではない。
- `human-scorecard.csv`: 一次意味評価用の未記入シート。固定本人根拠は親ディレクトリのemployee-package.json / retrieved-catalog.json。
- `evaluation.json`、Provider別attempts.jsonl: モデル・usage・入力digest・検査の原記録。

一次評価・独立意味評価は未実施。空欄をPASSにせず、独立評価者は未選定。今回の22件では回答欠測があるためモデル間の品質優劣を判定しない。新たな送信は別実験として計画・承認し、今回結果を保持する。

VB/VC/VF、タスクチェック、既存承認前manifestは更新しない。コード・プロンプト・設定は変更していない。
