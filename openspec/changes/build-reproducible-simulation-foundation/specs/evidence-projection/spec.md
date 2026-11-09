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
システムは、公開設定で拡張できない役割別上限を適用し、管理専用の原因・正解・未観測の予約イベントを調査者と生成器へ、当人の知識範囲外の情報を当人の生成器へ漏洩してはならない（MUST NOT）。調査者に許可された他者の操作記録や、公開記録から推論できる関係は禁止対象にしない。

#### Scenario: Interview context
- **WHEN** インタビュー用コンテキストを構成する
- **THEN** 当人の許可情報だけを含め、他社員だけの知識、内部の正解、非公開の行動規則を渡さない

#### Scenario: Unknown role
- **WHEN** 未定義または未許可の役割で取得する
- **THEN** 拒否し、管理者情報へフォールバックせず、非公開情報の存在を漏らさない

#### Scenario: Misconfigured public allowlist
- **WHEN** 公開設定が管理専用情報を調査者出力へ、または他人だけの知識・未観測予約を当人の生成器入力へ追加しようとする
- **THEN** 設定の拒否または安全な拒否応答により、本文・根拠ID・メタデータ・エラーを含め非公開情報を提供しない

#### Scenario: Observable causality remains available
- **WHEN** 許可された操作記録に質問、承認、AI再開の時刻と公開可能な関連IDがある
- **THEN** 記録と関係を取得でき、調査者が因果仮説を推論できることだけを理由に秘匿しない

#### Scenario: Hidden search profile before observation
- **WHEN** 固定検索範囲だけが異なるScenario 1.4.0の実行を、検索前の同時刻・同じ本人観測と公開可能な接頭履歴で比較する
- **THEN** 本人パッケージと公開証拠が本文・ID・digest・件数・メタデータ・エラーを含め一致する。未観測のプロファイルやそのdigestを転記せず、本人・公開IDの材料にも使わない

#### Scenario: Irrelevant search scope change
- **WHEN** 一致を持たないファイルだけを検索範囲へ追加し、同時刻の取得結果・本人観測・公開可能な履歴が同一である
- **THEN** 本人・公開出力の内容と識別子が一致する。検索範囲を資料公開権限や調査者用の証拠検索範囲へ流用せず、管理用の入力識別値やprofile digestを公開しない

### Requirement: EP07 Retention bounded historical access
システムは、調査の重点範囲と参照可能範囲を分離し、固定入力で定義した最小の保持条件と権限に基づいて過去記録を提供しなければならない（SHALL）。任意の保持規則を実行する汎用ポリシー機構は要求しない。

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

#### Scenario: Leading question contains a new event
- **WHEN** 質問が固定本人情報にない日時・行動を既成事実として提示する
- **THEN** 質問文を過去の証拠として採用せず、否認・不明・記憶なし等で回答できる

### Requirement: EP09 Interview epistemic limits
システムは、回答で経験・本人の解釈・推測・不明・記憶なしを区別できなければならない（SHALL）。

#### Scenario: No remembered reason
- **WHEN** 当時の理由が本人向け情報にも記憶にもない
- **THEN** 不明または記憶なしと答えられ、一般的な行動方針から具体的な過去の出来事を断定しない

#### Scenario: Grounded misunderstanding
- **WHEN** 当時の誤認が固定本人情報に記録されている
- **THEN** 本人の認識として説明でき、世界の客観的事実と一致しないことだけで生成ミスと分類しない

### Requirement: EP10 Interview validation record
システムは、各回答試行に、使用した固定本人情報・根拠、生成器とプロンプトの版、質問・回答、検査結果・限界を関連づけた管理用監査記録を固定しなければならない（SHALL）。

#### Scenario: Trace an answer attempt
- **WHEN** 回答が生成され、採用、棄却、または意味判定不能となる
- **THEN** 当該本人パッケージの版、根拠、生成条件、回答、検査理由を照合でき、意味判定不能はUNKNOWNとして残る

### Requirement: EP11 Projection consistency report
システムは、投影の根拠・知覚・公開範囲の検査結果を、対象と理由付きで報告しなければならない（SHALL）。

#### Scenario: Forged experience
- **WHEN** 根拠のない経験または他人だけの知識を検査入力へ混入する
- **THEN** 違反箇所を報告し、有効な投影として公開しない

#### Scenario: Unsupported external validity
- **WHEN** 実開発者への妥当性や実ツールの効果を整合性検査で評価しようとする
- **THEN** UNKNOWNまたは対象外とし、整合性PASSから効果実証を導かない

#### Scenario: Derived information contradicts canonical facts
- **WHEN** 根拠イベントIDは存在するが、投影の対象版・操作内容が再生状態と矛盾する
- **THEN** 派生情報の不一致を検出して公開を止め、参照IDが解決するだけで有効としない

