# G2 固定シナリオ契約 1.0.0

`fixtures/g2/scenario.json` は、G1で固定した教材から作成した #1955 演習の候補・規則・仮想Patch・modeled Checkを保持する。これは実行結果ではなく、G3以降が利用できる検証済み入力である。`lae-sim validate-scenario fixtures/g2/scenario.json` は外部接続やシミュレーションを行わずに検査する。

## 境界

- `source_manifest` はG1 manifestのsource ID、revision、個別ファイルdigestを再参照する。可動refや別版へ置換しない。
- `world_claims` は実在OSS、架空企業draft、合成仮定を `origin` と `status` で区別する。`context` は `company_context`、`team_profile`、`exercise_scenario` の三層をclaim IDで結ぶ。
- `actor_view` は本人に見える初期claimと候補表示名だけを持つ。管理用期待値、固定候補順、Patchの正解ラベルを含めない。
- `references` の `unrecorded` / `unresolved` はtargetを断定できない。資料が束にあること、本人がアクセスできること、関係が収録済みであることは別契約である。
- `candidates` はT01–T15を順序なしで定義する。利用条件、前提、効果は有限の型付き演算だけを使い、任意スクリプトとIssue固有演算を拒否する。
- `rules` はR-A–R-Gの判断原則であり、候補優先順位やP1へ到達するPolicyではない。T15による有効な未完了を許し、DevEx問題の発生を成功条件にしない。

## PatchとCheck

P1–P4はB0の `server/src/eslint.ts` に対応する限定的なbefore/afterバイト断片を持つ。検証器はG1 readable extractの元バイトdigest、before断片の存在、断片digest、意味状態、影響referenceを照合する。P5は同一バイトを持つ変更なし・追加調査である。

意味状態は有限な教材宣言であり、TypeScript構文、コンパイル、VS Code動作を保証しない。P2のURLなし文書操作副作用、P3の型フィルタ違反、P4の不明型扱い、fresh/existing cache条件を別に記録する。

C01–C12はすべて `mode=modeled` である。C11/C12も実行計画とUNKNOWNの限界を固定しただけで、実機、build、型検査、既存テストを実行した証拠ではない。検証器は未知版、未知述語、`executed`への格上げを拒否する。Check evaluatorやWorkspace適用はG2の範囲外である。

## 固定条件と未決定事項

EX01/EX02は演習目的と仮想提出先を固定する。EX03は一人の仮名参加者、読取り・検索・仮想編集・modeled check・情報質問の範囲を宣言し、相談相手を承認者とは扱わない。EX04はこの入力ではAI無効、時間は合成tick、応答は期限前に保証されないとする。会社全体の個別権限、AI承認、実名の専門家、応答SLAは未決定の会社事実として補完しない。

抽出履歴は手動抽出・レビューを記録する。準備LLMは使用しておらず、実行時LLM、Google Drive、GitHubへの接続は不要である。
