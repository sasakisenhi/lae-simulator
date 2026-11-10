# ライセンスの適用範囲と第三者素材

確認日: 2026-11-10

ルートの [LICENSE](LICENSE) は、本プロジェクトが権利を持つオリジナルコードと本体向けドキュメントに適用します。第三者素材を再ライセンスするものではありません。`fixtures/g1/sources/lae/` の資料6件は、2026-11-10に提供者本人から権利保有とMITでの公開許諾を確認し、ルートのMITライセンスを適用します。

## 固定教材

| 素材 | 固定版・原著作者等 | 条件・確認結果 | 同梱の原文・出典 |
|---|---|---|---|
| vscode-eslint（B0） | `790646388696511b2665a4d119bf0fb713dd990d` / Microsoft Corporation | MIT。著作権・許諾文を保持して配布 | `fixtures/g1/sources/oss/b0/License.txt`、`fixtures/g1/raw/b0/License.txt.b64` |
| ESLint文書（E0） | `abea3b6f399fde9e28cf6dc5d6c013938f163cdc` / OpenJS Foundation and other contributors | MIT。著作権・許諾文を保持して配布 | `fixtures/g1/sources/oss/e0/LICENSE`、`fixtures/g1/raw/e0/LICENSE.b64` |
| eslint-plugin-header（H0） | `63f18ce725edb23a2d274b234df7f12ff0b7f009` / Stuart Knightley and contributors | MIT。著作権・許諾文を保持して配布 | `fixtures/g1/sources/oss/h0/LICENSE.md`、`fixtures/g1/raw/h0/LICENSE.md.b64` |
| Issue #1955（I1955） | 2024-11-26 / Josh Kelley (`joshkel`) | 下記のGitHub規約D.6と投稿時のMITライセンスに基づく判断 | `fixtures/g1/sources/issue/issue-1955.md`、[原投稿](https://github.com/microsoft/vscode-eslint/issues/1955) |
| Issueコメント（I1955-C1） | 2024-11-27 / `dbaeumer` | 同上。監査用資料であり、演習開始時の本人知識ではない | `fixtures/g1/sources/issue/comment-2503124072.md`、[原投稿](https://github.com/microsoft/vscode-eslint/issues/1955#issuecomment-2503124072) |
| LAE資料6ファイル | 架空企業資料 v0.2.0 / プロジェクト提供者 | MIT。2026-11-10に提供者が権利保有・公開を確認 | `fixtures/g1/sources/lae/`、元のDrive IDはmanifestに記録 |

### Issue本文・コメントの扱い

投稿時点より前から上流リポジトリにはMITライセンスが存在しています。GitHub利用規約D.6は、ライセンス表示のあるリポジトリへのContent追加を、別契約がある場合を除き、同じ条件での提供としています。[現行規約D.6](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#6-contributions-under-repository-license) と [2024年投稿時点の規約](https://github.com/github/site-policy/blob/673c01e2bed86d4e1f62f10f1d4d00a4c4cdd867/Policies/github-terms/github-terms-of-service.md) を確認しました。

このため、本プロジェクトでは両投稿をMIT条件で利用できると判断します。個別に許諾を取得したという意味ではありません。投稿者との別契約の存在までは確認できていません。原投稿者の帰属表記を上表に保持し、上流のMIT許諾文はB0のライセンス原文に保持します。公開されていることや閲覧・forkの許可だけを根拠にした判断ではありません。

manifestの `NOASSERTION` は取得時の記録です。固定入力・digest・来歴の再現性を維持するため、取得時の原本とmanifestは書き換えず、この文書に追加調査の判断を記録します。

### 原文の保持

固定コミットにある3件のライセンス原文のSHA-256と、`raw/` のbase64を復号したバイト列が一致することを確認しました。`sources/` の読みやすいコピーには改行の変換・追加が含まれます。対象版、出典、内容digestは `fixtures/g1/manifest.json` にあります。

LAE資料の許諾根拠は、提供者本人による権利保有・MIT公開の確認です。架空企業の設定であることやDriveから閲覧できることを、許諾の根拠とはしていません。

## Python依存ライブラリ

依存ライブラリの対象版は `uv.lock` に固定しています。本リリースのソースアーカイブにPython依存ライブラリ本体は同梱せず、インストール時に各配布元から取得します。本体MITライセンスによって各依存の条件を置き換えるものではありません。

Linux環境にインストール済みの28依存パッケージについて、固定版との一致、配布メタデータのライセンス表示、ライセンスファイルの同梱を確認しました。直接依存は OpenAI SDK 3.46.0（Apache-2.0）、Google Gen AI SDK 3.0.0（Apache-2.0）、Pydantic 2.14.3（MIT）です。推移依存にはMIT、MIT-0、Apache-2.0、BSD系、PSF-2.0、MPL-2.0等が含まれます。条件付き依存 `httpx2-jsfetch` 1.0（BSD-3-Clause）も、lock記載のwheelを取得し、固定ハッシュ・メタデータ・ライセンス原文を確認しました。調査記録は開発用の `docs/release-rights-review-20261110.md` に保持しています。

以上は配布メタデータとライセンス原文の確認であり、依存パッケージに組み込まれたすべての第三者コードを網羅的に監査したものではありません。依存ライブラリを同梱するオフライン配布・単体実行ファイル化は本確認の対象外です。その場合は各ライセンス、NOTICE、ソース提供義務などを別途確認してください。
