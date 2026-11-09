# G2 固定シナリオ契約 1.2.0

`fixtures/g2/scenario.json` は、G1で固定した教材から作成した #1955 演習の候補・規則・仮想Patch・modeled Checkを保持する。これは実行結果ではなく、G3以降が利用できる検証済み入力である。`lae-sim validate-scenario fixtures/g2/scenario.json` は外部接続やシミュレーションを行わずに検査する。

## 境界

- `source_manifest` はG1 manifestのsource ID、revision、個別ファイルdigestを再参照する。可動refや別版へ置換しない。
- `world_claims` は実在OSS、架空企業draft、合成仮定を `origin` と `status` で区別する。`context` は `company_context`、`team_profile`、`exercise_scenario` の三層をclaim IDで結ぶ。
- `actor_view` は本人に見える初期claimと候補表示名だけを持つ。管理用期待値、固定候補順、Patchの正解ラベルを含めない。
- `references` の `unrecorded` / `unresolved` はtargetを断定できない。資料が束にあること、本人がアクセスできること、関係が収録済みであることは別契約である。
- Searchが複数参照を獲得した場合、参照IDはPython文字列の昇順でイベント・状態へ記録し、Workspaceパスはパス文字列の昇順で直列化する。集合の反復順や`PYTHONHASHSEED`へ依存させない。
- `candidates` はT01–T15を順序なしで定義する。利用条件、前提、効果は有限の型付き演算だけを使い、任意スクリプトとIssue固有演算を拒否する。
- `patch.apply` 候補の `patch_ids` は選択可能なPatch IDを明示する。実行時には候補の前提と対象を正準Reducerで検査する。1.2.0では必須とし、1.0.0/1.1.0の旧入力で未指定の場合は従来の全Patchを選択可能とする解釈を維持する。
- `rules` はR-A–R-Gの判断原則であり、候補優先順位やP1へ到達するPolicyではない。T15による有効な未完了を許し、DevEx問題の発生を成功条件にしない。

## PatchとCheck

P1–P4はB0の `server/src/eslint.ts` に対応する限定的なbefore/afterバイト断片を持つ。検証器はG1 readable extractの元バイトdigest、before断片の存在、断片digest、意味状態、影響referenceを照合する。P5は同一バイトを持つ変更なし・追加調査である。

意味判定は`semantic_model`の版付き`source-facts-1`で定義する。型付きCheck assertionは有限なfactの真偽だけを照合し、factは各Workspace版の現在バイトから再評価する。`semantic_delta`は説明文であり、Evaluatorは参照しない。Patch適用・複数Patch・撤回後のバイトが固定マーカーから一意に分類できない場合はUNKNOWNとする。これはTypeScript構文、コンパイル、VS Code動作を保証しない。P2のURLなし文書操作副作用、P3の型フィルタ違反、P4の不明型扱い、fresh/existing cache条件を別に記録する。

C01–C12はすべて `mode=modeled` である。C11/C12も実行計画とUNKNOWNの限界を固定しただけで、実機、build、型検査、既存テストを実行した証拠ではない。検証器は未知版、未知述語、`executed`への格上げを拒否する。schema 1.0.0は後方互換で読み込めるが、型付き意味事実を持たないため、実行時Checkは安全側にUNKNOWNとなる。schema 1.1.0の意味モデルは固定バイト断片の観測に限られ、管理用期待ラベルをEvaluatorへ渡さない。

## 固定条件と未決定事項

EX01/EX02は演習目的と仮想提出先を固定する。EX03は一人の仮名参加者、読取り・検索・仮想編集・modeled check・情報質問の範囲を宣言し、相談相手を承認者とは扱わない。EX04はこの入力ではAI無効、時間は合成tick、応答は期限前に保証されないとする。会社全体の個別権限、AI承認、実名の専門家、応答SLAは未決定の会社事実として補完しない。

抽出履歴は手動抽出・レビューを記録する。準備LLMは使用しておらず、実行時LLM、Google Drive、GitHubへの接続は不要である。

## Scenario版別入力例

以下は各版で追加・異なる入力を示す断片であり、完全なScenario文書ではない。

### 1.0.0 / 1.1.0

```json
{"schema_version":"1.0.0","candidates":[{"operation":"patch.apply"}]}
```

1.0.0/1.1.0では`patch.apply`候補の`patch_ids`省略を旧意味どおり全Patch選択可能として扱う。`search_profile`は未知入力として拒否する。

### 1.2.0 / 1.3.0

```json
{"schema_version":"1.3.0","tool_availability":{"code.search":true}}
```

1.2.0/1.3.0では`patch.apply`に`patch_ids`が必須。1.3.0は`tool_availability`とCandidateの`required_claims`を受理し、初期知識・要求知識の出典上限を検査する。両版とも`search_profile`は拒否する。

### 1.4.0

```json
{"schema_version":"1.4.0","tool_availability":{"code.search":true},"search_profile":{"paths":["server/src/is.ts"]}}
```

1.4.0は1.3.0の入力検査と実行意味を継承する。`search_profile`省略時はWorkspace全体、指定時は非空の一意な相対POSIXパス集合だけを検索範囲とする。明示した`null`は拒否する。参照の`evidence`は既存欄を使い、B0の収録済み参照を出典・完全Workspaceパス・1始まり包含行範囲へ一意に解決する。曖昧、誤出典、範囲外の行は実行前に拒否し、未収録・未解決参照を収録済みへ昇格させない。検索範囲を狭めても参照の曖昧さは解消しない。範囲や結果を直接入力するフィールドはない。
# Scenario 1.4.0 search result contract

For Scenario 1.4.0, a Search result is calculated from case-insensitive matches in the current Workspace version and the configured `search_profile.paths` only. Omitting `search_profile` searches all Workspace files. An explicit profile is a fixed set; its array order does not affect results. Recorded reference IDs are included only when their validated full Workspace path and line range contain a matching line, and only when the reference is recorded, non-audit, and not invalidated. Results are sorted deterministically.

A successful search with no results records `no-match-in-search-scope`. This means only that the query had no match in that operation's scope. It does not assert that a match is absent outside the scope, that the search tool was unavailable, that a location is known, or that the participant understood the material. Search publication uses the existing `limitations` field to state that results are scope-limited without disclosing the paths or scope size. Earlier scenario versions retain their previous search and no-match semantics.

## Scenario 1.4.0: 一つの参照は一つのファイルに限定する

`evidence`は一つの完全Workspaceパスと、そのファイル内の行範囲に対応する。

| 入力例 | 動作（対象と行が有効な場合） |
|---|---|
| `a.ts:1` | 受理 |
| `a.ts:1-5,8-10` | 受理 |
| `eslintServer.ts:692-700,823-827` | 受理 |
| `a.ts:1,b.ts:2` | 拒否 |
| `a.ts:1-3,b.ts:5-7` | 拒否 |

異なる完全パスへ解決される指定は、`$.references[index].evidence`と理由コード
`multiple-workspace-reference-paths`を含む入力エラーで拒否する。最後のファイルの採用、
先行区間の付け替え、一部採用などの暗黙補正は行わない。同じ完全パスに解決される
短い名前と完全パスの再指定は受理する。既存の単一ファイル参照と旧1.0〜1.3の
入力検証意味は維持する。複数ファイル参照は将来必要性が確認された場合の別仕様変更とする。
