# LAE Simulator

再現可能な合成Issueシミュレーションと、その履歴から調査用証拠を生成するためのローカル実装です。現在はOpenSpec変更 `build-reproducible-simulation-foundation` のTask 1.2までを実装しています。固定世界入力とCF0 fixtureの検証はできますが、シミュレーション実行はまだ含みません。

## 対応環境

- Python 3.14.8（`.python-version` と `pyproject.toml` で固定）
- uv 0.12系（`uv.lock` を使用。Task 1.1の検証版は0.12.24）
- Linux x86_64で検証。実装はOS固有APIを使用しない

uvは固定Pythonを必要に応じて取得し、ローカルの`.venv`へ同期します。アプリケーションとテストにはサードパーティ依存がありません。

## セットアップと起動

```console
uv sync --locked
uv run --locked lae-sim doctor
uv run --locked lae-sim validate-world fixtures/cf0/world.json
```

`doctor` は実行入口とランタイム版を検査します。`validate-world` は固定入力を読み込み、型・版・参照・権限・公開上限を検査して内容識別値を表示します。どちらもシミュレーションは実行しません。

## テスト

```console
uv run --locked python -m unittest discover -s tests -v
```

技術選定、決定性、保存形式、再生、役割別公開上限の実装方針は [docs/architecture/foundation.md](docs/architecture/foundation.md)、入力項目と検証契約は [docs/input-contract.md](docs/input-contract.md) を参照してください。

