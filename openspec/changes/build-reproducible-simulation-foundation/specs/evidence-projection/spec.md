# Spec Delta

## Purpose

共通の固定履歴から調査者向け合成記録と本人向け経験を生成し、根拠と公開範囲を追跡可能にする。観測、認識、推測、モデル限界を分離し、追加調査と合成インタビューによる仮説検討を可能にする。

## ADDED Requirements

### Requirement: EP01 Shared evidence origin
システムは、合成記録・本人経験・回答根拠を正準イベントまたは固定資料へ追跡可能にしなければならない（SHALL）。

#### Scenario: Trace related outputs
- **WHEN** 管理者が同じ操作のログと本人経験を照合する
- **THEN** 元イベント・対象資料・コード版を特定でき、履歴にない経験が追加されていないことを確認できる

### Requirement: EP02 Observable work records
システムは、Issue理解、コード・資料探索、画面遷移、AI・相談、待機・切り替え、仮想変更・チェック・提出の収録された履歴を取得可能にしなければならない（SHALL）。

#### Scenario: Retrieve an issue timeline
- **WHEN** 調査者が権限内のIssue履歴を要求する
- **THEN** 主体、対象、時刻、参照版、結果を時系列で取得でき、未完了でも利用可能な記録を確認できる

### Requirement: EP03 Event provenance classes
システムは、ツールで取得可能な形式を模した合成操作、内部合成イベント、実測記録を区別して表示しなければならない（SHALL）。

#### Scenario: Synthetic focus log
- **WHEN** ApplicationFocusedを合成出力する
- **THEN** 合成であることと想定する取得元を示し、実IDEで採取したログとは表示しない

#### Scenario: Private decision is not telemetry
- **WHEN** 本人の暫定解釈が更新される
- **THEN** 内部合成イベントと識別し、通常のIDE操作ログで直接観測した心理状態として公開しない

### Requirement: EP04 Employee perception boundary
システムは、本人経験に本人の直接経験または伝達内容だけを含めなければならない（SHALL）。

#### Scenario: Limited notification
- **WHEN** 通知が到着しても本人がまだ確認していない
- **THEN** 到着した事実と本人の知覚を分離し、未確認の内容や管理用原因を本人情報へ渡さない

### Requirement: EP05 Fixed employee evidence package
システムは、終了時の本人情報について、固定背景、実行中の知覚、当時の認識、保持された記憶を区別して固定しなければならない（SHALL）。

#### Scenario: No prehistory invention
- **WHEN** 開始前の具体的エピソードが背景情報に存在しない
- **THEN** 経験・記憶の形成時にそのエピソードを補作しない

#### Scenario: Memory is incomplete
- **WHEN** 記憶形成規則が一部の判断理由を保持しない
- **THEN** 固定された欠落として残し、後の質問から理由を生成して補わない

### Requirement: EP06 Role bounded disclosure
システムは、管理者・本人・調査者に対し許可された情報だけを提供しなければならない（SHALL）。

#### Scenario: Interview context
- **WHEN** インタビュー用コンテキストを構成する
- **THEN** 当人の許可情報だけを含め、他社員だけの知識、内部の正解、非公開の行動規則を渡さない

#### Scenario: Unknown role
- **WHEN** 未定義または未許可の役割で取得する
- **THEN** 拒否し、管理者情報へフォールバックせず、非公開情報の存在を漏らさない

### Requirement: EP07 Retention bounded historical access
システムは、調査の重点範囲と参照可能範囲を分離し、権限・保存条件に基づいて過去記録を提供しなければならない（SHALL）。

#### Scenario: Earlier retained evidence
- **WHEN** 重点範囲外でも許可と保存条件を満たす記録を要求する
- **THEN** 記録を提供し、固定の12週間制約を課さない

#### Scenario: Missing evidence
- **WHEN** 詳細が未記録または取得不能である
- **THEN** 許可範囲で利用不能を示し、管理用履歴や新しい物語で欠落を埋めない

### Requirement: EP08 Fixed interview grounding
システムは、固定された本人経験・記憶・認識・行動方針に基づく自然言語インタビューを提供しなければならない（SHALL）。

#### Scenario: Why was a file opened
- **WHEN** 調査者が特定の閲覧理由を尋ねる
- **THEN** 本人向け固定情報にある理由を回答根拠とし、正準状態の隠れた説明を自動開示しない

### Requirement: EP09 Interview epistemic limits
システムは、回答で経験・本人の解釈・推測・不明・記憶なしを区別できなければならない（SHALL）。

#### Scenario: No remembered reason
- **WHEN** 当時の理由が本人向け情報にも記憶にもない
- **THEN** 不明または記憶なしと答えられ、一般的な行動方針から具体的な過去の出来事を断定しない

#### Scenario: Grounded misunderstanding
- **WHEN** 当時の誤認が固定本人情報に記録されている
- **THEN** 本人の認識として説明でき、世界の客観的事実と一致しないことだけで生成ミスと分類しない

### Requirement: EP10 Interview failure handling
システムは、回答の根拠検査と検査限界を記録し、検出した根拠なしの具体的発言や情報漏洩を有効回答として提供してはならない（MUST NOT）。

#### Scenario: Fabricated episode is detected
- **WHEN** 検査で未登録の具体的経験または非公開情報の混入を検出する
- **THEN** 回答を棄却し、固定入力を変えない制限付き再生成または回答不能とし、検査証拠を管理者へ残す

#### Scenario: Meaning cannot be verified
- **WHEN** 自動検査で回答の意味的整合性を確定できない
- **THEN** 検査状態をUNKNOWNとして記録し、確認済みの整合性や幻覚の完全防止を主張しない

### Requirement: EP11 Projection consistency report
システムは、投影の根拠・知覚・公開範囲の検査結果を、対象と理由付きで報告しなければならない（SHALL）。

#### Scenario: Forged experience
- **WHEN** 根拠のない経験または他人だけの知識を検査入力へ混入する
- **THEN** 違反箇所を報告し、有効な投影として公開しない

#### Scenario: Unsupported external validity
- **WHEN** 実開発者への妥当性や実ツールの効果を整合性検査で評価しようとする
- **THEN** UNKNOWNまたは対象外とし、整合性PASSから効果実証を導かない

### Requirement: EP12 Investigable evidence retrieval
システムは、調査者がIssue、時刻、操作、成果物を起点に許可された関連証拠を追加取得できなければならない（SHALL）。

#### Scenario: Follow an alternative hypothesis
- **WHEN** 調査者が待機の原因を調べるため通知・承認・並行作業の記録を要求する
- **THEN** 固定履歴にある関連証拠を取得でき、取得順序を変えても内容が変わらない

### Requirement: EP13 Investigation acceptance record
システムの受入では、第三者が公開証拠から仮説・競合仮説・追加調査・判断更新を根拠付きで記録できることを検証しなければならない（SHALL）。

#### Scenario: Evidence is inconclusive
- **WHEN** 第三者がログとインタビューを調べても必要な根拠が不足する
- **THEN** 判断保留と限界を受入記録に残せ、特定原因の発見や改善策の採用を合格条件にしない

### Requirement: EP14 Observation coverage limits
システムは、提供する証拠の収録粒度と推論限界を明示しなければならない（SHALL）。

#### Scenario: Unmodeled GUI details
- **WHEN** 記録していないメニュー操作や心理的負担について質問する
- **THEN** 操作結果から詳細や負担を断定せず、モデル外または根拠不足と示す
