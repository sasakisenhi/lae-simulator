# LAE Simulator

固定入力から合成Issueシミュレーションを実行し、履歴・調査用証拠・合成インタビューを生成するローカルCLIです。v0.1.0は初期リリースです。

生成物は合成情報です。実際の従業員の行動や実測結果ではありません。仮想変更・modeledチェックは、実リポジトリへの変更や実コンパイルの成功を意味しません。

## インストール

Python 3.14.8、uv 0.12系を使用します。Linux x86_64で検証しています。他のOSは未検証です。

GitHub Releaseの「Source code (zip)」または「Source code (tar.gz)」をダウンロードして展開し、展開先で実行してください。uvが固定Pythonと依存ライブラリを取得するため、初回セットアップにはネット接続が必要です。

```console
uv sync --locked
uv run --locked lae-sim doctor
uv run --locked lae-sim --help
```

以降のコマンドも展開先で実行します。`fixtures/` は必要な入力・教材なので、内部の相対配置を変更しないでください。

## 最初のシミュレーション

APIキー不要の最小サンプルです。

```console
uv run --locked lae-sim validate-world fixtures/cf0/world.json
uv run --locked lae-sim run fixtures/cf0/world.json --output .lae-runs
```

実行結果のJSONに表示される `run_path` を次の `<run_path>` に指定します。

```console
uv run --locked lae-sim public-log <run_path>
```

`run` は入力検証・実行・保存・再生照合を行います。保存済みrunを上書きしません。`public-log` は保存内容を再検査し、調査者向けの合成ログを返します。

## Issue演習と証拠取得

固定教材は `microsoft/vscode-eslint` のIssue #1955を使う仮想演習です。実際のGitHubへPRを送信しません。

```console
uv run --locked lae-sim validate-materials fixtures/g1/manifest.json
uv run --locked lae-sim validate-scenario fixtures/g2/scenario-collaboration.json
uv run --locked lae-sim run-scenario fixtures/g2/scenario-collaboration.json --commands fixtures/g8/commands.json --output .lae-runs
```

表示された `run_path` を使って証拠を取得します。

```console
uv run --locked lae-sim evidence <run_path> --scenario fixtures/g2/scenario-collaboration.json
uv run --locked lae-sim evidence --help
```

このCLIの `run-scenario` は指定されたコマンド列を実行します。自律的な行動選択の受入検証とは区別してください。

## 合成インタビュー

固定回答モードは外部APIへの送信なしで実行できます。Issue演習で保存した `run_path` を指定してください。インタビューの保存先はrunディレクトリの外に置きます。

```console
uv run --locked lae-sim interview <run_path> --scenario fixtures/g2/scenario-collaboration.json --config fixtures/g8/fixed.json --questions fixtures/g8/questions.json --output .lae-interviews
```

この固定回答例は回答を捏造せず `UNKNOWN` を返すため、終了コード6（`answered-unknown`）になります。回答は `.lae-interviews/provider-1/public.json` に保存されます。終了コード0の事実回答や受入成功を示す例ではありません。

外部LLMを使う場合は `prepare-interview --help` と `interview --help` を確認してください。APIキーは設定が指定する環境変数で渡し、配布ファイルへ書き込まないでください。外部送信には接続設定・価格情報・予算・送信承認が必要です。費用が発生することがあります。同梱の接続設定は例示であり、利用時点のモデル利用可否や価格を保証しません。

## 結果とエラー

- 実行成功と業務上の完了は別です。結果の `status` と `business_outcome` を確認してください。
- 保存ディレクトリには正準履歴や管理用情報が含まれます。調査参加者へ配布する場合は、公開取得コマンドの出力を使ってください。
- 入力不正は終了コード2、内部エラーなどは3を返します。エラーのJSONを確認し、入力や保存物を手で書き換えて成功扱いにしないでください。
- 入力の配置・内容・版が変わると検証に失敗することがあります。元の配布物を別の場所へ展開して確認してください。

## 利用条件と配布範囲

本体のオリジナルコードと本体向けドキュメントは [MIT License](LICENSE) で提供します。LAE資料6件も提供者の許諾によりMITで提供します。第三者素材を再ライセンスするものではありません。素材の出典・利用条件は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を確認してください。

リリースアーカイブは本体・使い方・必要データ・依存固定ファイルを含みます。開発用仕様、テスト、検証ログ、個人設定は含みません。変更点と制約は [RELEASE_NOTES.md](RELEASE_NOTES.md) を参照してください。
