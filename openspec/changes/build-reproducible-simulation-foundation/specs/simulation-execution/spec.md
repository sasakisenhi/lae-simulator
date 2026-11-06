# Spec Delta

## Purpose

固定された教材と本人条件から、Issue着手からPR提出までの行動と環境への作用を実行する。情報取得と解釈、非同期作業、仮想変更とその証拠を結び、再現可能で検査可能な正準履歴を保存する。

## ADDED Requirements

### Requirement: SE01 Code change lifecycle
システムは、Issue着手から調査、方針選択、仮想変更、確認、PR提出までを状態変化として表現しなければならない（SHALL）。

#### Scenario: Submit a virtual PR
- **WHEN** 教材の提出条件を満たす変更を本人が提出する
- **THEN** 対象Issue、差分版、提出主体、説明を持つ仮想PRを生成し、レビュー・マージを実行しない

### Requirement: SE02 Explainable background influence
システムは、設定した割り込み・依存等の外部作用を、その発生条件と対象への作用へ追跡可能にしなければならない（SHALL）。

#### Scenario: External interruption
- **WHEN** 定義した外部作用が実行中の作業に影響する
- **THEN** 発生イベント、通知内容、停止・残作業・再開への作用を管理者が照合できる

#### Scenario: Dependency release is stale or unobserved
- **WHEN** 依存が解除されても本人への通知が未確認である、または解除前の完了イベントが中断によって失効している
- **THEN** 環境の依存状態と本人の認識を区別し、未確認情報を判断へ使わず、失効イベントを再作用させない

### Requirement: SE03 Knowledge bounded decisions
システムは、本人の行動選択を、その時点の本人情報と認識に基づかせなければならない（SHALL）。

#### Scenario: Hidden cause does not guide action
- **WHEN** 非公開の原因または将来応答時刻だけを変え、比較時点の論理時刻・本人が観測したイベント列・本人情報が同一である
- **THEN** その共通観測区間の行動選択に隠れた情報を使わない。応答到着や観測できる待機経過によって観測条件が異なった後の行動差は禁止しない

### Requirement: SE04 Action feasibility separation
システムは、操作前提を満たすが目的に不適切な行動を、正解でないことだけを理由に拒否してはならない（MUST NOT）。

#### Scenario: Wrong but feasible edit
- **WHEN** 本人が存在する編集可能な箇所に不適切な変更を選ぶ
- **THEN** 操作前提が一致すれば変更でき、その影響を後続の確認で調べられる

#### Scenario: Impossible edit
- **WHEN** 存在しない対象または権限のない対象への変更を要求する
- **THEN** 実行を拒否し、状態を変更せず理由を記録する

### Requirement: SE05 Revisable actor knowledge
システムは、知識項目ごとに未知・情報取得・暫定解釈・本人による確認を区別し、根拠に基づく撤回・修正を記録しなければならない（SHALL）。

#### Scenario: Reading does not imply understanding
- **WHEN** 本人が仕様書を開く
- **THEN** 情報取得を記録しても、その内容の正しい理解や世界の真実との一致を自動認定しない

#### Scenario: Counterexample revises belief
- **WHEN** 本人が暫定解釈と矛盾する確認結果を取得する
- **THEN** 元の解釈と根拠を残して撤回・修正でき、再調査の候補を再評価する

### Requirement: SE06 Causal action effects
システムは、操作の結果を参照した環境版へ作用させ、その結果を次の行動候補へ反映しなければならない（SHALL）。

#### Scenario: Search and navigation
- **WHEN** 本人が対象版の収録コードを検索して結果を開く
- **THEN** 実在する一致箇所と参照版を返し、表示対象と取得情報を更新する

#### Scenario: Tool availability changes the route
- **WHEN** 定義元移動機能がなくテキスト検索だけ利用できる
- **THEN** 利用不能な移動を成功させず、検索等の実行可能な候補から次の操作を選ぶ

### Requirement: SE07 Async collaboration
システムは、AI・同僚の応答を、タスク・質問・依存・権限・応答規則に基づく非同期結果として扱わなければならない（SHALL）。

