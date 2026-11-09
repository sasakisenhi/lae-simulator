# G8 オフライン修復（2026-11-09）

対象change: build-reproducible-simulation-foundation、Task 6.3と関連する6.5。
**修復後もTask 6.3の正式受入はINCONCLUSIVE。6.3・6.5の完了チェックは変更しない。**
本作業ではAPI送信・課金・VB/VC/VF実施・commit/push/deploy/archiveを行っていない。

## 件数の母集団と重複

診断の母集団はapproved / repeat-1という異なる2評価runの44要求。
Providerごと22要求、各質問Q01–Q11を各runで1回ずつ送った。
旧ライブ評価の文書コピーは重複加算しない。通信0件の元runには22件の
事前失敗記録があるが、送信試行の母集団に入れない。
保存済みのレビュー資料・評価コピー・元runをevidence-inventory.jsonで識別し、
作業前後で87ファイルのhashが不変であることを確認した。

| 集計段階 | Gemini / gemini-2.5-flash | OpenAI / gpt-6.1-terra | 合計 |
|---|---:|---:|---:|
| 送信試行 | 22 | 22 | 44 |
| API応答取得（未完了応答も含む） | 16 | 3 | 19 |
| 生成完了 | 14 | 3 | 17 |
| 構造検証PASS | 14 | 3 | 17 |
| 新意味検証PASS（限定定型回答） | 0 | 1 | 1 |
| 新意味検証NEEDS_REVIEW | 14 | 2 | 16 |
| 公開可能 | 0 | 1 | 1 |

44 = 通信失敗25 + API応答取得19。
25 = 429分類24（Gemini 5 / OpenAI 19）+ 5xx相当1（Gemini）。
19 = 出力未完了2（Gemini）+ 構造化回答17。
17 = 旧REJECT 9 + 旧保留7 + 旧ACCEPT 1。
したがって429の24件と出力未完了2件と構造化回答17件は互いに排他的であり、
残る5xx相当1件を足すと44件。棄却9・保留7は17回答の内数である。

質問別・run別・Provider別・モデル別の送信/API応答/生成完了/構造/
根拠ID/開示境界/意味/再質問/公開可否は
`reaudit-final/question-stages.csv`に全44行で固定した。
構造・意味検証に到達していない27件はNOT_RUNであり、意味FAILでも適切なUNKNOWNでもない。
ここでAPI応答取得とはSDKが生成レスポンスを返したこと。
旧エラーの正確なHTTP status、Retry-After、終了理由、推論token数は未保存であり、補完しない。

## エラー分類と終了診断

新しいadapters/interview_diagnostics.pyへ純粋な分類・許可リスト処理を分離した。
APIアクセスは従来どおりinterview_remote.pyに置き、Domain Coreへ通信を追加しない。
インストール済みSDKを確認し、Google APIErrorのJSONはdetails属性から取得する。

- HTTP status、既知error code/type、Provider、モデル、数値Retry-After、
  形式検査済みrequest IDだけを保存する。生エラー本文・任意headers・URLは保存しない。
  request IDは管理監査用であり、調査者の回答へ公開しない。
- 既知の残高/課金/利用枠エラーはquota-or-billingで再試行不可。
  同じ生成器の後続質問も送信せず、既存のローカル予算ゲートも維持する。
- 原因不明の429とGeminiの汎用RESOURCE_EXHAUSTEDはrate-limit-unknownで再試行不可。
  旧24件を新しい原因コードへ事後分類し直すことはしない。
- 既知の一時制限はretry_onへ明示されている場合だけ、最大max_attempts（上限3）まで。
  Retry-Afterを待機下限とし、10秒を超える指定なら早期再送せず終了する。
  既存ライブ設定のmax_attempts=1 / retry_on空は変更していない。
- SDK応答から終了理由/応答状態、出力token、推論token、設定token上限を保存する。
  SDKが提供しない値はnull。STOP/completed以外の未完了応答は、JSONが構文上有効でも
  正常回答として採用しない。ライブ出力上限1024は維持した。増額の見積もりや変更は今回対象外。

秘密を含む例外本文、認証headers、任意診断フィールド、偽request ID、
秘密文字列のfailure codeを使う反例を検査した。診断値は監査境界で再検査する。
raw_outputは合成回答の管理監査として従来どおり保持するが、現在のAPIキー値を伏せる。
任意の第三者個人情報を完全に自動識別する仕組みを追加したという意味ではない。

