# OpenSpec × Codex 自律開発ワークフロー

本書は、承認済みのOpenSpec変更を機能グループ単位で実装し、節目で人間が確認するための運用手順である。現在の対象changeは`build-reproducible-simulation-foundation`。ワークフロー整備自体は同changeの25タスクへ数えない。

## 1. 実装単位と承認境界

人間は開始時にchange、機能グループ、含めるタスク、除外範囲を明示する。Codexはその範囲で次を自律実行する。

1. Proposal、Design、該当Specs、Tasks、既存実装、Git差分を確認する。
2. 依存を満たす順に実装し、関連テストを追加する。
3. 失敗を調査して安全な局所修正を行い、検査を再実行する。
4. 受入条件を満たしたタスクだけを完了にする。
5. 機能グループの境界で人間へ完了報告する。

Task 1.3を指定する場合、1.3だけを一つの機能グループとする。Task 2.1以降へ自動的に進まない。停止条件はルート`AGENTS.md`に従う。

## 2. 検証の三層

### A. 自動テスト

具体的な入力、回帰、境界条件、異常系を検証する。現在の標準入口は次のとおり。

```console
uv sync --locked
uv lock --check
uv run --locked python -m unittest discover -s tests -v
uvx --from ruff==0.17.4 ruff check .
uvx --from mypy==2.4.1 mypy --strict src tests
uv run --locked python -m compileall -q src tests
openspec validate build-reproducible-simulation-foundation --type change --strict --no-interactive
git diff --check
```

変更に不要な検査を省略した場合は、完了報告へ理由を残す。成功したテストだけでOpenSpecの要求充足を推定しない。

### B. OpenSpecとの整合性レビュー

対象タスクについて、要求、受入Scenario、Design判断、成果物、依存、完了条件と実装・テストの対応を確認する。`openspec-verify-change`が導入済みなら利用できるが、Verifyはchange全体の未完了も報告する。途中段階では、未指定の後続タスクが未完了であることを全体失敗と取り違えず、指定機能グループの整合性所見を分けて記録する。

OpenSpec 1.16.0の現在のglobal profileは`core`で、Verify workflowは未導入である。導入にはglobal profileの変更が必要なため、自動変更しない。人間の承認後に次を実行する。

```console
openspec config profile
# Verify changeを現在のworkflowsへ追加し、deliveryを確認する
openspec update .
```

`openspec config profile`は`~/.config/openspec/config.json`を変更し、他のOpenSpecプロジェクトにも影響する。`openspec update .`は選択したprofileをこのプロジェクトのスキル・コマンドへ反映する。実行前後に次で差分を確認する。

```console
openspec config list
openspec update --dry-run --json .
git status --short
```

### C. コードレビュー

バグ、境界条件、状態不整合、非決定性、公開境界、セキュリティ、過剰実装、テスト不足を確認する。Codex CLI 0.166.0では次を利用できる。

```console
codex review --uncommitted
codex review --base master
codex review --commit <SHA>
codex review --uncommitted "Task 1.3の要求とDesign D4/D10/D12を基準に、決定性・再生・公開境界・過剰実装を重点レビューする"
```

`--uncommitted`はstaged、unstaged、untrackedをすべて含み、Codexが作った差分だけには限定されない。`--base`は指定branchとのmerge-baseからの差分、`--commit`は一つのcommitを対象にする。組込みReviewは専用reviewerを使い、所見を報告するだけで作業ツリーを変更しない。

独立レビューのためのカスタムサブエージェントは現時点では置かない。サブエージェントは親セッションのsandbox・approvalを継承し、instructionsだけではread-only権限を保証できないためである。より強い権限分離が必要なら、別Codexセッションをread-onlyで開始する。

## 3. Git差分の分離

機能グループ開始前に`git status --short --branch`と`git log -1 --oneline`を記録する。既存差分がある場合、`codex review --uncommitted`は混在差分をレビューするため、次のいずれかを人間が選ぶ。

- 既存成果を人間が確認して基準commitにし、次の機能グループを別commitまたは別branchで作業する。
- commit済みの基準SHAを記録し、`codex review --base`または`--commit`でレビュー対象を固定する。
- commitしない場合は対象ファイルをレビュー指示へ明記し、混在差分が入力に残ることを受け入れる。

Codexは明示的な依頼なしにcommit、branch切替、差分破棄を行わない。

## 4. 機能グループ完了ゲート

次をすべて区別して報告する。

- Aの実行結果と、未実行・対象外の検査
- Bで確認した要求・Scenario・Design・タスク完了条件
- Cの所見と、修正後の再レビュー状況
- 未検証事項、残存リスク、人間判断事項

OpenSpec strict validationは文書形式の検査であり、機能動作やchange全体完成の証拠ではない。Verify、テスト、レビューのいずれか一つだけでタスクを完了扱いにしない。
