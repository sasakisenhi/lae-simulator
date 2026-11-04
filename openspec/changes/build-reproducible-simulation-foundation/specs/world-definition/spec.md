# Spec Delta

## Purpose

架空企業の業務を、調査結果や改善策に合わせて途中変更することなく実行するため、世界定義と実行前提を固定し識別する。正式な企業設定と開発検証用データを区別し、実行結果の由来を確認できるようにする。

## ADDED Requirements

### Requirement: Explicit world inputs
システムは組織・社員、固定背景情報、業務規則、初期状態、背景工程からの作用を明示した世界定義を入力できなければならない（SHALL）。

#### Scenario: Load a minimal world
- **WHEN** 管理者が有効な最小世界を読み込む
- **THEN** 実行に用いる社員、業務規則、初期状態、背景作用と背景情報を確認できる

### Requirement: Reject invalid definitions
システムは未定義の社員への参照、不正な状態、非対応の定義版を含む入力を実行前に拒否しなければならない（SHALL）。

#### Scenario: Invalid reference
- **WHEN** Issueの担当者が世界定義に存在しない
- **THEN** 対象箇所と理由を示して入力を拒否し、成功した実行結果を生成しない

#### Scenario: Unsupported version
- **WHEN** 非対応の定義版が入力される
- **THEN** 非対応であることを明示し、暗黙の変換や既定値への置換を行わない

### Requirement: Identifiable frozen inputs
システムは実行で使用した世界定義、規則、初期条件を固定し、その内容を識別可能にしなければならない（SHALL）。

#### Scenario: Input changes after execution
- **WHEN** 実行完了後に元の世界定義ファイルが変更される
- **THEN** 保存済み実行は元の入力を保持し、新しい入力とは区別できる

### Requirement: Predetermined study timeline
システムは12週間を助走4週、履歴形成4週、主観測4週に分けた時間条件を実行前に固定しなければならない（SHALL）。

#### Scenario: Period boundaries
- **WHEN** 12週間の実行が完了する
- **THEN** 最後の4週間が主観測期間として記録され、発生した問題による期間の自動選別は行われない

### Requirement: Fixture provenance
システムは開発検証用世界を正式なLAE設定と識別できなければならない（SHALL）。

#### Scenario: Unprovided company material
- **WHEN** 開発検証用世界を使用して実行する
- **THEN** 管理者向け入力・出力に検証用であることが明示され、正式資料に裏付けられた設定とは扱われない

### Requirement: No required problem outcome
世界定義は特定の課題の発生や特定改善策の有効性を実行成功の必須条件にしてはならない（MUST NOT）。

#### Scenario: Uneventful valid world
- **WHEN** 有効な定義による実行に、明確なボトルネックが発生しない
- **THEN** その理由だけで実行を失敗扱いしたり、問題が発生するまで結果を差し替えたりしない
