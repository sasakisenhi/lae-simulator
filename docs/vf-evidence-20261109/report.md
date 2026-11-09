# VF MVP完成判定の集約（2026-11-09）

対象: `build-reproducible-simulation-foundation` / Task 7.4 / 全59 WD・SE・EP要件、103 Scenario、28タスク。

**総合判定: PASS — 人間最終承認済み。Task 7.4完了、28/28タスク完了。**
ユーザーの「確認しました。問題ないです」を、直前の明示的なMVP完成承認質問への回答として記録した。承認対象snapshotと原発言は[人間承認記録](human-approval.json)、承認前のNOT READY文書・検査・対応表・コードは`pre-approval/`へ保持する。

## 承認対象と根拠

[要件追跡表](traceability.md)と[機械可読対応表](traceability.json)に、Designの正準対応表を基礎として、全要件→Design→Task→関連試験・条件付き受入報告を列挙した。103 Scenarioの一覧も併記した。各試験ファイルの全メソッドを各Scenarioに一対一対応させたという主張ではなく、各報告の条件・反例と対応試験を合わせて照合するための表である。

WD01–16、SE01–25、EP01–17は既存の条件付き完了・修正記録と現在の回帰検査を合わせた作成者集約でPASS。EP18とTask7.4も今回の人間最終承認によりPASS。残る27タスクは完了記録と証拠を追跡した。独立した別レビュアーによるVF再受入とは表示しない。

| 判定 | 結果 | 対象・証拠と限界 |
|---|---|---|
| A / 7.1 | PASS | [VA](../va-acceptance.md): 固定G1–G7の独立2プロセス、byte比較、再生、異常注入28ケース。別エンジンや隔離した意味評価者ではない |
| Aへの1.4.0影響 / 6.6 | PASS（実施義務の範囲） | [G9](../g9-search-profile-impact.md): 旧入力1.0–1.3・実G6保存物・CF0、現在版検索、非干渉性、保存・再生・再hash改変・保存障害。旧Aの判定を新版へ書き換えず、別の影響確認として集約 |
| B / 7.2 | PASS | [run-2](../vb-search-profile-evidence/report.md): 新取得情報8run、他必須対20run、別デモ6run。17条件の独立反復、入力一変数監査、観測→認識→候補→選択→操作完了。共通準備やデモを自律行動の証明へ流用しない |
| G8 / 6.3, 6.5 | PASS | [G8最終裁定](../g8-acceptance.md): 固定応答の境界検査、OpenAI11問、独立意味評価24支持/2不確実、不確実2件は人間裁定で解決。一般的な自由文意味保証や自動公開許可ではない |
| C / 7.3 | PASS | [VC再試行](../vc-evidence-20261109-repeat-1/report.md): 新規コンテキスト、tool call 0、二段階封印、担当が選んだ追加取得51件、再評価・事後照合。単一runの調査手続きであり、同系列モデルの偏りは残る |
| VF / 7.4 | PASS | 承認対象snapshotを固定した人間最終承認記録に基づき完了 |

A/B/Cは互いの合格を前提に実施していない。VFだけが集約する。過去の各文書の「後続へ進まない」は当時の作業境界で、現在のVF指示と混同しない。

## レビュー対応と歴史的判定

- G6: stale提出、虚偽executed、同tick終了、payload型、保存失敗報告等を修正し反例追加。詳細は[closure報告](../g6-closure.md)。
- G7: 本人情報の過剰転記、旧投影公開、認可前例外、逆順応答ID、公開根拠漏洩等を修復。[再受入](../g7-reacceptance.md)に指摘と再検証を保持。
- G9: 複数ファイル参照の曖昧な束縛を一参照一ファイルへ制限し、null参照のTypeErrorも修正。更新前snapshotはhistoryへ保存し、人間確認後に完了。
- VB: 旧総合INCONCLUSIVEとrun-1 FAILを保存。timeout通知を実応答と区別する評価器訂正後、条件を変えずrun-2で再実行。G8関連の後発差分はVB固定対象の受入へ混入させず、G8側で別検証。
- G8: Gemini失敗・欠測、旧INCONCLUSIVE、独立評価のUNCERTAINを保持。選定OpenAIと人間裁定の最終記録を別成果物で保持。
- VC: 初回モデル名記録不足によるINCONCLUSIVEを保存。同じ公開入力・初期プロンプト・基準で、モデル名を明示した別試行のPASSを使用。

過去のFAIL等は訂正・再試行との関係を示した履歴であり、現行必須項目の未解決状態から恣意的に除外したものではない。元証拠は変更しない。

