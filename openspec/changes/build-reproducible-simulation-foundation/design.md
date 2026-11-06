# Design

## Context

目的と範囲はproposal.mdを参照。改訂前のリポジトリは計画成果物のみで、実装・テスト・生成データ・正式LAE資料はない。既存3 capabilityを維持し、その未反映のADDED要件を改訂する。以下のWD/SE/EP番号は各specのRequirement名先頭にある安定IDであり、旧要件との対応はMigration Planに示す。

前回Exploreでは指定SHA、Gitツリーと取得バイト列のblob一致、設定と処理関係を確認した。取得証拠は会話にあり、教材ファイルとしては未保存。3経路は紙上追跡であり、シード付きエンジンの生成結果・実機の不具合再現・修正検証ではない。本改訂でその状態を昇格させない。

## Goals / Non-Goals

**Goals:** 一件のIssueで固定入力、行動選択、状態遷移、非同期時間、仮想Workspace、記録・本人経験・インタビュー、追加証拠取得を縦断する。技術整合性、反応性、第三者による調査可能性を別に検証する。

**Non-Goals:** 全社の12週間実行、レビュー・マージ、実IDE・ビルド、自由なコード生成、全面的なTS解析、高度な心理モデル、汎用プラグイン基盤、介入効果算出、認証サービス。通常は一人の開発者と模擬AI・相談先で足り、複数AIは同じタスク管理を拡張して試す。

## Decisions

### D1. 教材と汎用処理をローカルの論理境界で分ける

対応: world-definition/WD01, WD02, WD12、simulation-execution/SE14。

| コンポーネント | 責務 | 引き受けないこと |
|---|---|---|
| Preparation / Loader | 取得・出典確認、候補構造化、定義検査、スナップショット固定 | 実行途中のLLMによる教材追加 |
| Policy | 本人情報・予測から候補を選択し、根拠を記録 | 正解ラベル・管理原因の参照 |
| Transition Engine | 操作前提・環境作用・版・資源を更新 | Issue専用のif分岐 |
| Scheduler | 時刻、非同期完了、依存、割り込みの管理 | 実時間のsleepや実ネットワーク応答 |
| Check Evaluator | 教材定義の限定述語を版付き状態へ適用 | 実ツールの正しさ認定 |
| Projector / Interview | 記録・本人経験・記憶、許可コンテキスト、回答・根拠検査 | 正準履歴の変更 |
| Validator / Run Store | 整合性・公開境界検査、固定結果保存、役割別取得 | 障害の自動修復、旧履歴の書換え |

単一端末上のモジュール境界とする。言語、SimPy等、物理保存形式は未選定。独自キューでも既存DESライブラリでもD5の決定性を満たす必要がある。既存のPython/JSON案は未実装なので採用済み契約と扱わない。実装入口Task 1.2で選び、固定環境を記録する。WebサービスやDBを先に置く代替は、MVPで必要な調査能力を増やさず運用範囲を広げるため選ばない。

```text
OSS + issue + documents --> Preparation / Loader --> frozen scenario
                                                        |
                          actor view --> Policy --> Transition Engine
                              ^                         |       |
                              +-------------------------+   Scheduler
                                                        |
                                           canonical events + state
                                                        |
                                  +---------------------+----------------+
                                  v                                      v
                         records / retrieval                  employee package
                                  |                                      |
                                  |                                Interview
                                  +---------------------+----------------+
                                                        |
                                            role-scoped investigation
```

### D2. 教材を完全SHAと有限の参照範囲で固定する

対応: world-definition/WD03, WD05, WD07, WD11, WD12。

