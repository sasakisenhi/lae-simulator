# Spec Delta

## Purpose

固定された世界定義に従ってコード変更業務と背景工程の影響を実行し、調査と将来の介入検討に利用できる正準履歴を残す。同じ実行条件から同じ業務イベントと最終状態を再現し、結果の由来と失敗を確認可能にする。

## ADDED Requirements

### Requirement: Code change lifecycle
システムはIssue受領、実装、PR作成、レビュー、必要な修正、CI、マージを、定義された業務規則に従う状態遷移として実行しなければならない（SHALL）。

#### Scenario: Lifecycle with rework
- **WHEN** 修正要求とCI結果を含む検証用条件で変更を実行する
- **THEN** 管理者はIssueとPRに関連する作業、レビュー、修正、CI、マージの順序と最終状態を履歴から確認できる

### Requirement: Explainable background influence
システムは背景イベントが中心工程へ与えた影響を、その背景イベントへ追跡可能にしなければならない（SHALL）。背景工程の内部作業の詳細再現は要求しない。

#### Scenario: Background inputs
- **WHEN** 企画変更、QA差し戻し、他チーム依存、割り込みが中心工程へ作用する検証用実行を行う
- **THEN** 管理者は各作用の発生時刻、関係者、理由、対象作業への影響を確認できる

### Requirement: Knowledge bounded decisions
社員の業務上の判断は、その時点で本人に利用可能な知識と状態に基づかなければならない（SHALL）。

#### Scenario: Unseen external event
- **WHEN** 他チームの出来事が本人に伝わっていない
- **THEN** その社員の判断根拠に未伝達情報は含まれない

### Requirement: Reproducible execution
システムは同一の世界入力、シード、エンジン版、対応実行環境で、同一の正準イベント列と最終状態を生成しなければならない（SHALL）。実行識別子や実時間等の管理メタデータの一致は要求しない。

#### Scenario: Independent repeated runs
- **WHEN** 同一条件で独立した実行を2回行う
- **THEN** 管理メタデータを除いたイベント列と最終状態が一致し、比較結果を検証者が確認できる

#### Scenario: Simultaneous events
- **WHEN** 同時刻に複数のイベントが処理対象になる
- **THEN** 処理順序が同一条件で安定し、その後の状態も再現する

### Requirement: Execution provenance
システムは各実行に、固定入力、シード、エンジン版、定義版、実行環境、期間条件と完了状態を関連づけなければならない（SHALL）。

#### Scenario: Inspect a saved run
- **WHEN** 管理者が保存済み実行を確認する
- **THEN** 再実行条件と結果の由来を特定できる

### Requirement: Consistent canonical history
システムは保存前の検査で、無効な状態遷移、参照切れ、時刻逆行、二重の資源割当を検出しなければならない（SHALL）。

#### Scenario: Invalid transition evidence
- **WHEN** 検証用に不正な遷移や参照切れを含む履歴を検査する
- **THEN** 問題のイベントと検査理由を報告し、その結果を有効な正常完了として扱わない

### Requirement: Frozen completed run
システムは完了済み実行の入力・正準履歴・最終状態を参照操作によって変更してはならない（MUST NOT）。

#### Scenario: Read after completion
- **WHEN** 第12週終了後に記録や社員経験を繰り返し取得する
- **THEN** 時間と正準履歴は変化せず、新しい経験は発生しない

#### Scenario: Changed rules
- **WHEN** 管理者が別の規則で実行する
- **THEN** 元の完了済み実行を保持したまま、異なる条件の実行として識別される

### Requirement: Explicit failed execution
システムは実行・整合性検査・保存の失敗を明示し、部分結果を正常完了として公開してはならない（SHALL）。自動修復や途中再開は要求しない。

#### Scenario: Interrupted persistence
- **WHEN** 結果保存の途中で障害を発生させる
- **THEN** 成功結果として利用できず、障害が報告され、既存の完了済み実行は保持される