## 回答監査

検査器はinterview-checks-v3、監査行はinterview-audit-3。
新監査にdecisionとstagesを追加した。構造、本人の根拠カタログ内のID、根拠の付与、
開示境界、意味対応、再質問整合性、公開可否を別々に記録する。
既存CLIとの互換のため小文字statusはaccepted/rejected/inconclusiveを維持し、
decisionのACCEPT/REJECT/NEEDS_REVIEWがそれぞれ対応する。

valueが英語根拠に部分文字列として存在することを支持の必要条件から外した。
有効IDがある翻訳・要約はNEEDS_REVIEWとし、意味的に正しいとは認定せず公開を保留する。
根拠IDなしの具体的主張、無効ID、私的IDの本文出力、誤認の事実への昇格、
明確な同一エピソードの具体的主張矛盾はREJECTにする。
値ラベルや翻訳表現の違いだけで再質問矛盾とは断定しない。
引き続き質問文を根拠には使わず、誤認/推測/UNKNOWN/記憶なしを保持する。
支持があるように見える自由文や、UNKNOWNと称して具体的事実を加えた文は
意味を機械確認できなければNEEDS_REVIEWで非公開。自動的な意味保証はしない。

## 17回答の新旧比較

| 旧判定 | 件数 | 新ACCEPT | 新REJECT | 新NEEDS_REVIEW |
|---|---:|---:|---:|---:|
| REJECT | 9 | 0 | 0 | 9 |
| 保留 | 7 | 0 | 0 | 7 |
| ACCEPT | 1 | 1 | 0 | 0 |
| 合計 | 17 | 1 | 0 | 16 |

全17件で保存時の旧判定と旧checksを凍結した旧検査器で再現し、その後新検査器を適用した。
採用済み履歴だけを各検査器へ渡し、他Provider/runとは履歴を共有しない。
`reaudit-final/reaudited-answers.json`に各回答の旧/new checksと変更理由を保持する。
新規採用は0件。新REJECT 0件は17回答に限定した結果で、不正回答を受理する意味ではない。
反例テストでは明確な不正をREJECTし、NEEDS_REVIEW/REJECTを公開しないことを確認する。
再評価スクリプトはsocket接続を禁止し、新規出力の既存ファイル上書きも拒否する。
最終の段階別集計はreaudit-final配下。直前の集計も作業証拠として残している。

## 要求・受入と検証

Task 6.3はEP06/08/09の本人入力・認識種別、EP10の追跡、EP15の公開禁止、
EP16の再質問整合性を要求する。通信分類や構造の成功だけでは自然言語の意味検証を満たさない。
今回は選定モデルの自由文の独立意味評価が未完了なので正式受入INCONCLUSIVEを維持する。
依存する6.5も完了にしない。本修復で完了にしたタスクは0件。
開始時のOpenSpec進捗は23/28、終了時は24/28（7.2が別途完了状態になっている）。
本作業はtasks.mdを編集しておらず、別途の7.2判定を本修復の成果や根拠には使わない。

検査結果はvalidation.jsonとunittest-final.logを参照。
検査器・診断のテスト、CF0/#1955/Replay/保存/公開境界を含む全unittest、
Ruff全体、mypy strict、構文検査、OpenSpec strict、diff-checkを実施した。
全340テスト成功、Ruff成功、mypy strictは86ファイル成功。ログ末尾のFAIL JSONは
既存harnessの負のテストが出す期待出力であり、unittestの失敗ではない。
形式検査は意味的な受入の代替ではない。

責務レビュー: 新診断モジュールは標準ライブラリだけに依存し、SDK境界から一方向に呼ぶ。
回答検査は純粋な固定本人情報の処理、再評価はapplication側スクリプトに置く。
新しい正準イベント・World/schema族・保存artifactは追加せず、旧runを再保存しない。
本セッションでの自己レビューであり、独立意味評価・独立コードレビューではない。
残るリスクは自由文の意味判定、モデルが生成するtopic/valueの正規化、未知エラーコードの
分類保留、形式に合わず保存しないrequest ID。実環境のquota根因は旧ログからは特定不能。
