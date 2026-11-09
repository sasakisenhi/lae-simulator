# Issue #1955 演習の実行と公開証拠

実行結果: valid。業務状態: incomplete。保存再取得・Replay: PASS。

同梱の明示コマンド列（Issue読取 → metadata検索 → R01への参照移動）を実行した。自律Policyの実行ではない。

公開証拠 51件（操作・終了記録 4件を含む）。metadata検索 5件。再取得結果の一致を確認。

## 操作・終了記録

### public:PUB-588e35b2e3b3b707

```json
{
  "acquisition": "synthetic event projection; real collection unverified",
  "body": {
    "acquisition_method": "synthetic event projection; real collection unverified",
    "actor_id": "ACTOR-DEVTOOLS-EXERCISE",
    "assumed_source": "simulated tool operation: issue.read",
    "available_fields": [
      "event_id",
      "logical_time",
      "kind",
      "actor_id",
      "target_id",
      "version"
    ],
    "coverage": null,
    "event_id": "PUB-588e35b2e3b3b707",
    "evidence_refs": [],
    "kind": "document-read",
    "limitations": null,
    "logical_time": 1,
    "outcome": null,
    "source_class": "tool-shaped",
    "synthetic": true,
    "target_id": "D01",
    "version": "B0"
  },
  "classification": "public-evidence",
  "digest": "sha256:59ccd8d8d0031c1716cb3d6b35bb827e1a28c47c462e5869ce983891d5559375",
  "event_id": "PUB-588e35b2e3b3b707",
  "id": "public:PUB-588e35b2e3b3b707",
  "issue": "I1955",
  "operation": "document-read",
  "retained": true,
  "source_class": "tool-shaped",
  "target": "D01",
  "tick": 1,
  "version": "B0"
}
```

### public:PUB-7d678321ba8c57b5

```json
{
  "acquisition": "synthetic event projection; real collection unverified",
  "body": {
    "acquisition_method": "synthetic event projection; real collection unverified",
    "actor_id": "ACTOR-DEVTOOLS-EXERCISE",
    "assumed_source": "simulated tool operation: code.search",
    "available_fields": [
      "event_id",
      "logical_time",
      "kind",
      "actor_id",
      "target_id",
      "version",
      "query",
      "result_refs"
    ],
    "coverage": null,
    "event_id": "PUB-7d678321ba8c57b5",
    "evidence_refs": [],
    "kind": "search",
    "limitations": null,
    "logical_time": 2,
    "outcome": null,
    "query": "metadata",
    "result_refs": [
      "R01",
      "R02",
      "R06",
      "R10",
      "workspace:B0:server/src/eslint.ts#121",
      "workspace:B0:server/src/eslint.ts#1211",
      "workspace:B0:server/src/eslint.ts#1223",
      "workspace:B0:server/src/eslint.ts#1228",
      "workspace:B0:server/src/eslint.ts#1229",
      "workspace:B0:server/src/eslint.ts#128",
      "workspace:B0:server/src/eslint.ts#130",
      "workspace:B0:server/src/eslint.ts#131",
      "workspace:B0:server/src/eslint.ts#133",
      "workspace:B0:server/src/eslint.ts#141",
      "workspace:B0:server/src/eslint.ts#144",
      "workspace:B0:server/src/eslint.ts#150",
      "workspace:B0:server/src/eslint.ts#153",
      "workspace:B0:server/src/eslint.ts#155",
      "workspace:B0:server/src/eslint.ts#158",
      "workspace:B0:server/src/eslint.ts#259",
      "workspace:B0:server/src/eslint.ts#326",
      "workspace:B0:server/src/eslint.ts#330",
      "workspace:B0:server/src/eslint.ts#368",
      "workspace:B0:server/src/eslint.ts#372",
      "workspace:B0:server/src/eslint.ts#640",
      "workspace:B0:server/src/eslintServer.ts#25",
      "workspace:B0:server/src/eslintServer.ts#295",
      "workspace:B0:server/src/eslintServer.ts#661",
      "workspace:B0:server/src/eslintServer.ts#693",
      "workspace:B0:server/src/eslintServer.ts#824"
    ],
    "source_class": "tool-shaped",
    "synthetic": true,
    "target_id": "metadata",
    "version": "B0"
  },
  "classification": "public-evidence",
  "digest": "sha256:905d510812b59224dab7e42fd44aab15d65a5c8eed5679badcdc53ac2c7f5a69",
  "event_id": "PUB-7d678321ba8c57b5",
  "id": "public:PUB-7d678321ba8c57b5",
  "issue": "I1955",
  "operation": "search",
  "retained": true,
  "source_class": "tool-shaped",
  "target": "metadata",
  "tick": 2,
  "version": "B0"
}
```

### public:PUB-a15837892e1efe9d