#### Scenario: Forged scoped search evidence
- **WHEN** 検索の派生状態または投影に、対象範囲の実バイトと検証済み参照対応から得られない結果を混入する
- **THEN** 正準再生との不一致を検出し、有効公開を停止する。artifact digestの再計算や有効な参照IDの存在だけで受理しない

### Requirement: EP12 Investigable evidence retrieval
システムは、調査者がIssue、時刻、操作、成果物を起点に許可された関連証拠を追加取得できなければならない（SHALL）。

#### Scenario: Follow an alternative hypothesis
- **WHEN** 調査者が待機の原因を調べるため通知・承認・並行作業の記録を要求する
- **THEN** 固定履歴にある関連証拠を取得でき、取得順序を変えても内容が変わらない

#### Scenario: Retrieval crosses a protected boundary
- **WHEN** 関連IDの追跡に非公開記録、未記録の詳細、または権限外の資料が含まれる
- **THEN** 許可された証拠だけを返し、非公開対象の存在・件数・内容を漏らさず、欠落を新しい事実で補わない

### Requirement: EP13 Investigation acceptance record
システムの調査可能性受入では、管理情報を見ない別の評価主体が公開証拠と合成インタビューから仮説・競合説明・追加調査・判断更新を根拠付きで記録できることを検証しなければならない（SHALL）。実人間を必須とはせず、管理情報から隔離された評価主体の代替を認める。

#### Scenario: Evidence is inconclusive
- **WHEN** 第三者がログとインタビューを調べても必要な根拠が不足する
- **THEN** 判断保留と限界を受入記録に残せ、特定原因の発見や改善策の採用を合格条件にしない

#### Scenario: Blind investigation and sealed assessment
- **WHEN** 調査者用証拠と取得・質問手段が揃い、別の評価主体が管理用真因・状態・正解経路を見ずに調査する
- **THEN** 事前固定した手順で調査記録を封印してから検証者が照合し、管理情報の閲覧があればブラインド試験のPASSにしない

### Requirement: EP14 Observation coverage limits
システムは、提供する証拠の収録粒度と推論限界を明示しなければならない（SHALL）。

#### Scenario: Unmodeled GUI details
- **WHEN** 記録していないメニュー操作や心理的負担について質問する
- **THEN** 操作結果から詳細や負担を断定せず、モデル外または根拠不足と示す

#### Scenario: Scoped no hit is not global absence
- **WHEN** 固定検索範囲で無ヒットだった記録を本人情報または公開証拠として取得する
- **THEN** 記録した検索範囲内での結果という限界を示し、Workspace全体や実在OSSでの不存在へ拡張しない。非公開の範囲パス集合・件数・digestで限界を説明しない

### Requirement: EP15 Rejected interview publication prevention
システムは、検出した根拠なしの具体的発言、情報漏洩、固定本人情報では説明できない回答矛盾を有効回答として提供してはならない（MUST NOT）。

#### Scenario: Fabricated or contradictory answer
- **WHEN** 検査で創作・漏洩・根拠のない具体的事実主張の矛盾を検出する
- **THEN** 回答を棄却し、固定本人情報を変えない制限付き再生成または回答不能とする

### Requirement: EP16 Cross question factual consistency
システムは、再質問・言い換え質問への具体的事実主張を、同じ固定本人情報と既存の回答監査記録に照らして検査可能にしなければならない（SHALL）。

#### Scenario: Paraphrase changes an unsupported fact
- **WHEN** 同じ場面についての言い換え回答が対象ファイルや行動理由を根拠なく変更する
- **THEN** 逐語差ではなく主張と根拠の不整合を検出し、EP15に従って制御する

#### Scenario: Fixed mistaken or uncertain memory
- **WHEN** 固定情報に誤認・曖昧な記憶がある、または回答が不明・記憶なし・推測である
- **THEN** 根拠と認識種別に沿った差を許容し、客観的真実との不一致や表現差だけで矛盾としない

### Requirement: EP17 Independent acceptance verdicts
システムの受入では、技術的整合性・行動反応性・調査可能性を、それぞれの前提が揃った時点で独立に判定・記録しなければならない（SHALL）。

#### Scenario: Unready and inconclusive are different
- **WHEN** 必要な実行物・証拠・隔離条件がない試験、または実施したが判断に十分な証拠がない試験を報告する
- **THEN** 前者はNOT READY、後者はINCONCLUSIVEとし、成立した期待結果はPASS、観測された要件違反はFAILとして、他試験の判定待ちを前提にしない

### Requirement: EP18 MVP completion gate
MVPの完成判定は、全必須要件の証拠と三種類の受入結果がPASSである場合に限りPASSとしなければならない（SHALL）。

#### Scenario: Unverified mandatory behavior remains
- **WHEN** 必須要件または受入試験にFAIL、NOT READY、INCONCLUSIVE、未確認が残る
- **THEN** MVP全体をPASSにせず、阻害要件と不足証拠を示す。対象外の実機検証や経験的妥当性のUNKNOWNは別に記録する
