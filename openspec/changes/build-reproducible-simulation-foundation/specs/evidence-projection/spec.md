# Spec Delta

## Purpose

業務記録と社員経験を共通の業務履歴から形成し、後続の調査とヒアリングの根拠を提供する。正準情報、本人が知る内容、調査者に公開する内容を分離し、整合性の検査と調査後の照合を可能にする。

## ADDED Requirements

### Requirement: Shared evidence origin
システムは業務記録と社員経験を、実行の正準イベントまたは固定背景情報に根拠づけなければならない（SHALL）。

#### Scenario: Trace related outputs
- **WHEN** 同じPRに関する記録と社員経験を管理者が照合する
- **THEN** 両方の情報源を特定でき、実行履歴にない経験が追加されていないことを検査できる

### Requirement: Observable work records
システムはIssue変更履歴、PR・レビュー履歴、CI結果、および背景作用の業務上の痕跡を出力しなければならない（SHALL）。

#### Scenario: Record timeline
- **WHEN** IssueまたはPRの記録を参照する
- **THEN** 関連する業務記録の時刻、主体、内容と対象を時系列で確認できる

### Requirement: Employee perception boundary
システムは社員経験に、本人の直接経験または本人に伝達された内容だけを含めなければならない（SHALL）。経験の内容と、管理用の真の原因は区別する。

#### Scenario: Limited message
- **WHEN** 背景イベントの真の原因を知らない社員が、限定された連絡だけを受け取る
- **THEN** 社員経験には連絡された内容と伝聞であることが残り、未伝達の真の原因は含まれない

### Requirement: Fixed employee evidence package
システムは第12週終了後に、社員の固定背景情報と12週間の知覚・経験を識別して取得できなければならない（SHALL）。これは後続の記憶・認識形成の入力であり、高度な記憶モデルは要求しない。

#### Scenario: No prehistory invention
- **WHEN** シミュレーション開始前の具体的エピソードが固定背景情報に存在しない
- **THEN** 社員情報の取得時にそのエピソードを補作しない

### Requirement: Role bounded disclosure
システムは管理者、社員本人、調査者に応じた出力を提供し、未許可情報を公開してはならない（SHALL）。調査者への正準状態・内部パラメータ・管理用因果情報・非公開根拠参照の公開は禁止する。

#### Scenario: Employee and investigator exports
- **WHEN** 同じ実行から社員本人向けと調査者向けの出力を要求する
- **THEN** 社員には本人向け情報だけ、調査者には通常の役割権限で閲覧可能な業務情報だけが提供される

#### Scenario: Unknown role
- **WHEN** 未定義または未許可の役割で出力を要求する
- **THEN** アクセス拒否を返し、管理者向け情報へフォールバックしない

### Requirement: Retention bounded historical access
システムは主観測期間と参照可能期間を区別し、権限と保存条件を満たす過去12週間の記録を提供できなければならない（SHALL）。

#### Scenario: Earlier retained record
- **WHEN** 調査者が第2週の記録を要求し、その記録が権限と保存条件を満たす
- **THEN** 主観測期間外であることだけを理由に除外しない

#### Scenario: Unavailable record
- **WHEN** 記録が保存条件を満たさない、または閲覧権限がない
- **THEN** 利用不能またはアクセス拒否を示し、記録を創作せず、未許可の内容や存在を漏らさない

### Requirement: Projection consistency report
システムは投影の根拠参照、対象社員の知覚範囲、公開範囲を検査し、管理者が違反箇所を追跡できる結果を出さなければならない（SHALL）。

#### Scenario: Forged experience
- **WHEN** 元イベントのない社員経験を検査用に混入させる
- **THEN** 根拠不備として検出し、有効な投影として公開しない

#### Scenario: Unsupported conclusion
- **WHEN** 検査対象が将来のLLM発言の正しさや改善効果など、本基盤では評価できない内容である
- **THEN** 評価対象外またはUNKNOWNとし、整合性検査のPASSで正しさを保証した扱いにしない
