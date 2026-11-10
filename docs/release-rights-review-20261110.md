# リリース権利調査（2026-11-10）

## 対象と結果

リリース用master（基準abfc1d1）の本体・教材・uv.lockを対象とする。別ブランチの実行結果、Git履歴、開発支援ツールの再配布権は対象外。著作権の帰属や非公開契約を証明する調査ではない。

- 本体: Gitの著者はsasakishinのみ。ユーザーのライセンス作成依頼に基づき、オリジナルコードと本体向け文書にMITを設定。Git著者情報だけで職務著作等の権利帰属を証明するものではない。
- OSS 3件: 固定コミットの公式ライセンス原文とraw base64復号値のSHA-256が一致。著作権・許諾文を保持。
- Issue・コメント: 公式APIで投稿者・投稿日・本文一致を確認。投稿時のGitHub規約D.6と投稿前から存在するMITライセンスに基づき利用可能と判断。別契約の有無は未検証。
- LAE資料6件: Driveメタデータに所有者・許諾の根拠はなかった。2026-11-10、提供者本人から権利保有とMIT公開への同意を確認。ルートMITを適用。取得時の原本とmanifestは変更しない。
- 公開Release: 2026-11-10、ユーザーからLAE資料のMIT公開とリリースpushの承認を受領。
- 取得時のmanifest（NOASSERTIONを含む）と固定素材のdigestは変更せず、追加調査結果はTHIRD_PARTY_NOTICES.mdに記録。

## 一次資料

- [現行GitHub規約D.6](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#6-contributions-under-repository-license)
- [2024年投稿時点の規約](https://github.com/github/site-policy/blob/673c01e2bed86d4e1f62f10f1d4d00a4c4cdd867/Policies/github-terms/github-terms-of-service.md)
- [投稿より前の上流ライセンス履歴](https://github.com/microsoft/vscode-eslint/commit/a391a32348938811640059a6e81c35da05584e67)
- [Issue本文](https://github.com/microsoft/vscode-eslint/issues/1955): joshkel、2024-11-26
- [コメント](https://github.com/microsoft/vscode-eslint/issues/1955#issuecomment-2503124072): dbaeumer、2024-11-27
- [MIT標準本文](https://opensource.org/license/mit)

## ライセンス原文のSHA-256

- `b0/License.txt.b64`: `976f8ed671d885872afac0021bd78b3d84fe8d4783a98b46deb5a7dc4e29dbff`
- `e0/LICENSE.b64`: `3b6be04f862a077a4b97929dbf247299360824d9365f8603c263769303ace18c`
- `h0/LICENSE.md.b64`: `08c98374b7cc1f1e21a7cdcaafacdad49cde98949df3c55351ab822bcc80e2f3`

## Python依存

Linux Python 3.14.8環境の配布METADATA、License-File、実ファイルを照合。28件は固定版との一致・ライセンス原文あり。条件付き依存httpx2-jsfetch 1.0はlock記載のwheelを取得し、SHA-256・METADATA・BSD-3-Clauseの原文を確認。依存本体はソースアーカイブに同梱しない。全OSのwheel、組込み第三者コード、オフライン再配布を対象とする網羅的確認ではない。

| パッケージ | 固定版 | メタデータのライセンス表示 | 確認 |
|---|---|---|---|
| annotated-types | 0.8.0 | MIT | 版一致・原文あり |
| anyio | 4.16.0 | MIT | 版一致・原文あり |
| certifi | 2026.10.23 | MPL-2.0 | 版一致・原文あり |
| cffi | 2.1.1 | MIT-0 | 版一致・原文あり |
| charset-normalizer | 3.5.2 | MIT | 版一致・原文あり |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | 版一致・原文あり |
| distro | 1.9.0 | Apache License, Version 2.0 | 版一致・原文あり |
| google-auth | 2.62.1 | Apache 2.0 | 版一致・原文あり |
| google-genai | 3.0.0 | Apache-2.0 | 版一致・原文あり |
| h11 | 0.16.0 | MIT | 版一致・原文あり |
| httpcore2 | 2.16.0 | BSD-3-Clause | 版一致・原文あり |
| httpx2 | 2.16.0 | BSD-3-Clause | 版一致・原文あり |
| httpx2-jsfetch | 1.0 | BSD-3-Clause | lock記載wheelのSHA-256・原文を照合 |
| idna | 3.20 | BSD-3-Clause | 版一致・原文あり |
| jiter | 0.19.0 | MIT | 版一致・原文あり |
| openai | 3.46.0 | Apache-2.0 | 版一致・原文あり |
| pyasn1 | 0.6.5 | BSD-2-Clause | 版一致・原文あり |
| pyasn1-modules | 0.4.2 | BSD | 版一致・原文あり |
| pycparser | 3.12 | BSD-3-Clause | 版一致・原文あり |
| pydantic | 2.14.3 | MIT | 版一致・原文あり |
| pydantic-core | 2.50.4 | MIT | 版一致・原文あり |
| requests | 2.34.2 | Apache-2.0 | 版一致・原文あり |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | 版一致・原文あり |
| tenacity | 9.1.4 | Apache 2.0 | 版一致・原文あり |
| truststore | 0.10.5 | MIT | 版一致・原文あり |
| typing-extensions | 4.16.0 | PSF-2.0 | 版一致・原文あり |
| typing-inspection | 0.4.5 | MIT | 版一致・原文あり |
| urllib3 | 2.8.0 | MIT | 版一致・原文あり |
| websockets | 17.4 | BSD-3-Clause | 版一致・原文あり |
