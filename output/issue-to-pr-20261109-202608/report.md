# Issue #1955：Issue読取から仮想PR提出まで

結果: **submitted**。保存再取得・Replay: **PASS**。公開証拠の再取得一致を確認。

これは既存エンジンに明示経路を与えた演習デモ。自律Policyが修正案を発見した実験ではない。

## 実行した経路

Issue読取 → metadata検索 → R02参照移動 → README/API文書/規則コード読取 → 教材パッチP1適用 → 模擬チェック7件 → 仮想PR提出。

## 仮想PRの内容

Issue #1955の演習用変更。docs.urlがなくても有効なrule metadataを保持し、ドキュメントアクションはURL取得可能な場合に表示する。固定教材パッチP1を仮想Workspaceへ適用した。

変更ファイル: server/src/eslint.ts, server/src/eslintServer.ts

差分全文: [virtual-change.diff](virtual-change.diff)。提出記録: [virtual-pr.json](virtual-pr.json)。

## 模擬チェック

| ID | 結果 | mode | 確認範囲 |
|---|---|---|---|
| C01 | PASS | modeled | metadata registration and fix recording |
| C02 | PASS | modeled | explicit type filtering |
| C03 | PASS | modeled | registration and URL retrieval |
| C04 | PASS | modeled | documentation action presentation |
| C05 | PASS | modeled | unfiltered branch |
| C06 | PASS | modeled | unknown type handling |
| C10 | UNKNOWN | modeled | version correspondence |

## 公開操作履歴

| 公開ID | 論理時刻 | 操作 | 対象 |
|---|---:|---|---|
| public:PUB-588e35b2e3b3b707 | 1 | document-read | D01 |
| public:PUB-7d678321ba8c57b5 | 2 | search | metadata |
| public:PUB-b875172ad0ea4182 | 2 | navigate | R02 |
| public:PUB-a88f8553403e8b39 | 3 | document-read | D02 |
| public:PUB-5a5469f49385b570 | 4 | document-read | D04 |
| public:PUB-022d6d4f264bca36 | 5 | document-read | D05 |
| public:PUB-e1219afbd9a9842b | 6 | document-read | D06 |
| public:PUB-c1db5b3fee954a48 | 7 | patch-applied | P1 |
| public:PUB-d8a969e4e7ad4f37 | 8 | check-evaluated | C01 |
| public:PUB-e1ca682c0ff86faa | 9 | check-evaluated | C02 |
| public:PUB-dd351d2a8ece4afa | 10 | check-evaluated | C03 |
| public:PUB-f4a342f24987199e | 11 | check-evaluated | C04 |
| public:PUB-d4647aefa69d41ab | 12 | check-evaluated | C05 |
| public:PUB-1242970d2c6e23af | 13 | check-evaluated | C06 |
| public:PUB-329d543d3b7d2407 | 14 | check-evaluated | C10 |
| public:PUB-94a0d4a4554501a6 | 15 | submission-created | SIMULATED-SUBMISSION |
| public:PUB-a7e3e038ca47e47a | 15 | run-ended |  |

## 出力と限界

公開証拠64件、うち操作・終了記録17件。全文は[public-evidence.json](public-evidence.json)。

合成教材の意味モデルによる検査のみ。VS Code/plugin実行、自動修正の実機再現、build/typecheck/既存テスト（C11/C12）、実GitHub送信は未実施。

提出先はローカル仮想資源SIMULATED-SUBMISSION。PR番号・外部URLは発行しない。レビュー、マージ、リリースは今回の対象外。
