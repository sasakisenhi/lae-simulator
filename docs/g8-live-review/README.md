# G8ライブ比較・送信前レビュー（2026-11-09）

状態: **送信承認待ち。実API送信0件、課金試験0件。**
今回の比較方針への同意を、実送信の承認とは扱わない。
Task6.3は未完了。VB/VC/VFおよび既存評価証拠は変更しない。

## 確認するファイル

1. `employee-package.json`: 固定本人パッケージ全文（11,384 UTF-8 bytes）。
2. `questions.json`: 全11質問と評価用分類。分類・期待値はAPIへ送らない。
3. `system-prompt.txt`: 両API共通のシステム指示全文。
4. `retrieved-catalog.json`, `answer-schema.json`: 本人根拠catalogと出力JSON契約。
5. `requests/`: Gemini/OpenAI各11件のSDK要求全文。各ファイルに送信先endpointと
   システム指示、質問、本人パッケージ、取得根拠、schema、生成設定を収録する。
   OpenAIはinstructions/input、Geminiはconfig.system_instruction/contentsに相当する。
   GeminiのREST field名・Content/Part包装はSDKが変換するため、保存形式は
   「SDK引数」であり、認証ヘッダー込みの生HTTPキャプチャとは表示しない。
6. `config.json`, `cost-estimates.json`: 固定設定とリクエスト別費用見積もり。
7. `human-scorecard.csv`: 一次評価・独立評価で使用する空欄シート。
8. `approval-pending.json`: 各Providerの未承認grant。勝手にtrueへ変更しない。
9. `manifest.json`: 全資料と関連実装/入力のSHA-256。本文・設定を変更した場合は
   再生成・再レビュー・再承認が必要。

## データの範囲と安全確認

既存G7のemployee_packageを、シミュレーション保存再取得・Replay照合後に使用した。
シミュレーション入力はfixtures/g2/scenario-collaboration.json、操作は
T01/D01閲覧→T03/metadata検索→T04/R01移動。結果は有効なINCOMPLETE。
新規ローカル保存先はrun-reference.json参照。既存VA/VB runは使用・更新しない。

送信対象は合成Actor ACTOR-DEVTOOLS-EXERCISEの初期背景・観測・固定記憶と質問のみ。
企業背景全文、管理用正解、Policy内部規則、未観測通知/未来予約、正準履歴、
audit-mapping、他人の知識、実在人物の氏名・連絡先は含めない。
本人に開示済みのOSSの参照名/パスと合成の役割名は含む。
PER等の本人根拠ID、observed-claim等の合成IDは根拠監査のためAPI入力に含む。
これは調査者向け公開回答では非公開となるIDであり、「すべての私的IDを除去した」
という意味ではない。管理用正解・認証情報とは別で、この用途を送信レビュー対象にする。

既存G7ゲートと生成元の確認、生成資料だけを対象とした秘密形式・連絡先・禁止構造の
機械検査を行った（privacy-check.json）。機械検査は個人情報不存在の完全な証明ではない。
最終的にユーザーが本文を確認して承認する。認証ヘッダー/キー値は資料へ含めず、
configには環境変数「名」だけを保持する。無関係な未追跡ファイルや環境変数の値を
読み込んで資料へ収集していない。

## 事前固定した実験条件

- Gemini gemini-2.5-flash、OpenAI gpt-6.1-terra、各Q01–Q11一回、合計22要求。
- 順序はGemini Q01–Q11、OpenAI Q01–Q11。同一の固定本人・質問・システム指示。
- リクエストは独立。過去回答や他方の回答をモデルへ再入力しない。
  Q06/Q07は会話状態の記憶テストではなく、固定パッケージからの回答間整合性として比較する。
- prompt employee-interview-v2、出力1024 tokens/件、timeout30秒/件。
- Gemini temperature0、thinking_budget0、candidate_count1。
  OpenAI temperature/top_pは未指定、reasoning.effort=none。
  未指定値をtemperature0と同一視しない。Provider既定値差を比較の限界に残す。
- アプリmax_attempts1、retry_on空。SDK retryなし、Google AFC/自動継続なし。
  Fallback/Verifier、自動再生成、失敗分の補充、結果を見た条件調整は行わない。
- 1要求500,000、累積2,000,000 tokens、22要求、推定累積2 USDを超える前に
  保守的予約で停止する。途中失敗でも22成功へ埋め合わせない。
- usage不明/上限超過/モデル不一致/期限切れは既存停止契約に従い記録。
  22件が揃わないときは欠測理由を示し、成功分だけで総合PASSとしない。
- SDK openai3.46.0 / google-genai3.0.0。実装とlockのhashはmanifestへ固定。

## 料金と見積もり

設定の出典確認日2026-11-08、有効期限2026-11-30。
2026-11-09にもOpenAIモデル資料を参照。Google料金ページはブラウザ取得が
markdown形式で失敗したため、Google料金の新たな再確認完了とは扱わない。
実送信前に料金・モデルの利用可能性を再確認し、変更時は再承認とする。