#### Scenario: Approval blocks an AI task
- **WHEN** AIの次の作業が許可範囲を超える
- **THEN** 承認依頼と待機を記録し、承認まで対象変更を行わず、拒否時は定義した代替または保留へ進む

#### Scenario: Independent human work
- **WHEN** AIが実行中で本人に独立作業がある
- **THEN** 本人はその作業を進められ、AIの経過時間を本人の純待機時間へ置き換えない

### Requirement: SE08 Notification lifecycle
システムは、通知の発生・到着・本人の認知・閲覧・対応を区別しなければならない（SHALL）。

#### Scenario: Delayed attention
- **WHEN** 本人の作業中に通知が到着し、後で確認する
- **THEN** 到着時点で内容を本人の判断へ渡さず、確認時刻と対応時刻を別に記録する

### Requirement: SE09 Work interruption and resumption
システムは、中断時の作業文脈と残作業を保持し、再開時に何を確認し直したか追跡可能にしなければならない（SHALL）。

#### Scenario: Resume a suspended task
- **WHEN** 中断した作業を本人が再開する
- **THEN** 元の目標・版・残作業を参照でき、再開の確認作業と画面移動を区別して記録する

### Requirement: SE10 Resource and time accounting
システムは、人間の能動作業、非同期実行、待機、画面切り替え、タスク切り替え、再開作業の時間を区別して整合的に記録しなければならない（SHALL）。

#### Scenario: Parallel activity
- **WHEN** 人間とAIが同時に別作業を進める
- **THEN** 区間の重なりを保持し、人間の能動作業を二重割当せず、経過時間を単純加算しない

#### Scenario: Resumption is already explicit
- **WHEN** 再開のための読み直し時間を操作として計上する
- **THEN** 同じ内容の汎用再開コストを重ねて計上しない

### Requirement: SE11 Versioned virtual workspace
システムは、仮想変更の基準版、変更前後、対象要素、主体、適用・撤回・統合の結果を追跡可能にしなければならない（SHALL）。

#### Scenario: Stale AI patch
- **WHEN** AI成果の基準版と統合先が一致せず変更箇所が競合する
- **THEN** 無条件で上書きせず競合として保留し、解決または再実行なしに統合成功としない

#### Scenario: Index invalidation
- **WHEN** 変更で静的参照表の前提が壊れる
- **THEN** 対象参照を無効またはUNKNOWNとし、再確認されるまで最新関係として使わない

### Requirement: SE12 Check evidence modes
システムは、チェックの入力版、規則、判定、適用限界、modeledまたはexecutedの根拠種別を記録しなければならない（SHALL）。

#### Scenario: A modeled check passes
- **WHEN** 模擬規則が限定された保存条件を満たすと判定する
- **THEN** modeledのPASSと検査範囲を示し、実VS Code動作・ビルド成功を保証しない

#### Scenario: Unsupported check
- **WHEN** チェックが対象変更または条件に対応していない
- **THEN** UNKNOWNを返し、変更IDの存在だけでPASSにしない

### Requirement: SE13 Explicit run outcomes
システムは、PR提出、情報不足等の未完了、作業中止、期限到達と、内部エラーによる無効実行を区別しなければならない（SHALL）。

#### Scenario: Waiting beyond the deadline
- **WHEN** 必須情報が未取得で代替作業もなく、応答前に期限へ達する
- **THEN** 未解決依存・残作業・未処理イベントを残す有効な未完了結果を保存し、PRを強制しない

#### Scenario: Submission is not correctness
- **WHEN** 本人が教材の提出条件を満たしてPRを作成する
- **THEN** 提出とチェック結果を別に記録し、提出だけで変更の正しさを認定しない

### Requirement: SE14 Reproducible execution
システムは、同じ固定入力・規則・シード・エンジン版・対応環境から同じ正準履歴と最終状態を生成しなければならない（SHALL）。

#### Scenario: Independent repeated runs
- **WHEN** 同一条件で独立した実行を2回行う
- **THEN** 実時間等の管理メタデータを除く正準列・最終状態が一致する