基準B0:
- Repository: https://github.com/microsoft/vscode-eslint
- Issue本文: https://github.com/microsoft/vscode-eslint/issues/1955
- Commit: `790646388696511b2665a4d119bf0fb713dd990d`
- Commit日時: 2024-06-17T08:55:59Z、親: `4b202340da986fec4f926e72312508e20b2140f0`
- Tree: `227194d87976be6f62cf1ce5e5c0f4ce9f5de819`
- Explore取得時の `refs/heads/release/3.0.10` はB0と一致。今後の固定根拠は可動refでなくB0と内容識別値。
- Issue本文作成: 2024-11-26T23:12:55Z。翌日の[コメント](https://github.com/microsoft/vscode-eslint/issues/1955#issuecomment-2503124072)は開始時非公開の監査資料とする。演習の公開カットオフは本文取得直後・翌日コメント前に置く。コード時点と資料公開時点を別項目として扱う。

#### 取得する教材と既確認識別値

以下はB0のGit blob ID。Task 1.1で再取得・バイト照合し、出典、ライセンス、取得方法、結果、SHA-256をmanifestへ保存する。取得不能なら別refへ置換しない。

| パス | Git blob ID |
|---|---|
| server/src/eslint.ts | b355b6b332307577b175ea3ba78f999c6e0d096f |
| server/src/eslintServer.ts | 2f2719efcf3af8992b5af4e071785015b515e78d |
| package.json | 93efd44a8478538c16b7e9f8ff3129e4257bb63f |
| README.md | 94875302f7441a36c2e9e4aa69221311b6b60c06 |
| server/package.json | 355e5661de8bc4a420f4ee81879b2dfd7197accb |
| package-lock.json | 09c46484ca4eadc4dce7f035bcf107d21b8339b1 |
| License.txt | dcdd1210b29d59ae4e456eb1bec0fcde2eec8f6a |
| $shared/settings.ts | 4679c71b6d39488998d65fcd2158305bef52a804 |
| server/src/shared | fbd7093c1049453929cfa5adaa88ab6abd186e12 |

補助の `server/src/is.ts` も取得する。既確認SHA-256は `caa10fb82231adbdc92c93e506b42ab5e1c3f453aa274e329a6cd6b0368f143f`。sharedはGit mode 120000で内容が `../../$shared/`。通常ファイルとシンボリックリンクを区別し、安全に教材内の実体へ解決する。リンク先を文字列置換して架空のファイルを作らない。

外部資料E0:
- ESLint v8.57.0のコミット `abea3b6f399fde9e28cf6dc5d6c013938f163cdc`
- [Custom Rules](https://github.com/eslint/eslint/blob/abea3b6f399fde9e28cf6dc5d6c013938f163cdc/docs/src/extend/custom-rules.md): type、custom ruleでdocs任意、fixable。
- [Node.js API](https://github.com/eslint/eslint/blob/abea3b6f399fde9e28cf6dc5d6c013938f163cdc/docs/src/integrate/nodejs-api.md): fixTypes、getRulesMetaForResults。
- 外部資料自身のライセンスも収録する。B0のlockfileは開発依存ESLint 8.57.0だが、拡張はWorkspace等のESLintを読む。E0は教材用APIプロファイルであり報告者の実環境の復元ではない。

外部ルール例H0:
- `Stuk/eslint-plugin-header@63f18ce725edb23a2d274b234df7f12ff0b7f009`、package版3.1.1。
- [lib/rules/header.js](https://github.com/Stuk/eslint-plugin-header/blob/63f18ce725edb23a2d274b234df7f12ff0b7f009/lib/rules/header.js#L121)のtype=layout、fixable=whitespace、docs.urlなしを確認。
- index.js、package.json、ライセンスをともに固定。報告者のインストール版と一致するとは未確認。

Issue本文は原因候補に言及しているため、原文利用時の本人にもその手掛かりを渡す。技術的不具合がある既知Issueを選ぶことと、IDE改善・Human Inbox等のDevEx上の必要性を保証することを区別する。原因手掛かりを削除する教材加工は本MVPで行わない。

#### 最小参照モデル

Referenceは `id, source_id, path, revision, symbol, span, relation, target_id, evidence, verification, coverage`。verificationは手動確認・自動抽出・推定を区別し、coverageは収録済み・未収録・未解決。行番号だけでなく内容識別値と抜粋境界を持つ。以下はExploreで手動確認した種。

| ID | B0の位置 | 関係 |
|---|---|---|
| R01 | eslint.ts:121–126 | docs.urlとtypeは別の任意要素 |
| R02 | eslint.ts:143–165 | captureはAPI結果を取得し、URLが文字列の場合だけmap保存 |
| R03 | eslint.ts:174–175 | getUrlがmapからURL取得 |
| R04 | eslint.ts:178–179 | getTypeがmapから型取得 |
| R05 | eslint.ts:182–183 | hasRuleIdは登録有無 |
| R06 | eslint.ts:1188–1239 | validateの型集合→lint→capture→getType→record |
| R07 | eslint.ts:712–746 | CodeActionsのURI別保存とrecord |
| R08 | eslint.ts:389以降、412–422 | Fixes/getScopedが診断と記録を対応 |
| R09 | eslintServer.ts:582–643 | 記録取得と単一修正操作生成 |
| R10 | eslintServer.ts:692–700、823–827 | 文書操作表示は登録有無、実行はURL有無 |
| R11 | eslintServer.ts:748–804 | 一括修正の既存記録利用／fix=true再lint分岐 |
| R12 | eslint.ts:1113–1156 | withClass/newClassがoptionsを外部クラスへ渡す |
| R13 | is.ts:16–17 | 文字列判定は非空・有効URL検証とは別 |
| R14 | header.js@H0:121–125 | URLなし・layout型・fixableの実例 |

Documentは `id, source_id, version, content_digest, claims, related_refs, published_at, audience, availability`。D01=Issue本文、D02=README@B0、D03=package設定、D04=Custom Rules@E0、D05=Node API@E0、D06=header@H0、D07=後日コメント。D07は監査のみ。公開時点・権限・アクセス条件は別軸。

MVPの検索は固定コーパスの実テキスト検索、移動はこの有限の検証済み参照表で実装する。LSP・ESLintの解析・動的依存全体は境界外。未収録関係はUNKNOWN。設定・メタデータ・lint結果は固定入力の境界値として受け、外部プラグインを実行した証拠とは扱わない。

### D3. 候補カタログをLLMの出力から検証・固定する

対応: world-definition/WD08, WD09, WD12、simulation-execution/SE03, SE04, SE06。

物理形式を問わない入力契約:
- Scenario: schema_version、exercise_id、source_manifest、Issue、references/documents、actors、tools、policies、candidates、patches、checks、time_models、response_models、timeline、disclosure/retention。
- Candidate: id、goal、actor_visible_label、required_information、availability条件、operation、target_refs、operation_preconditions、expected_information、on_success、on_failure、knowledge_effects、next_goal_options、duration_model、evidence_refs。
- LLM抽出履歴: 入力版、モデル・設定、生成出力、検証者・検証結果。LLM生成そのものの再現は保証せず、検証済み出力を固定する。
- 前提・効果は、型付きの有限な演算（比較、集合、参照、状態更新、タスク生成等）で表す。任意スクリプトの実行やIssue IDによる分岐は行わない。未対応の演算はLoaderが拒否する。

expected_informationや管理用の正しさラベルをPolicyへそのまま渡さない。本人が知る候補名・既知対象・本人の予想と、結果を計算する教材規則を分離する。検索語・移動対象はIssueや既知情報、検索結果から得る。未知の正解シンボルを直接指定しない。

| 候補 | 操作・目的 | 主な根拠／前提 | 成功・不成功と次候補 |
|---|---|---|---|
| T01 | IssueRead、依頼理解 | D01閲覧可 | 現象A・原因候補T→T02/T03 |
| T02 | DocumentRead、設定確認 | D02/D03 | 設定A、仕様未確定→T04/T05 |
| T03 | CodeSearch、所在探索 | 固定版と検索ツール | 一致箇所A／該当なし→T04/別検索 |
| T04 | FileOpen/SymbolNavigate、定義・利用元追跡 | 発見済み対象、R01–R13 | 関係の取得・解釈／未収録→T05/T09 |
| T05 | DocumentRead、外部仕様確認 | D04/D05アクセス可 | 仕様A、解釈T/C／UNAVAILABLE→T07/T15 |
| T06 | 外部ルール閲覧 | D06 | 形状A、報告環境同一性は不明→T04 |
| T07 | QuestionSend、同僚相談 | 既知の相手・質問内容 | 非同期質問／不能→T13/T15 |
| T08 | AITaskDelegate、調査・案の委任 | 本人の利用方針、入力、権限 | タスク生成→独立作業/T13 |
| T09 | 方針比較・選択 | 本人が取得した根拠 | 選択・棄却・保留→T10/T05/T15 |
| T10 | PatchApply/Revert | 対象・版・編集権限・前提 | 新版／拒否・競合→T11/T04 |
| T11 | CheckExecute | 対応モデルとWorkspace版 | modeled判定取得→T09/T04/T14 |
| T12 | AIResultIntegrate | 完了成果と基準版 | 統合／競合→T11/T13 |
| T13 | Wait/Interrupt/Resume | 依存・残作業 | 新情報到着で候補再評価 |
| T14 | PullRequestCreate | 本人による提出判断と差分説明 | 仮想PR、終了 |
| T15 | Defer/Cancel | 未解決事項等 | 未完了・中止、終了 |

R-A: 未確認事項に対応する利用可能な調査を選ぶ。R-B: 暫定的に有効と考え、既知の禁止条件に反しない変更は試せる。R-C: 反例を得れば仮説を撤回・修正し候補を再評価。R-D: 委任方針と範囲を満たせば委任・承認判断。R-E: 応答待ちでも独立作業があれば進める。R-F: 必要情報不足かつ代替作業なしなら待機・保留。R-G: 提出条件と本人の確認方針を満たせば提出し、未解決で期限なら未完了。

選択は固定優先度と知識・状況条件を基礎とする。複数候補の同順位だけ、設定でシード付き重み選択を許す。実行可能判定は存在・版・権限・資源の検査であり、問題解決への有効性を判定しない。重みは一般的な本人方針と状況から得て、P1等の正解タグから与えない。常時最適化、LLMのオンライン選択、厳密なSMDPやペトリネットは今回は導入しない。

### D4. 最小状態と知識更新を明示する

対応: simulation-execution/SE03–SE06, SE09, SE11。

状態 S=(t,W,K,G,U,J,Q,N,L,Z):
- W: 不変の教材基準版、仮想Workspace版、文書・参照表の有効範囲。
- K: 本人ごとのclaim、内容、未知/取得/暫定/本人確認、根拠、認識時刻、撤回先。
- G: 現在目標、未解決事項、本人の予想、提出方針、依存関係。
- U: active_application、semantic_view、開いたファイル・資料、検索語と結果、利用可能コマンド。
- J: 人間・AI・相談タスクの状態、残作業、入出力版、依存、資源、応答予定。
- Q: DESキュー。実際の未来完了時刻は本人向けビューへ渡さない。
- N: 通知の生成・到着・認知・閲覧・対応状態。
- L: 追記専用イベントと各状態変化・因果参照。
- Z: 実行状態、業務終了理由、内部有効性、未解決依存。

F(S,a)は前提検査、開始イベント、時間経過、完了時の版再検査と効果適用、知覚・候補更新を行う。原則は完了時に効果を適用し、中断時には未完了の効果を適用しない。操作開始時と完了時の参照版を残す。本人が誤った対象を選ぶことは許容し、存在しない対象を開いた成功ログは作らない。

「確認済み」は本人が確認手続きを踏んだ状態であり、管理者の真実との一致ではない。資料を開いた直後は取得にとどめ、読み取ったclaim、解釈規則、反例や利用元確認を別の更新として残す。撤回は過去のKを消さず新しい認識へ接続する。誤認の生成には曖昧な情報・不十分な検証等の教材上の根拠が必要で、ランダムな無根拠エピソードは生成しない。

### D5. DES・時間・非同期タスクを一つの論理時計で管理する

対応: world-definition/WD04, WD10、simulation-execution/SE02, SE07–SE10, SE13, SE14。

内部時間は入力が宣言する整数tick。時間単位はmanifestに固定し、紙上例の1tick=1分を実測値と扱わない。実行窓は[0,H]。同時刻順序は、10=作業完了、20=応答・外部作用、30=通知配送、40=本人の判断機会、90=期限判定、同分類内は安定投入連番とする。小さい分類を同時刻へ遡って投入せず、必要なら次tickへ進める。H時点の許可された完了を処理してから期限を判定する。1回の判断機会につき最大1操作を開始し、無限のゼロ時間判断ループはINVALIDとして検出する。

能動作業は人間1資源につき1件。AIはタスクごとの資源・設定容量で独立に進行でき、依存を満たさなければ着手しない。ApprovalRequiredは許可外作業の前提で発生し、情報不足ならQuestionRequired。必要情報・許可・応答規則のないイベントを見栄えのため挿入しない。同僚は質問に含まれる情報と固定知識から応答を構成し、応答不能・期限後応答も許す。実行時にライブLLMへ問い合わせない。

通知到着だけで内容をKへ追加しない。確認方針は作業区切り・通知優先度・本人の予測等から決め、通知の存在認知、内容閲覧、応答を区別する。回答後は該当依存だけを解除する。中断は完了イベントを取り消しまたは失効させ、残作業・版・目標を保存。再開時に再確認が必要なら通常の閲覧・探索として計上する。資料取得不能や無応答時は独立作業へ移り、なければ待機または保留する。H後の未処理イベントは一覧に残し、その内容を本人の過去の経験へ入れない。

DurationModelは `id, unit, variables, formula_or_distribution, parameters, provenance_class, source, uncertainty, scope`。操作所要時間と、資料理解・予想待ち時間は別。利用する知識・対象の既知性・作業規模等を入力変数にできる。初期の数値は全て合成仮定。文献から値を導入する場合も適用条件と不確実性を再確認し、一律の「画面切替1回で何分損失」は採用しない。

集計は区間の和集合から経過・能動・純待機を求め、AI並列区間を人間待機へ加算しない。ApplicationFocusedは画面切替、goal/task変更は文脈切替、再開の読み直しは再開作業として分類する。同じ読み直しと抽象再開係数を二重請求しない。パラメータ感度は別入力として再実行する。

### D6. 仮想Workspaceは実バイト差分と検査可能な意味状態を併用する

対応: simulation-execution/SE06, SE11、world-definition/WD12。

不変なB0にoverlayを適用する。Patchは `id, base_digest, file, symbol_or_span, before_digest, replacement, author, semantic_delta, affected_refs` を持ち、適用前後の内容を保存する。任意LLMコード生成は不要。Task 2.2で具体的な限定差分を教材として準備・レビューする。「P1が付いた」というフラグだけの変更にはしない。

Semantic deltaは変更箇所との対応を人手検証する教材データ。内容識別値と一致する有限の版だけにチェックモデルを結びつける。任意の未知パッチはUNKNOWN。全TS構文を解析しない代わりに、メタデータ保存条件・型フィルタ・文書操作条件等の限定意味状態をバイト差分に結びつける。この抽象化の一致は教材検証の責任でありコンパイル保証ではない。

適用時にbeforeと権限を検査し、失敗なら無変更。撤回も履歴に残る新版。AIはタスク基準版から別overlayを出し、人間側へ統合するときに競合判定する。自動マージ・自由な競合解消は要求せず、競合なら保留または新基準版で再実行する。編集で影響する参照表は無効化し、教材にある検証済み新版参照へ切替えられる場合だけ復活させる。

#### #1955の仮想変更候補

| ID | 対象・意図 | 影響・必要な知識 |
|---|---|---|
| P1 | R02でURLと独立して有効なmetaを保存し、R10の文書操作提示を取得可能な非空URLで判定 | 型フィルタを保つ。保存と文書利用が別という根拠が必要 |
| P2 | R02の保存条件だけ緩和 | getTypeは改善し得るが、hasRuleIdでURLなし文書操作を提示し得る |
| P3 | R06の型制限を迂回してrecord | 実行可能だが明示フィルタの互換性を破る |
| P4 | R06で不明型を許可扱い | 情報欠落を許可とみなす根拠がない。反例・UNKNOWNの対象 |
| P5 | 変更なしで追加調査 | 仕様不明や情報不足で正当な選択 |

P1も実機検証済み修正ではない。captureは既登録IDを上書きしないため、fresh cacheの主ケースと既存キャッシュの回帰条件を分ける。特殊なunused-disable-directiveの登録・clearを維持する。診断表示の抑制条件とrecord呼出しは別なので、表示されないことだけでrecordなしとはしない。

### D7. チェックは変更IDでなく版と限定述語を評価する

対応: simulation-execution/SE12, SE16、evidence-projection/EP11。

Checkは `id, input_cases, subject_version, coverage, predicates, expected_property, evidence_refs, mode, limitations`。Evaluatorは、対応する意味状態に対してmap登録、型取得、修正記録、文書操作提示等を計算する。結果はPASS/FAIL/UNKNOWN。実行失敗・不整合はINVALIDであり、性質のFAILやUNKNOWNと別。B0でC01がFAILになることは想定された教材条件で、実行自体をINVALIDにしない。

| ID | 条件・確認する性質 | 紙上評価・限界 |
|---|---|---|
| C01 | URLなし、type=layout、layout許可、ruleId/fixあり、fresh cache→記録される | B0 FAIL、P1/P2 PASS |
| C02 | URLあり、type=layout、problemだけ許可→記録しない | B0/P1 PASS、P3 FAIL |
| C03 | URLあり、許可型→記録とURL取得を維持 | B0/P1 PASS |
| C04 | URLなし、修正記録あり、文書表示有効→空の文書操作を提示しない | P1 PASS、P2 FAIL |
| C05 | URLなし、型あり、fixTypesなし→非フィルタ経路維持 | B0/P1 PASS |
| C06 | 型なし、有効フィルタ→不明型を許可型扱いしない | P1はPASS。利用者期待全体はUNKNOWN |
| C07 | 空fixTypes／有効値なし→拡張内の型集合なし分岐 | 外部ESLintの入力受理はUNKNOWN |
| C08 | メタデータAPIなし／結果なし→情報を創作しない | 自動修正全体はUNKNOWN |
| C09 | 既存ID、clear、特殊directive→既存意味を保持 | cache有無をケースごとに明示 |
| C10 | 文書版・診断・修正の対応 | 対象版不一致を検出 |
| C11 | 実VS Codeで各自動修正経路が動作 | 未実施、UNKNOWN |
| C12 | ビルド・型検査・既存テスト | 未実施、UNKNOWN |

C01–C10はmodeled。C11/C12は実行証拠なしにexecutedへ変更しない。recordはCode Action全体の必要情報の一部であり、computeAllFixesの別経路や実際の適用成功まで保証しない。対象外の型・壊れたメタデータ・未知版は適用範囲を確認し、なければUNKNOWN。P1を常にPASSにする専用判定は作らない。

### D8. 正準イベントから公開記録と本人経験を投影する

対応: evidence-projection/EP01–EP07, EP11, EP12, EP14、simulation-execution/SE17。

イベント共通項目: id、run_id、logical_time、order、kind、actor、task/goal、target_refs、input/output_version、state_delta、caused_by、duration/interval、perception、classification。操作命令と完了イベントを区別し、開始・失敗・拒否も記録する。

| 起点 | 操作・イベント例 |
|---|---|
| 本人操作 | IssueRead、DocumentRead、CodeSearched、FileOpened、SymbolNavigated、ApplicationFocused、QuestionSent |
| 本人操作 | PatchApplied/Reverted、CheckExecuted、AITaskDelegated、AIStatusViewed、AIQuestionAnswered、ApprovalResolved、AIResultIntegrated、PullRequestCreated |
| 非同期 | ReplyReceived、AIQuestionRaised、ApprovalRequested、AITaskCompleted、NotificationDelivered |
| 作業制御 | WorkInterrupted、WorkResumed、WaitStarted/Ended、RunEnded |
| 内部 | KnowledgeAcquired、InterpretationRevised、DecisionRecorded、AccessFailed、ReferenceInvalidated |

イベント名だけで分類しない。全シミュレーション出力にsynthetic=trueを持たせ、その上でsource_classをtool-shaped/internalに分ける。tool-shapedには想定ツール・取得方式・取得できるフィールドを示す。ApplicationFocused等も実ツールで常に採れるとは限らず、取得元が未確認なら取得可能性を未検証とする。実測を取り込む将来はmeasuredと別に識別する。内部のKや正解は通常の操作ログへ出さない。

Projectorは固定履歴からログ、意味的画面状態、本人の直接経験・伝聞を生成する。未知のメニュー操作・スクリーンショット・認知負荷を後付けしない。本人の主観はKまたは固定された経験記述であり、操作回数や時間から直接算出した心理的事実ではない。

公開はallowlistで構成し、投影ID→正準イベント・資料への管理用対応表を別保存。調査者には許可された資料・ログのIDだけを返し、内部原因・方針閾値・未確認の将来応答時刻を隠す。正準領域へOSアクセスできる管理者からの隔離は保証しない。取得不能エラーでも秘匿対象の存在を漏らさない。保存条件の評価時点は固定run終了時点。重点範囲と保持範囲を分離する。

取得入口はIssue、時間、対象、操作、成果物、公開根拠IDによる検索・関連取得。専用GUIは不要。追加取得は同じ固定履歴の別投影であり、過去の再シミュレーションではない。

### D9. インタビューは固定された本人パッケージへの読み取りに限定する

対応: evidence-projection/EP04–EP10、simulation-execution/SE17。

終了時にbackground、perceptions、belief_history、memory、behavior_policyの本人向け説明を固定する。MVPの記憶形成は、指定した保持・省略マスクと要約規則で十分。事実の欠落と、根拠のある誤認を分ける。複雑な忘却モデルや第二の回答エンジンは作らない。

質問を受け、許可された本人パッケージから関連情報を取得し、LLMへ渡す。回答は発言単位の `text, epistemic_kind, private_support_ids` を返す契約。experience/interpretation/inference/unknown/not_rememberedを識別し、根拠IDは管理用に検査する。調査者へ出すのは許可された自然言語回答と公開可能な根拠だけ。

根拠優先順位は、本人が保持する経験・当時の認識、固定記憶、一般方針に基づく明示的推測、不明・記憶なし。隠れた正準履歴から失われた理由を自動復元しない。一般方針から過去の具体的日時・行動を創作しない。

Validatorは参照の存在・当人帰属・公開境界・対象版を決定的に検査し、構造化された具体的日時・対象・行動主張を経験表と照合する。自然言語全体の意味保証はできない。検出した捏造・漏洩は棄却し、MVPは再生成なしで回答不能としてよい。意味判定不能はUNKNOWNの検査状態を保存し、調査者にも回答が未検証の合成回答であることを示す。自由文の残余リスクはTask 6.3/7.3の人手監査で確認する。

LLMアダプターは差替可能。自動テストは固定応答の代替実装で捏造・誤認・不明を再現し、第三者調査は固定教材と選定した生成器を使い版・プロンプト・応答を記録する。接続不能は回答不能とし、新しい事実で補わない。生成器が未接続ならインタビュー受入を完了扱いしない。会話表現の逐語再現を正準履歴の再現保証に含めないが、使用した回答は保存し監査できる。質問順序で本人の過去のK・記憶は変えない。

### D10. 固定保存と失敗境界を業務終了から分離する

対応: simulation-execution/SE13–SE18、world-definition/WD03。

保存契約は入力スナップショット、manifest、正準イベント、最終状態、未処理キュー、Workspace差分、投影、本人パッケージ、対応表、検査結果。物理形式は未選定。manifestに定義・教材・規則・エンジン・ランタイム・依存・OS、乱数方式、シード、時間単位・窓、正規化規則を含む。

業務状態はSUBMITTED / INCOMPLETE / CANCELLED。INCOMPLETEにはblocked_information、deadline等の理由と残依存を付す。内部有効性はVALID / INVALIDで別管理。modeledチェックのFAILやPRなしを内部エラーと扱わない。提出条件は差分・説明・確認範囲・未検証事項が揃うことと本人の提出方針で、C11/C12の実行や全チェックPASSを普遍条件にしない。

結果は新規保存先へ書き、Validatorが遷移・参照・資源・投影を検査した後に公開。既存結果は上書きしない。保存障害・内部例外・不正遷移は正常公開を止め、対象・理由を管理者へ返す。Loader=入力、Engine/Scheduler=遷移と資源、Projector/Interview=根拠、Run Store=保存の検出責任。自動復旧・途中実行再開・全版互換変換は非対象。

乱数は固定した安定アルゴリズムと用途別ストリーム（行動選択・操作時間・応答時間）を使い、列挙順も固定する。実時間・ランダムUUID・処理系依存hashを意味内容へ混ぜない。同一固定環境で正規化イベント・最終状態・投影が一致することを独立プロセスで検証する。別シードの差は強制しない。ライブ外部出力は実行中に取得せず保存済み入力を再利用する。

将来の介入は別入力・規則版・実行にし、変更・追加仮定を記録する。同じシードだけで比較可能とせず、必要なら新モデルでベースラインも別実行し、旧履歴を保存する。モデルにない効果は生成しない。

### D11. 紙上3経路を受入用の入力条件へ変換する

対応: world-definition/WD06、simulation-execution/SE19、evidence-projection/EP13。

以下は合成時間による紙上例。数値は校正前の仮定。候補・規則・教材・チェック・期限H=40は共通。A/B/Cという経路IDは期待証拠のラベルだけで、実行入力の制御命令にしない。

| 入力差 | A | B | C |
|---|---|---|---|
| 型フィルタ維持の初期理解 | あり | 未確認 | あり |
| 変更前確認方針 | 調査後に選択 | 暫定案も試す | 外部仕様の確証を要求 |
| D04/D05アクセス | 可 | 可 | 不可 |
| AI方針 | 自分で調査 | 委任可 | 利用しない |
| 応答モデル | 相談なし | AIが編集範囲拡大を要求 | 同僚応答45、本人は実時刻を知らない |

| 経路 | 論理区間と状態・情報変化 | 分岐の根拠 |
|---|---|---|
| A | 0–5 Issue/設定、5–13 captureと型利用を追跡、13–16外部仕様、16–20文書操作確認、20–24 P1、24–28模擬確認、28–31提出 | 調査からP2副作用を知り、P1を選択。最初から正解を渡さない |
| B | 0–8 Issue/設定/validate、8–10 P3、10–13 C02反例、13–14撤回、14–16委任、16–19人間が外部仕様確認 | filterを外してよいと暫定解釈。反例で再調査 |
| B続き | AIは16–17調査しserver変更の承認待ち、通知17/本人確認19、19–20承認、AI20–24実行。人間20–24 server確認、24–26統合、26–30模擬確認、30–33提出 | 元依頼の編集許可はeslint.tsのみ。R10修正に範囲拡大が必要。人間とAIの並列を二重計上しない |
| C | 0–10 Issue/設定/ソース、10–11外部資料取得不能、11–13質問、13–16独立整理、16–40待機、40未完了 | 仕様確証なし、代替調査を消化、相談未応答、期限という状態の組合せ。45の応答を知識へ先取りしない |

実装受入では分刻みの完全一致より、同じ規則から必要な状態・反例・待機が生じることを検証する。具体パラメータ・期待経路は実装前に固定し、問題を発見するまでシードを探してケーススタディに採用しない。経路の検証用入力と、DevEx調査用のケース選定を区別する。

### 要件・設計・主タスクの対応

番号は各capabilityの安定ID。下表は主要な実装先であり、全件の最終証拠はTask 7.4で集約する。区間表記に隠れた対応漏れを避けるため各要件を列挙する。

| 要件 | 設計 | 主タスク |
|---|---|---|
| WD01 | D1/D3 | 1.3 |
| WD02 | D1/D3 | 1.3 |
| WD03 | D2/D10 | 1.3, 5.3 |
| WD04 | D5 | 1.3, 3.1 |
| WD05 | D2 | 1.1 |
| WD06 | D3/D11 | 2.1, 7.2, 7.3 |
| WD07 | D2 | 1.1 |
| WD08 | D3/D6/D7 | 2.1, 2.2 |
| WD09 | D3/D4 | 1.3, 2.4 |
| WD10 | D5 | 3.1 |
| WD11 | D2/D3 | 1.3, 2.3 |
| WD12 | D1/D3/D6/D7 | 2.1, 2.3, 4.1 |
| SE01 | D10 | 5.1 |
| SE02 | D5 | 3.2 |
| SE03 | D3/D4 | 2.4 |
| SE04 | D3/D4 | 2.3 |
| SE05 | D4 | 2.4 |
| SE06 | D3/D4/D6 | 2.3 |
| SE07 | D5 | 3.3, 4.2 |
| SE08 | D5 | 3.3 |
| SE09 | D4/D5 | 3.2 |
| SE10 | D5 | 3.2 |
| SE11 | D6 | 2.2, 2.3, 4.2 |
| SE12 | D7 | 2.2, 4.1 |
| SE13 | D10 | 5.1 |
| SE14 | D5/D10 | 1.2, 3.1, 7.1 |
| SE15 | D10 | 1.2, 3.1, 5.3 |
| SE16 | D7/D10 | 5.2 |
| SE17 | D8/D9/D10 | 5.3, 7.1 |
| SE18 | D10 | 5.3 |
| SE19 | D11 | 7.2 |
| EP01 | D8 | 6.1 |
| EP02 | D8 | 6.1, 6.5 |
| EP03 | D8 | 6.1 |
| EP04 | D8/D9 | 6.2 |
| EP05 | D9 | 6.2 |
| EP06 | D8/D9 | 6.3, 6.4 |
| EP07 | D8 | 6.4 |
| EP08 | D9 | 6.3, 6.5 |
| EP09 | D9 | 6.3 |
| EP10 | D9 | 6.3 |
| EP11 | D7/D8 | 6.1, 7.1 |
| EP12 | D8 | 6.4, 6.5 |
| EP13 | D11 | 7.3 |
| EP14 | D8 | 6.1, 6.4, 7.3 |

## Risks / Trade-offs

- [整合性を現実妥当性と誤認] → 三種類の受入を分離し、現実行動の実証はUNKNOWN。合成ログと合成回答の一致は独立証拠ではない。
- [候補に正解が埋まり本人へ漏れる] → actor viewと教材の結果規則を分離し、隠れ情報変更で判断が不変なテストを行う。
- [P1等の意味状態とバイト差分がずれる] → 教材の差分レビュー・内容識別・対応チェックを必須にし、未知版はUNKNOWN。
- [Issue自体に原因手掛かりがある] → その条件を明示して利用し、DevEx上の原因発見と技術Issueの原因推定を混同しない。
- [詳細GUIを省略して操作性を評価し過ぎる] → 画面・対象・利用可能コマンドまでに限定し、未収録メニューや心理負荷は推論限界を示す。
- [自由文LLMの意味検証は不完全] → 最小権限、構造化根拠、棄却・UNKNOWN、人手監査。完全な幻覚防止を保証しない。
- [公開境界の破壊は高影響] → 正準・本人・調査者の契約変更時、本文・根拠ID・エラー情報を再検証する。
- [時間仮定が課題の結論を支配] → 根拠分類と感度比較を残し、一律損失係数を使わない。
- [調査可能な問題が生じない] → 改善不要・判断保留を許容。追加調査が不可能なら受入上の不足を報告し、課題を後付けしない。

## Migration Plan

### 旧要件からの対応

旧文書は未実装・未アーカイブのため、実装済み要件に対するREMOVED/MODIFIED deltaは作らない。Git履歴と以下の対応表で旧計画からの変更を追跡する。

| 旧capability / Requirement | 扱いと改訂先 |
|---|---|
| world-definition / Explicit world inputs | 変更継承→WD01。教材・本人・ツール中心へ |
| Reject invalid definitions | 継承→WD02 |
| Identifiable frozen inputs | 継承→WD03 |
| Predetermined study timeline | 変更→WD04。12週・4週三区分はMVPから削除。期間事前固定だけ継承 |
| Fixture provenance | 拡張→WD05。OSS・合成・正式資料を区別 |
| No required problem outcome | 継承→WD06 |
| simulation-execution / Code change lifecycle | 変更→SE01。着手→提出。レビュー・CI工程・マージの義務を削除 |
| Explainable background influence | 縮小→SE02。割り込み・依存等だけ。企画/QA四種の必須再現は延期 |
| Knowledge bounded decisions | 拡張→SE03、SE05 |
| Reproducible execution | 継承→SE14 |
| Execution provenance | 継承→SE15 |
| Consistent canonical history | 拡張→SE16 |
| Frozen completed run | 継承→SE17。第12週終了条件を除去 |
| Explicit failed execution | 継承→SE18。業務未完了との違いをSE13で新設 |
| evidence-projection / Shared evidence origin | 拡張→EP01 |
| Observable work records | 変更→EP02。レビュー・CI履歴から操作・協働・仮想チェックへ |
| Employee perception boundary | 継承→EP04 |
| Fixed employee evidence package | 変更→EP05。12週から実行終了へ、記憶固定を追加 |
| Role bounded disclosure | 継承→EP06 |
| Retention bounded historical access | 変更→EP07。12週制限を除き公開原則を継承 |
| Projection consistency report | 継承→EP11 |

新設はWD07–WD12、SE04–SE12（SE05を除く）、SE13、SE19、EP03、EP08–EP10、EP12–EP14。SE05は旧知識境界の拡張。旧要件名を参照する下流のテスト・文書はこの表で移行する。

### 旧設計判断からの対応

| 旧決定 | 改訂先と扱い |
|---|---|
| D1 Python/CLI | 新D1。ローカル境界を継承、Python選定は解除 |
| D2 DES/判断 | 新D3–D5。DESと本人境界を継承、レビュー/CI/マージ規則は削除 |
| D3 時間/乱数 | 新D5/D10。12週・整数分固定を外し、tickと安定順序を具体化 |
| D4 正準/投影 | 新D4/D8/D9。知識・画面・インタビューを拡張 |
| D5 JSON保存 | 新D10。公開・失敗境界を継承、JSON/JSONL選定は解除 |
| D6 公開 | 新D8/D9。12週前提を外し回答コンテキストまで適用 |
| D7 縦断検証 | 新D11とTasks 7。三種類の受入へ |
| D8 将来介入 | 新D10。別版・別実行・比較限界を継承 |

### 旧18タスクからの対応

| 旧Task | 新Task | 扱い |
|---|---|---|
| 1.1 | 1.2 | 実装環境選定を含めて再定義 |
| 1.2 | 1.3 | 教材入力・版・参照検証へ |
| 1.3 | 1.1、2.1、2.2 | OSS教材・候補・チェックの単位へ分割 |
| 1.4 | 3.1 | 12週カレンダーを削除、論理時間・期限へ |
| 2.1 | 3.1、7.1 | 決定的キューと再現性 |
| 2.2 | 2.3、2.4、5.1 | レビュー/マージ削除、行動・Workspace・提出へ |
| 2.3 | 2.4 | 認識更新と誤判断を追加 |
| 2.4 | 3.2、3.3 | 割り込み・依存・協働へ縮小 |
| 2.5 | 5.2 | 版・資源・履歴の検査へ |
| 3.1 | 6.1 | 操作ログと根拠投影へ |
| 3.2 | 6.2 | 本人経験・固定記憶へ |
| 3.3 | 6.1、6.3 | 投影検査と回答検査へ分割 |
| 3.4 | 6.4 | 公開・保持・追加取得へ |
| 4.1 | 5.3 | manifestと固定入力保存 |
| 4.2 | 5.3 | 有効な未完了と内部失敗を分離 |
| 4.3 | 6.5 | ローカル縦断入口へ |
| 5.1 | 7.1、7.2 | 再現性と反応性を分離 |
| 5.2 | 7.3、7.4 | 第三者調査と受入証拠へ |

改訂後はTask 1.1から開始し、各単位でテスト・利用説明を揃える。旧実装・生成データの移行はない。後続契約が変わった場合は影響する教材・投影・回答・検証証拠を再確認する。撤回・介入でも保存済み結果を上書きしない。

## Open Questions

以下は意味契約・成果物・タスク構造を変えない技術選定として延期する。
- Task 1.2: 言語、テスト入口、キューのライブラリ、物理保存形式。選定後は対応環境と正規化仕様を固定する。
- Task 6.3: LLMプロバイダー・モデル・プロンプト詳細。許可コンテキスト、根拠付き出力、棄却/UNKNOWNの契約は固定。
- 操作・応答時間の校正値、正式LAEの社員・経歴。MVPでは明示した合成入力を使い、実測・正式資料を得たら別版で検証する。
- 実VS Code再現、コンパイル、経験的行動妥当性、介入効果。今回の合格の前提にはしない。
