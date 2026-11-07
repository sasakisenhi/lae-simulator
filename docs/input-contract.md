# 固定世界入力契約 1.0

本契約はOpenSpec変更 `build-reproducible-simulation-foundation` のTask 1.2で導入する。入力の読込みと実行を分離し、`validate-world` は検証済みの不変型を構築するだけで、候補選択、イベント生成、状態遷移、保存、公開ログ生成を行わない。

## 構造

主要なトップレベル項目はすべて必須である。未実装機能も暗黙の既定値にせず、`patches`、`checks`、`response_models`を空配列として明示する。これらに要素を入れる定義は、対応タスクまで`unsupported-definition`として拒否する。

| 項目 | 内容 |
|---|---|
| `schema_version`, `exercise_id`, `fixture`, `seed` | 契約版、教材ID、合成適合教材の宣言、固定seed |
| `source_manifest` | 出典ID、版、根拠分類、取得状態、利用条件 |
| `documents`, `issue` | 固定テキスト、内容SHA-256、対象Issueと本文参照 |
| `world_facts` | 世界側で保持する情報。本人の初期知識へ自動追加しない |
| `references` | 収録済み、未収録、未解決を区別する有限参照表 |
| `actors`, `tools` | 本人の初期知識、利用ツール、権限、対応操作 |
| `access_outcomes` | 収録範囲とは独立した、本人ごとの資料アクセス結果 |
| `policies` | 候補定義とは別の決定的優先規則 |
| `candidates` | Design D3の目的、表示名、必要情報、利用条件、操作、対象、前提、結果、知識効果、時間・根拠参照 |
| `time_models` | 単位、変数、式、合成根拠、不確実性、適用範囲 |
| `timeline` | 開始、期限、観測窓、整数tickの単位 |
| `disclosure` | コード側固定上限を狭める役割別allowlist |
| `retention` | 固定runを後続検査で参照するための最小保持条件 |

任意項目は`references[].target_id`だけである。`coverage=recorded`では必須、`unrecorded`または`unresolved`では指定禁止とする。この条件付き項目により、未収録・未解決を実在しない対象へ変換しない。

## ID・版・参照

全エンティティIDは一つの名前空間で一意とする。source、document、Issue、world fact、reference、actor、knowledge claim、tool、candidate、policy、time model間の重複を拒否する。参照先は定義済みIDへ解決し、sourceを参照するdocument・Issue・referenceの版はmanifestの版と一致しなければならない。

操作は契約版が対応する有限集合から選ぶ。schema 1.0は`issue.read`と`document.read`だけを受理する。候補は本人が保持するtool、対象resource、必要permission、宣言済みaccess outcome、対象版、根拠reference、time modelを参照する。Issue IDや教材名による分岐はない。

## 認識・アクセス・収録範囲

- `world_facts`は世界側情報であり、`actors[].initial_knowledge`とは別の型・領域に置く。
- 初期知識と知識効果は根拠IDを必須とし、未定義根拠を拒否する。
- access outcomeは`available`または`unavailable`であり、資料がfixture内に存在するかとは別に記録する。
- reference coverageは`recorded`、`unrecorded`、`unresolved`。API上はそれぞれ`resolved`、`out-of-scope`、`unknown`となる。未定義reference IDだけが`absent`である。
- permissionはvisibilityや役割上限を拡張しない。管理専用documentへのactor read permissionと、固定上限を越えるallowlistを拒否する。

## 固定化とエラー

受理したJSONはUTF-8、object key昇順、余分な空白なしで正規化し、全入力のSHA-256を`content_id`とする。object keyの並びは識別値へ影響しないが、値の変更は影響する。重複JSON key、非対応フィールド、型不一致、非対応版、内容digest不一致、重複ID、参照切れ、版不一致、非対応操作、権限不足、可視性矛盾、公開上限超過を、`path`、`code`、`message`付きで拒否する。

## 設計判断

入力形式はTask 1.1で選定したJSONを継承し、検証後はfrozen dataclassとenumへ変換する。JSON Schemaだけではsource版一致、候補からactor/tool/permission/accessへの参照、役割上限との積集合といった意味検査が別途必要になるため、schema 1.0は標準ライブラリによる一つの検証器で構造と意味をまとめて検査する。外部依存を追加せず、エラーのpathと理由を同じ契約で返せる。

主要項目を任意にして既定値を補う案は採用しない。固定入力の省略が実行環境によって異なる意味へ変わることを避け、未対応版・未対応フィールドも暗黙変換せず拒否する。候補と決定規則は別配列にし、`policies[].actor_id`で本人へ関連づける。これにより候補カタログ自体へ固定実行経路を埋め込まず、別教材でも同じ検証処理を使える。

## CF0

`fixtures/cf0/world.json`は合成のengine conformance fixtureである。埋込み固定テキスト、合成Issue、一人の本人、IssueRead候補、決定的優先規則、1tickの合成時間、期限2tick、最小の公開条件を持つ。世界側だけが保持するfact、本人がアクセスできない固定document、未収録reference、未解決referenceを含み、これらの区別を検査できる。

CF0は架空企業設定、特定チーム、実在OSS、外部Issue、ネットワーク、文書サービス、生成サービスを参照しない。これは実測データ、正式な企業資料、ケーススタディの結果ではなく、汎用入力処理の合成適合教材である。