#### Scenario: Simultaneous events
- **WHEN** 同時刻に応答、作業完了、期限が発生する
- **THEN** 定義した安定順序で処理され、繰り返し実行でも結果が一致する

### Requirement: SE15 Execution provenance
システムは、入力識別値、シード、規則・定義・エンジン・実行環境の版と終了状態を各実行へ関連づけなければならない（SHALL）。

#### Scenario: Inspect a saved run
- **WHEN** 管理者が保存済み実行を確認する
- **THEN** 再実行条件、教材版、時間仮定、モデルの保証境界を特定できる

### Requirement: SE16 Consistent canonical history
システムは、無効な遷移、参照切れ、版不一致、時刻逆行、資源の二重割当を検出しなければならない（SHALL）。

#### Scenario: Inject invalid history
- **WHEN** 検査用履歴へ不正遷移または版不一致を混入する
- **THEN** 対象イベントと理由を示してINVALIDと判定する

### Requirement: SE17 Frozen completed run
システムは、終了後の参照・質問によって固定入力・正準履歴・最終状態を変更してはならない（MUST NOT）。

#### Scenario: Queries in a different order
- **WHEN** 保存済み結果へ異なる順序でログ取得と質問を行う
- **THEN** 過去の事実と状態は不変であり、新しい経験を追加しない

#### Scenario: Changed model
- **WHEN** 管理者が規則または介入条件を変更して再実行する
- **THEN** 元結果を保持し、変更点と追加仮定を持つ別条件の結果として識別する

### Requirement: SE18 Execution failure report
システムは、内部処理・整合性検査・保存の失敗を、対象と理由を持つ管理用の失敗記録として報告しなければならない（SHALL）。

#### Scenario: Report a persistence failure
- **WHEN** 結果保存の途中で障害が発生する
- **THEN** 保存成功とは別の失敗記録に対象と理由を残し、業務上の未完了と区別する

### Requirement: SE19 Behavioral responsiveness
システムは、本人知識・取得情報・アクセス・応答条件・ツール機能の影響を、制御した条件対で検証可能にしなければならない（SHALL）。

#### Scenario: Change a relevant condition
- **WHEN** 決定的な規則と固定時間を使い、知識、反例情報、資料アクセス、AI・同僚応答時間、または操作機能を一つだけ変えた最小条件対を実行する
- **THEN** 他の入力が同じである証拠と、変更条件に対応する最初の候補・判断・待機の分岐を特定できる。3経路デモの比較だけで代替しない

#### Scenario: No forced variation
- **WHEN** 変更条件が選択に影響しない実行、または別シードで同じ結果が出る実行を得る
- **THEN** 結果差を作るために追加の問題や分岐を挿入しない

### Requirement: SE20 Canonical state reconstruction
システムは、初期スナップショット・固定入力と規則・順序付き正準イベント列を基礎として状態を再生し、保存状態との不一致をINVALIDとして扱わなければならない（SHALL）。

#### Scenario: Stored state contradicts replay
- **WHEN** 保存された最終状態の版、知識、終了理由、またはキューを改変して再生状態と照合する
- **THEN** 不一致を対象付きで検出し、その実行を有効結果と判定しない

### Requirement: SE21 Scheduled event lifecycle
システムは、イベント予約・取消・失効とその順序を再生可能な正準記録として保持しなければならない（SHALL）。

#### Scenario: Replay a cancelled completion
- **WHEN** 作業の完了予約後に中断・取消を行い、保存履歴を再生する
- **THEN** 同じ予約と取消・失効状態を復元し、古い完了の効果を適用せず、終了時の未処理キューが一致する

### Requirement: SE22 Invalid result publication prevention
システムは、内部失敗または整合性違反のある部分結果を、有効な提出・未完了結果として公開してはならない（MUST NOT）。

#### Scenario: Failure does not publish a valid run
- **WHEN** 保存途中障害、再生不一致、または不正遷移を検出する
- **THEN** 有効公開を停止し、既存の有効結果を変更せず、調査者向け取得から無効な部分結果を返さない
