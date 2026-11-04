# Tasks

この一覧は基盤の実装のみを扱う。ケーススタディ全体、LLMヒアリング、介入比較の完了を意味しない。D1～D8はdesign.mdの決定を参照する。

## 1. 入力と最小世界

- [ ] 1.1 D1のローカルパッケージとテスト実行入口を用意し、対応ランタイムと実行手順を文書化する。確認: クリーンな環境でパッケージの読込みとテスト入口が動作する。
- [ ] 1.2 `world-definition/Explicit world inputs`、`Reject invalid definitions`を満たす入力読込み・参照/版/状態検証を実装する（D4）。確認: 有効世界は受理され、未定義社員、不正状態、非対応版は理由つきで実行前に拒否されるテスト。
- [ ] 1.3 `world-definition/Fixture provenance`、`No required problem outcome`用の明示的な検証世界を用意する（D7）。確認: 検証用表示、規則・背景情報の説明があり、問題発生を必須にしない入力を受理できる。
- [ ] 1.4 `world-definition/Predetermined study timeline`の時間・カレンダー境界を実装する（D3）。確認: 28/56/84日境界、業務時間外、最終時刻の扱いをテストし、主観測期間が結果に依存しない。

## 2. 決定的な業務実行

- [ ] 2.1 `simulation-execution/Reproducible execution`の基礎となる整数時間、同時刻順序、用途別シード乱数を実装する（D3）。確認: 同時刻を含む同一入力の順序が安定し、実時間やPython hashの変化に依存しないテスト。
- [ ] 2.2 `simulation-execution/Code change lifecycle`のIssue受領からマージまでの状態遷移と資源制約を実装する（D2）。確認: 正常、レビュー修正、CI失敗/再実行、複数Issueの待機、未完了終了の履歴テストと状態図の文書。
- [ ] 2.3 `simulation-execution/Knowledge bounded decisions`の限定された判断入力と判断根拠の記録を実装する（D2/D4）。確認: 本人に伝わらない出来事を変えても、その情報を前提とした判断が発生しないテスト。
- [ ] 2.4 `simulation-execution/Explainable background influence`の企画変更、QA起因修正Issue、依存待機/解除、割り込み/再開を実装する（D2）。確認: 各作用と原因参照、通知内容、既存マージ履歴の保持をテストし、背景モデルの限界を文書化する。
- [ ] 2.5 `simulation-execution/Consistent canonical history`の検査を実装する（D5）。確認: 不正遷移、参照切れ、時刻逆行、二重資源割当を注入し、対象イベントと理由が報告される。

## 3. 共通履歴からの記録・経験形成

- [ ] 3.1 `evidence-projection/Observable work records`、`Shared evidence origin`を満たすIssue/PR/レビュー/CI/背景痕跡の投影と管理用根拠対応を実装する（D4）。確認: 業務側IDで時系列を取得でき、全記録の根拠参照が解決するテスト。
- [ ] 3.2 `evidence-projection/Employee perception boundary`、`Fixed employee evidence package`の社員別経験を形成する（D4）。確認: 直接経験/伝聞、社員間の知覚差、限定通知をテストし、未伝達原因と未登録の開始前エピソードが含まれない。
- [ ] 3.3 `evidence-projection/Projection consistency report`の根拠・知覚範囲検査を実装する（D7）。確認: 偽造経験、欠落根拠、他社員情報の混入でFAILを返し、未対応の意味評価をUNKNOWNまたは対象外とする。
- [ ] 3.4 `evidence-projection/Role bounded disclosure`、`Retention bounded historical access`の公開処理を実装する（D6）。確認: 管理者/社員/調査者の許可と拒否、未知役割、保存期限、主観測外の取得をテストし、本文・参照・メタデータに非公開情報が漏れない。配布運用と認証を持たない境界を文書化する。

## 4. 固定結果の保存と利用入口

- [ ] 4.1 `world-definition/Identifiable frozen inputs`、`simulation-execution/Execution provenance`を満たす入力スナップショットとmanifest保存を実装する（D5）。確認: 元入力の変更後も使用入力・版・シード・環境・期間を確認できるテスト。
- [ ] 4.2 `simulation-execution/Frozen completed run`、`Explicit failed execution`の公開・失敗境界を実装する（D5）。確認: 既存結果への上書き拒否、保存中断/検査失敗時の非正常公開、繰り返し参照での不変性、別規則の別実行をテストする。
- [ ] 4.3 読込み、実行、検査、役割別出力のCLIを統合する（D1/D6）。確認: 文書の手順で検証世界の実行と成果物取得ができ、不正入力・権限拒否・不完全結果は非成功終了となる。

## 5. 縦断受入と証拠

- [ ] 5.1 独立プロセスで同じ12週間条件を2回実行する縦断テストを追加する（`simulation-execution/Reproducible execution`、D7）。確認: 管理メタデータを除く正準列・最終状態・投影が一致し、全件の根拠と期間境界の検査が通る。別シード実行は識別できるが、結果差の必須保証はしない。
- [ ] 5.2 要件別のテスト対応と実行証拠、未検証の仮定、既知の限界を受入報告にまとめる（D7/D8）。確認: 各spec要件に証拠または明示的な未確認状態があり、機械的整合性を企業の妥当性・LLM発言・改善効果の保証に読み替えていない。実装中に契約を改訂した場合は影響する投影・テストを再検証する。

## Workflow follow-up

- 基盤の検証後、正式企業資料の取り込み、記憶・認識形成とヒアリング、調査機能、介入と評価を別変更として検討する。
- 後続介入ではベースラインを保持し、モデル変更と追加仮定を明示して比較可能性を確認する。評価できない効果は生成しない。