## 今回の変更・責務

新規: `scripts/vf_acceptance.py`、`tests/test_vf_harness.py`、本ディレクトリの集約文書・対応表・検査記録。既存の未コミットVC成果物は保持。開始commitとファイルhashは`baseline.json`へ固定した。

VF検査器は文書の完全性と未完了の阻害を検査する開発用入口で、製品CLIではない。ファイル存在は内容妥当性の証明ではなく、意味判定は本報告と元受入証拠に分離する。FAIL/NOT READY/INCONCLUSIVE/UNKNOWN/未確認、空要件、欠けたA/B/C、人間承認なしをPASSにしない反例試験を追加。対象外UNKNOWNは必須入力へ混入させず別記する。

製品コード、Policy、依存、保存形式、schema、イベント族に変更なし。依存方向は開発検査器→文書のみで、Domain CoreへI/O・教材分岐を追加しない。新たな製品責務の分割は不要。commit/push/deploy/archive・外部送信は行わない。

## 検証

今回の結果:

- 全351 unittest PASS（63.113秒）。うちVF追加4件。完成ゲートの18通りの未解決状態と空入力・欠測・承認なしを拒否。検査器の完全性照合追加後にもVF4件を再実行しPASS。
- Ruff全体PASS、mypy strict src/testsは89ファイルPASS、compileall PASS、uv lock --check PASS。
- OpenSpec strict / git diff --check PASS。Tasks追記後にも再実行しPASS。
- 追跡構造10項目PASS、VC事後構造17項目再照合PASS。前者は意味充足の自動証明ではない。
- 開始時に固定した既存ファイルの照合結果は`preservation.json`を参照。既存ソース・試験・入力・過去証拠の変更0。新規VFファイルとTasks追記を別に扱う。
- uvキャッシュ書込みのsandbox拒否は初回失敗として保存し、承認された通常権限でRuff/mypy/lockを再実行。新規検査器のRuff指摘2件（re.M別名）は修正し再検査成功。単体テスト末尾のFAIL JSONは期待した障害注入の出力で、unittest自体はOK。

実行結果は`validation.json`と各logへ記録した。対応表の完全性と全自動テストに加え、Ruff、mypy strict、構文、lock整合、OpenSpec strict、差分を確認する。検査成功だけで全体承認を代替しない。VCの封印・公開API構造検証は書込み入口を使わず再照合し、意味評価は既存封印後報告を参照する。ライブ生成器の追試は既存受入証拠を用いるため実施しない。

## 延期範囲と残存リスク

| 項目 | 状態 | MVPとの関係 |
|---|---|---|
| C11/C12実機、実コンパイル・実IDE・実OSS再現 | UNKNOWN / 対象外 | modeled/未実施の表現・拒否動作は必須で検証対象。実動作のPASSとは扱わない |
| 実利用者への経験的妥当性 | UNKNOWN / 対象外 | 合成環境の手続き成立を超える主張をしない |
| 介入・改善効果、現実への一般化 | UNKNOWN / 対象外 | 別変更・別版・別実行が必要 |
| 全面GUI、レビュー/マージ/リリース、全社業務、高度認知 | 延期 / 対象外 | Proposalの除外範囲を維持 |

自由文の自動意味保証、将来モデル版・SDK、全歴史版互換、OS管理者からの秘匿、電源断耐久、第三者署名真正性は保証しない。Cの索引に本文がない箇所や未収録操作を創作で補わない。合成時間・業務上未完了・内部失敗と実測/実機成功を区別する。

## 人間最終承認

TasksのVFレビュー方式が要求する人間最終承認を取得した。承認された集約、条件付きA/B/C判定、延期範囲と残余リスクは本報告の範囲に限る。追加の未解決判断事項はない。実機・経験的妥当性・介入効果の対象外UNKNOWNは維持し、commit/push/deploy/archiveは実施しない。

### 承認反映後の再検証

人間承認記録・追跡表・Tasksを更新し、VF4テスト、追跡構造10項目、承認snapshot照合、Ruff、mypy strict（89ファイル）、compileall、OpenSpec strict、git diff --checkはすべて成功。`validation-approved.json`に記録し、OpenSpec applyは28/28・all_doneを確認した。製品動作の変更はなく、全351テストは承認前の成功記録を保持し、この更新では関連4テストを再実行した。承認前manifestの原物は`pre-approval/manifest.json`、承認後成果物は`final-manifest.json`で識別する。
