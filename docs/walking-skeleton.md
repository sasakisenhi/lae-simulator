# Task 1.3 Walking Skeleton

Task 1.3は、CF0を入力検証から調査者向け公開ログまで一つの汎用経路で処理する。CF0専用のIssue IDや内容による分岐は持たない。

## 実行経路

1. Task 1.2のLoaderがJSONを検証し、不変の`WorldDefinition`を作る。
2. Policyが本人の知識、ツール、権限、版、アクセス結果から、固定優先規則の最初の実行可能候補を選ぶ。
3. Engineが操作を開始し、`(due_tick, priority, insertion_sequence, scheduled_id)`順のキューへ完了と期限を予約する。
4. reducerが予約・消費・操作完了・終了を正準イベントとして適用する。通常実行と再生は同じreducerを使う。
5. Validatorが初期状態と正準履歴から状態を再生し、派生最終状態と一致することを確認する。
6. Projectorが固定のinvestigator上限と入力allowlistの積集合を適用し、検査済みの公開イベントだけを合成ログへ変換する。
7. Storeがrunを新規ディレクトリへ保存し、再取得時にdigest、入力ID、規則ID、正準再生、派生状態、公開投影を再検査する。

CF0では本人が`issue.read`を1tick実行し、表示対象と取得知識が更新される。期限2tickで、業務結果は有効な`INCOMPLETE/deadline`となる。PR提出がないことは内部エラーではない。

## 正準イベントと状態

最小履歴は候補選択、操作開始、予約、消費、操作完了、期限消費、終了を含む。予約・消費は管理用イベントであり、公開ログへ投影しない。操作開始・完了は`synthetic=true`かつ`source_class=tool-shaped`として公開でき、実ツールの実測ログとは表示しない。

イベントの順序、時刻逆行、候補・版・操作の不一致、予約なし消費、二重予約、完了ライフサイクル、過去に存在しない因果参照をreducerが拒否する。状態の任意差分は受理せず、イベント種別ごとの許可された効果だけを適用する。

## 保存物

各runディレクトリは次を持つ。

- `manifest.json`: 入力・規則・エンジン・Python・lockfile・時間条件・各artifact digest
- `world.json`: 実行に使用した正規化済み固定入力
- `initial-state.json`: 再生の初期状態
- `events.jsonl`: 順序付き正準イベント列
- `final-state.json`: 再生結果と照合する派生状態
- `public-log.json`: 調査者向けの合成公開投影
- `validation.json`: 内部整合性検査結果

run IDは固定入力ID、seed、schema版、エンジン版から実行前に決定的に生成し、初期状態、全正準イベント、公開記録、manifestへ関連づける。同じ保存先に同じrun IDが存在する場合は上書きせず、管理用のpersistence failureとして報告する。

## 失敗境界と非対象

有効な`INCOMPLETE`は終了理由を持つ業務結果であり、入力拒否、履歴不正、再生不一致、保存失敗、公開境界違反とは異なる。後者は`internal-error`または`INVALID`として有効公開を止める。

Task 1.3ではAI、LLM、仮想変更、modeledチェック、割り込み・再開、相談、仮想PRを実装しない。これらを模したイベントも生成しない。Walking Skeletonの成功はMVP全体の完成を意味しない。