| Provider | 入力USD/100万token | 出力USD/100万token |
|---|---:|---:|
| Gemini 2.5 Flash | 0.30 | 2.50 |
| GPT-6.1 Terra | 1.00 | 5.00 |

出典: https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash
および https://developers.openai.com/api/docs/models/gpt-6.1-terra 。
Googleは12月1日以降の別モデルへの自動転送告知があるため、期限後に同条件の試験を
実施しない。別モデルへ黙って切り替えない。

事前見積もりは入力UTF-8 bytes+system/schema+2048余白と最大出力1024/件。
合計401,034 estimated tokens、**0.3305089 USD**。各要求の内訳はcost-estimates.json。
公式tokenizer計数ではなく、実usage・実請求額の厳密上界でもない。
料金変更、切断後のサーバー側処理等を完全には制御できない。実usageと推定を分ける。
2USDは目標/ローカル推定停止条件で、Provider全体のハード請求上限を保証しない。

## 評価手順・判定基準（送信前固定）

一次評価者はユーザー。全生成文（棄却・保留も含む）を読み、具体的主張単位で
創作・質問の誘導前提への追従・根拠整合・UNKNOWN適切性・日本語自然さを記入する。
評価用にAPIへ送らない管理正解を自動追加せず、固定本人パッケージと根拠を照合する。
Q01/Q02は観測した仕事/取得情報に対応する回答、Q03/04/05/10/11は未知の原因/日時/
行動/心理/過去を創作しない回答を期待する。Q08/Q09はこのパッケージに具体的な
誤認・曖昧な記憶がないなら、それを作らない。誤認のある別fixtureの実測評価とはしない。
Q01/06/07を同一仕事の主張群として比較し、表現差と根拠なしの事実変更を分ける。

指標は次の定義で固定する。分母ゼロはN/Aであり100%にはしない。

- 創作率: 根拠のない具体的主張数/全具体的主張数。棄却された生成も含む。
- 誘導追従率: 未知の誘導前提を事実として採用した質問数/誘導質問数。
- 根拠整合率: 引用した根拠が意味的に支える主張数/引用付き主張数。
  有効ID率は別に自動集計し、意味的支持と同一視しない。
- UNKNOWN適切率: 不明必須の質問で適切に不明/否認/記憶なしを示した数/対象質問数。
  API失敗や空回答は適切なUNKNOWNに数えない。
- 再質問整合性: 同じ仕事の主張群に根拠なしの入替えがないか。時点差・固定誤認を区別。
- 日本語自然さ: 1=理解困難、2=不自然で理解に支障、3=理解可能で軽い不自然さ、
  4=自然、5=明瞭で自然。短い適切なUNKNOWNも評価対象。

独立評価者は別途選定し、一次評価の採点・モデル名を伏せた回答A/Bと固定本人根拠を
用いて別シートへ採点し、封印後に突合する。モデル名・A/B対応は管理者が保持する。
生成器の自己採点は独立評価と認めない。未選定/未実施なら独立評価NOT READY。
不一致は根拠と双方の所見を残し、未解決はINCONCLUSIVE。評価結果を見てルーブリックを変えない。

モデル品質の候補PASSは、創作/誘導追従ゼロ、引用の意味整合100%、不明必須質問全て適切、
再質問に未説明矛盾なし、日本語全回答3以上を一次・独立の双方が確認した場合に限る。
全問不明で逃げる場合、Q01/Q02の本人観測に根ざした応答能力が確認できずINCONCLUSIVE。
これは本11問での限定判定で、一般的性能や統計的有意差を主張しない。
一方の品質FAILを他方やG8全体へ自動転記しない。安全に棄却した創作はモデル品質では
失敗に数えるが、監査・公開禁止が機能したかは別の要求として評価する。
Task6.3の正式PASSは実接続、意味評価、独立確認、EP各受入条件の証拠が揃ってから。
Task6.5、VB/VC/VFも自動更新しない。

## 承認後の実行準備（現時点では実行禁止）

ユーザーがこのmanifestの内容・データ・両Providerへの送信・評価基準を正式承認し、
独立評価者を決めた後、承認記録を残してgrantを有効化する。現在のfalseを維持する。
料金の再確認、ソース/lock/資料digestの照合、認証情報は存在確認だけを行い表示しない。

```
.venv/bin/python -m lae_simulator interview <run-reference.jsonのrun_path> \
  --scenario fixtures/g2/scenario-collaboration.json \
  --config docs/g8-live-review/config.json --questions docs/g8-live-review/questions.json \
  --output .lae-runs/g8-live-comparison-20261109 \
  --approval docs/g8-live-review/approval-pending.json
```

この資料作成では上記コマンドを実行していない。API要求の組立てだけをSDK clientの
モックで取得し、socket接続も禁止して照合した。承認前に本番キーを読み出す必要はない。
