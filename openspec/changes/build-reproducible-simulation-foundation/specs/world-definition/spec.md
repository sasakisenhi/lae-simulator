# Spec Delta

## Purpose

調査より先に教材・本人情報・環境・規則を固定し、演習用OSSと架空企業設定を区別する。入力の根拠と不確実性を識別し、同じ条件の実行や後続の調査に必要な参照境界を提供する。

## ADDED Requirements

### Requirement: WD01 Explicit world inputs
システムは、教材、Issue、本人・ツール定義、規則、時間、アクセス・公開条件を参照可能な一つの実行入力として受け付けなければならない（SHALL）。本人・ツール定義の内容はWD09で扱う。

#### Scenario: Inspect a minimal world
- **WHEN** 管理者が有効な一件のIssueの入力を読み込む
- **THEN** 実行に使う各条件と定義版を確認できる

### Requirement: WD02 Reject invalid definitions
システムは、不正な状態、参照切れ、版の不一致、非対応の定義を実行前に理由付きで拒否しなければならない（SHALL）。

#### Scenario: Invalid reference
- **WHEN** 作業候補が未定義のコード参照IDまたは存在しない社員を参照する
- **THEN** 対象と理由を報告して実行を拒否し、未収録参照を有効な参照として補完しない

#### Scenario: Unsupported definition version
- **WHEN** 非対応の定義版を入力する
- **THEN** 暗黙に変換せず拒否する

### Requirement: WD03 Identifiable frozen inputs
システムは、実行に使用する全入力と規則を内容識別可能なスナップショットとして固定しなければならない（SHALL）。

#### Scenario: Changed preparation output
- **WHEN** 実行後に元資料やLLMの候補抽出結果が変更される
- **THEN** 保存済み実行は使用時の入力を保持し、新しい入力と区別できる

### Requirement: WD04 Predetermined study timeline
システムは、実行開始・終了条件と調査対象期間を結果確認前に固定しなければならない（SHALL）。

#### Scenario: One issue instead of twelve weeks
- **WHEN** 管理者が一件のIssueと有限の作業期限を設定する
- **THEN** 12週間やレビュー・マージを要求せず実行でき、発生した問題に合わせて観測期間を自動選別しない

### Requirement: WD05 Fixture provenance
システムは、演習用OSS、正式なLAE資料、検証用設定、実測、外部仕様、合成仮定を識別可能にしなければならない（SHALL）。

#### Scenario: Exercise is not an LAE product
- **WHEN** VS Code ESLint教材と検証用社員条件を取得する
- **THEN** LAEが当該OSSを開発・所有する事実や、社員条件が正式設定であるとは表示しない

### Requirement: WD06 No required problem outcome
システムは、特定のDevEx課題や改善策の必要性を実行成功の条件としてはならない（MUST NOT）。

#### Scenario: No improvement is justified
- **WHEN** 有効な実行から明確なDevEx問題が見つからない
- **THEN** その理由で結果を無効化したり、問題が出る入力・シードへ自動差し替えしたりしない

### Requirement: WD07 Versioned exercise sources
システムは、教材のコード・資料に出典、対象版、内容識別値、利用条件、取得・検証状態を関連づけなければならない（SHALL）。

#### Scenario: Exact commit cannot be verified
- **WHEN** 指定SHAの内容を確認できず別refだけ取得できる
- **THEN** 同一内容とみなさずUNAVAILABLEまたは未検証と示し、必須教材なら実行を拒否する

#### Scenario: Later issue discussion
- **WHEN** Issue作成後のコメントを教材へ収録する
- **THEN** 開始時に取得可能な資料と検証者向け後日資料を区別できる

### Requirement: WD08 Scenario candidate catalog
システムは、根拠・前提・結果・失敗時の扱いを持つ作業、探索、変更、チェック候補を、実行順序と独立した教材定義として受け付けなければならない（SHALL）。

#### Scenario: Candidate is not a scripted path
- **WHEN** 同じ候補集合に異なる初期知識を与える
- **THEN** すべての候補を実行する固定順序を要求せず、選択候補と選択結果を記録できる

### Requirement: WD09 Actor and tool configuration
システムは、本人の知識・行動方針、利用可能な操作、ツール機能、権限を設定できなければならない（SHALL）。

#### Scenario: AI is optional
- **WHEN** AI利用を選ばない本人条件で実行する
- **THEN** AI未使用のまま調査・変更・提出または未完了へ進める

#### Scenario: Invalid initial knowledge or capability
- **WHEN** 本人定義が未定義の根拠IDを初期知識として含む、またはツール定義が非対応操作を利用可能とする
- **THEN** WD02に従い対象を示して拒否し、管理者用情報や代替操作で暗黙補完しない

### Requirement: WD10 Time assumption provenance
システムは、所要時間・応答時間の生成規則に、入力変数、単位、根拠分類、不確実性、適用範囲を関連づけなければならない（SHALL）。

#### Scenario: Synthetic duration
- **WHEN** 根拠となる実測値のない操作時間を使う
- **THEN** 合成仮定と識別でき、規則・値を変更した別条件で感度を確認できる

### Requirement: WD11 Source access outcomes
システムは、本人による資料アクセスの成否を収録範囲とは独立して記録しなければならない（SHALL）。

#### Scenario: A fixed document is unavailable
- **WHEN** 教材に存在する資料への本人アクセスが不能となる
- **THEN** 利用不能という結果を記録し、閲覧成功や内容の知識取得を生成しない

### Requirement: WD12 Engine independent exercise definition
システムは、Issue固有のコード参照・知識・変更候補・チェック規則を、汎用実行処理を変更せず教材として読み込めなければならない（SHALL）。

#### Scenario: Replace a fixture
- **WHEN** 対応済み操作と定義形式を使う別の最小教材へ差し替える
- **THEN** Issue IDや対象シンボルをエンジンへ追加せず実行・検査できる

### Requirement: WD13 Reference coverage uncertainty
システムは、未収録・未解決の参照関係を不存在として回答してはならない（MUST NOT）。

#### Scenario: A relationship is outside the index
- **WHEN** 定義済み参照IDの収録範囲外または未解決の関係を問い合わせる
- **THEN** 対象外またはUNKNOWNを示し、関係が存在しないとは断定しない

### Requirement: WD14 Minimal intervention input contract
システムはScenario 1.3.0で、静的capabilityと独立した固定検索可用性を受理しなければならない（SHALL）。

#### Scenario: Independent fixed tool availability
- **WHEN** 同じ候補・capabilityに異なる固定検索可用性を与える
- **THEN** 両定義を受理し、可用性を固定入力として識別できる

#### Scenario: Legacy input
- **WHEN** 旧Scenario版を読み込む
- **THEN** 新フィールドは受理せず、既存定義の従来動作を維持する

### Requirement: WD15 Validated knowledge prerequisite inputs
システムはScenario 1.3.0の候補required_claimsと初期知識について、全IDと出典を検証し、未知claim・空出典・管理区分・監査専用出典を拒否しなければならない（SHALL）。

#### Scenario: Protected knowledge prerequisite
- **WHEN** 必要claimまたは初期claimが未定義か本人に許可されない出典を持つ
- **THEN** 対象を示して入力拒否し、本人情報へ混入させない
