# G8 再実行前確認（2026-11-09）

対象: build-reproducible-simulation-foundation、Tasks 6.3 / 6.5。
開始時HEAD: c338136。既存G9差分と送信前レビュー資料を保持した。

## 実行した検査

- `.venv/bin/python -m unittest discover -s tests -v`: 317件成功（63.621秒）。
  固定応答・通信モック・回答監査・公開禁止・再質問・#1955縦断CLI・CF0を含む。
  負の試験が出力するFAIL JSONはunittestの失敗ではない。
- Ruff 0.17.4: G8のadapters、interview関連、CLI、関連3テストファイルは成功。
  リポジトリ全体は既存G9差分の7件で失敗。対象はlocal_loader.py、
  local_model.py、world/scenario.py、test_search_profile_contract.py。
- mypy 2.4.1 `--strict src tests`: 83ファイルを検査し、既存G9差分の3件で失敗。
  local_loader.pyの空tuple推論、test_search_profile_contract.pyのOptional値2件。
  全体型検査成功とは扱わず、G9ファイルは本作業で変更していない。
- `.venv/bin/python -m compileall -q src tests`: 成功。
- OpenSpec change strict validation: 成功。機能受入の代替とはしない。
- `git diff --check`: 成功（本記録追加前）。

## 残る完了条件

選定生成器のライブ接続と回答の意味評価は未実施。
APIキー設定の確認は送信承認や接続成功の証拠とはしない。
README.mdの具体的な送信内容・Provider・22要求・予算についてユーザーへ
承認を求めた。承認grantはfalseを維持し、API送信・課金要求は行っていない。
一次評価者・独立評価者の指定も未確定である。

6.3はNOT READY、6.5は依存6.3未充足のため未完了を維持する。
既存実装の責務分離・要求対応・残余リスクはdocs/g8-validation.mdを参照。
本再確認ではコード変更・新たな独立コードレビューは行っていない。
自由文の意味・日本語品質・実usageは自動テスト成功から推定しない。
VB/VC/VF、既存VA/VB証拠、G9完了判定は更新していない。
commit/push/deploy/archiveは行っていない。

本記録は送信対象資料を変更しない追補であり、既存manifestの構成物ではない。
ライブ実行前の既存manifest照合・料金/モデル再確認は依然必要である。
