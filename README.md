# LAE Simulator

再現可能な合成Issueシミュレーションと、その履歴から調査用証拠を生成するためのローカル実装です。現在はOpenSpec変更 `build-reproducible-simulation-foundation` のTask 1.3までを実装しています。固定世界入力の検証に加え、CF0 fixtureの決定的な実行、再生検査、固定保存、公開ログ取得ができます。

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
uv run --locked lae-sim run fixtures/cf0/world.json --output .runs
# runの出力に表示されたrun_pathを指定する
uv run --locked lae-sim public-log .runs/run-<run-id>
```

`doctor` は実行入口とランタイム版を検査します。`validate-world` は固定入力を読み込み、型・版・参照・権限・公開上限を検査して内容識別値を表示します。この2コマンドはシミュレーションを実行しません。

`run`は入力を再検証してから、候補選択、論理時間イベント、終了判定、再生照合、公開投影を行い、新規runディレクトリへ保存します。同じrunを同じ保存先へ上書きしません。`public-log`は保存物のdigest、履歴再生、派生状態、公開投影を再検査してから、調査者向けの合成ログだけを返します。Task 1.3の契約と保存物は [docs/walking-skeleton.md](docs/walking-skeleton.md) を参照してください。

## テスト

```console
uv run --locked python -m unittest discover -s tests -v
```

技術選定、決定性、保存形式、再生、役割別公開上限の実装方針は [docs/architecture/foundation.md](docs/architecture/foundation.md)、入力項目と検証契約は [docs/input-contract.md](docs/input-contract.md) を参照してください。