```json
{
  "acquisition": "synthetic event projection; real collection unverified",
  "body": {
    "acquisition_method": "synthetic event projection; real collection unverified",
    "actor_id": "ACTOR-DEVTOOLS-EXERCISE",
    "assumed_source": "simulated tool operation: symbol.navigate",
    "available_fields": [
      "event_id",
      "logical_time",
      "kind",
      "actor_id",
      "target_id",
      "version"
    ],
    "coverage": null,
    "event_id": "PUB-a15837892e1efe9d",
    "evidence_refs": [],
    "kind": "navigate",
    "limitations": null,
    "logical_time": 2,
    "outcome": null,
    "source_class": "tool-shaped",
    "synthetic": true,
    "target_id": "R01",
    "version": "B0"
  },
  "classification": "public-evidence",
  "digest": "sha256:bff6ad244ef0f94e85f12fb6a0964ce589b4ae466166dcc528e6db7b91d7b9d4",
  "event_id": "PUB-a15837892e1efe9d",
  "id": "public:PUB-a15837892e1efe9d",
  "issue": "I1955",
  "operation": "navigate",
  "retained": true,
  "source_class": "tool-shaped",
  "target": "R01",
  "tick": 2,
  "version": "B0"
}
```

### public:PUB-870117d6ee9d78b1

```json
{
  "acquisition": "synthetic event projection; real collection unverified",
  "body": {
    "acquisition_method": "synthetic event projection; real collection unverified",
    "actor_id": "ACTOR-DEVTOOLS-EXERCISE",
    "assumed_source": "LAE simulator internal event",
    "available_fields": [
      "event_id",
      "logical_time",
      "kind",
      "actor_id",
      "outcome"
    ],
    "coverage": null,
    "event_id": "PUB-870117d6ee9d78b1",
    "evidence_refs": [],
    "kind": "run-ended",
    "limitations": null,
    "logical_time": 2,
    "outcome": "incomplete",
    "source_class": "internal",
    "synthetic": true,
    "target_id": null,
    "version": null
  },
  "classification": "public-evidence",
  "digest": "sha256:a998ad9fc5bf6f548c0cc737db01a800c8c7c8a55fd9425be0614be5c327bde4",
  "event_id": "PUB-870117d6ee9d78b1",
  "id": "public:PUB-870117d6ee9d78b1",
  "issue": "I1955",
  "operation": "run-ended",
  "retained": true,
  "source_class": "internal",
  "target": null,
  "tick": 2,
  "version": null
}
```

## 公開資料・参照・検索位置の一覧

| 公開ID | 種別 | 対象 |
|---|---|---|
| document:D01 | document.read | D01 |
| document:D02 | document.read | D02 |
| document:D03 | document.read | D03 |
| document:D04 | document.read | D04 |
| document:D05 | document.read | D05 |
| document:D06 | document.read | D06 |
| reference:R01 | metadata-fields | D02 |
| reference:R02 | metadata-capture | D02 |
| reference:R03 | url-lookup | D02 |
| reference:R04 | type-lookup | D02 |
| reference:R05 | registration-test | D02 |
| reference:R06 | validation-flow | D02 |
| reference:R07 | code-action-storage | D02 |
| reference:R08 | fix-record-link | D02 |
| reference:R09 | single-fix-generation | D02 |
| reference:R10 | documentation-action | D02 |
| reference:R11 | all-fixes-flow | D02 |
| reference:R12 | options-forwarding | D02 |
| reference:R13 | string-check | D02 |
| reference:R14 | url-less-layout-example | D06 |
| reference:R-UNKNOWN | outside-finite-index |  |
| workspace:B0:server/src/eslint.ts#121 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#1211 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#1223 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#1228 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#1229 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#128 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#130 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#131 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#133 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#141 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#144 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#150 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#153 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#155 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#158 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#259 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#326 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#330 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#368 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#372 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslint.ts#640 | workspace-search-hit | server/src/eslint.ts |
| workspace:B0:server/src/eslintServer.ts#25 | workspace-search-hit | server/src/eslintServer.ts |
| workspace:B0:server/src/eslintServer.ts#295 | workspace-search-hit | server/src/eslintServer.ts |
| workspace:B0:server/src/eslintServer.ts#661 | workspace-search-hit | server/src/eslintServer.ts |
| workspace:B0:server/src/eslintServer.ts#693 | workspace-search-hit | server/src/eslintServer.ts |
| workspace:B0:server/src/eslintServer.ts#824 | workspace-search-hit | server/src/eslintServer.ts |

## 出力ファイル

- public-evidence.json: 取得できた公開証拠の全文
- operation-evidence.json: 操作・終了記録
- metadata-evidence.json: metadataでの追加取得結果
- run-result.json / summary.json: 実行・取得結果

## 限界

操作履歴は合成記録。資料は固定教材。未収録は不存在を意味しない。コード修正・模擬チェック・PR提出はこのコマンド列に含まれず、incomplete終了を内部エラーや作業完了と扱わない。実機での再現・コンパイル・外部送信は実施していない。
