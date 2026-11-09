# G8 OpenAI単独・追加試験

ユーザーは既存出力の一次評価を問題なしと確認し、OpenAIだけでの継続を指定した。
primary-confirmation.jsonに発言と解釈を記録した。独立評価との相違は過去記録へ保持し、
ユーザーの確認を詳細な数値採点や将来の生成文の承認へ置換しない。

## 実行前固定条件

- 対象はgpt-6.1-terraのみ。固定本人情報・Q01–Q11・employee-interview-v2・JSON schemaは旧試験と同じ。
- 出力上限1024、reasoning effort none、timeout30秒、store false、SDK retryなし。
- 11要求を順に各1回、要求開始間隔を65秒以上に固定する。失敗分を補充しない。
- 最大要求数11、1件500,000 / 合計2,000,000 tokens、ローカル推定停止上限2 USD。
- Geminiは呼ばない。モデル比較の優劣はこの試験の目的ではない。
- 過去回答はAPIへ渡さない。Q01/Q06/Q07は固定本人情報に対する回答間整合性として照合する。
- 元のG8ルーブリックを継承する。欠測を適切なUNKNOWNと数えず、意味未確認は公開保留。
  構造成功だけでTask6.3をPASSにしない。

## 費用と送信資料

2026-11-09にOpenAI公式pricingページとモデル資料を再確認した。
Standardの入力1.00 / 出力5.00 USD per million tokensで、全11要求の保守的予約推定は
**0.245573 USD**。実usageと請求額は別であり、2 USDはProvider全体のハード上限ではない。

- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models/gpt-6.1-terra

requests/Q01–Q11.jsonはendpointとSDK引数全文。認証headersやAPIキー値は収録しない。
固定資料と生成指示は変更していない。新しい生成器や結果上書きは追加していない。

## 試験ドライバーと保存

scripts/g8_openai_acceptance.pyは通常のevaluateを使い、OpenAITransportの構築だけを
PacedOpenAITransportへ差し替える。各送信は元のOpenAITransport.requestを必ず呼ぶ。
差は送信間隔と管理用pacing記録だけで、結果・入力・トークン枠を変更しない。
間隔制御の単体テストで引数不変・待機・再試行なしを確認した。
Domain Coreや正準保存schemaには変更を加えていない。

通常の承認・予算・診断・公開ゲートを通す。既知の課金/残高/利用枠エラーは
再試行しない。結果を見た条件変更や成功例への差替えはしない。
新保存先はprotocol.jsonのevaluation_output。旧ライブ試験、独立評価、修復証拠は保持する。

結果取得後に、API成功・生成完了・構造・意味・公開を分けて評価する。
新しい回答は新たな意味評価の対象で、以前の一次承認を流用してPASSにしない。
VB/VC/VF、commit/push/deploy/archiveは対象外。
