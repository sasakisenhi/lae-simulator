# G8 ライブ評価の原因調査（2026-11-09）

対象はapproved / repeat-1の2回・計44要求。追加API生成要求、設定変更、判定変更は行っていない。
構造化回答を得た17件について、保存した回答を現在の検査器へ再入力し、全判定・検査結果が一致した。
機械的再現結果はdiagnosis-reproduction.json。これは独立意味評価ではない。

## 1. 通信失敗: 429の詳細が失われている

2回合計でGeminiのrate-limitは5件、OpenAIは19件。
interview_remote.pyの_failureはHTTP 429をすべてrate-limitへ変換する。
error.code/type、Retry-After、quota metric、request IDは保存されず、例外本文も破棄される。
したがって既存ログだけではRPM/TPM/日次枠/残高/支出上限を特定できない。
認証失敗、予算ゲート停止、モデル不一致として分類された試行はない。
両モデルとも応答成功例があり、恒常的なキー不正・モデル利用不能という説明は支持されない。

再実行のOpenAIはQ01–Q03で応答、以降8件で429。Geminiも成功と429が混在する。
これは時間枠による制限と整合するが、具体的制限値の証明ではない。
evaluateは待機なしで次の質問を送る。SDK再試行は無効、max_attempts=1。
したがって枠が回復する前に次の要求も失敗し得る。これは固定実験条件どおりの動作。

[OpenAI公式エラー文書](https://developers.openai.com/api/docs/guides/error-codes)も
429には頻度制限のほか残高・支出・使用量上限があると説明する。
残高不足と断定したり、待機だけで解決すると断定したりできない。
Geminiのprovider-unavailable 1件は同じ分類器でHTTP 5xxから生じるが、正確なstatusは未保存。

## 2. 棄却: valueの部分文字列検査と自然言語生成の不整合

棄却9件はすべてsupport FAILを含む。構造化回答17件ではdisclosure/cross_questionのFAILは0件。
interview_validation.pyはstatement.valueが引用した根拠textへcasefold部分文字列一致するかを確認する。
日本語訳・要約・モデルが付けた意味的ラベルは、内容が関連していても英語原文と一致しない。

例: EX01の根拠は英語の「固定Issueを調査する」説明だが、Geminiのvalueは
investigate_fixed_issue_and_specifications。原文にこの識別文字列は存在しないためFAIL。
OpenAIの日本語value「調査後、根拠と限界を示して提出または保留」も同じ理由でFAIL。
有効な引用IDが付いていても採用されない。これはモデル創作の確定証拠ではない。
一方、訳の誤りも存在し得るため、すべての棄却を誤検知とは断定しない。

## 3. 保留: 逐語引用・定型不明以外を自動採用しない設計

保留7件はsemantics/cross_question UNKNOWNによる。
検査器は原文の逐語一致または限定された不明・記憶なし定型文だけをPASSにする。
Gemini Q03の「私には見えなかった管理上の原因についてはわかりません。」は
unknown・根拠なし・valueなしでsupport PASSだが、定型「わかりません。」と異なるため保留。
再実行OpenAI Q03は定型「わかりません。」に一致して採用された。
日本語の自由な言い換えを促す生成指示と、機械検査が採用可能な表現には隔たりがある。
独立意味評価が未実施なので、通信を直すだけではG8の受入完了に届かない。

## 4. 出力未完了: 1024 token上限が有力

Geminiの初回Q09・再実行Q01がincomplete-output。
出力usageは1013 / 1009 tokensで、JSONがフィールド途中で途切れている。
max_output_tokens=1024、複数主張にtext/topic/value/episode/根拠IDを出す形式、
回答の短さ・主張数を制限しない指示が組み合わさっている。
上限到達が有力だが、finish_reasonを保存していないためMAX_TOKENSとは確定できない。
現在のGeminiTransportはSTOP以外を一律incomplete-outputへ変換する。
初回Q09の未完了原文には私的PER識別子を本文へ出す記述もある。
これは生成失敗として非公開であり、構造化回答のdisclosure FAIL 0件から
未完了原文まで漏洩要素なしと解釈してはならない。

## 次に必要な対応（今回未実装）

1. 通信境界で安全な許可リストによる診断情報を保存する。
   HTTP status、既知error code/type、数値Retry-After、finish_reason等を保持し、
   生エラー本文・任意headers・URL・認証情報は記録しない。
   既存記録から失われた詳細は復元できない。
2. ダッシュボードのモデル別RPM/TPM・使用量・課金枠と照合し、次の実験に送信間隔を固定する。
   今回の固定22要求を後付けで再試行成功へ置換しない。
3. 根拠判定のvalue契約を明確化し、日本語要約をFAILにする構造照合と
   意味的に未検証のUNKNOWNを区別する。逐語一致だけで一般的意味整合性を証明しない。
   検査を緩めて今回の回答をPASSに変える修正は行わない。
4. 次の実験では主張数・長さ制限、または出力token枠の見直しを別条件として固定する。
5. 人間の一次評価と独立意味評価を行い、支持・創作・誘導追従を回答単位で確認する。

今回は調査記録だけを追加した。コード、設定、旧証拠、タスクチェックは変更していない。
検証は17件のオフライン判定再現とgit diff --check。新たな機能変更がないため全テスト再実行はしていない。
