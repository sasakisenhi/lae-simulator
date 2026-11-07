# 固定教材の来歴とオフライン検証

G1教材は fixtures/g1/manifest.json を正本とし、通常実行時にGitHubやGoogle Driveへ接続しない。

- raw/**/*.b64 はGitHub原バイト列のBase64固定物である。検証時に復号し、SHA-256と指定されたGit blob IDを再計算する。
- sources/oss/** はレビュー用のUTF-8抽出物であり、改行正規化され得るためGit blobの正本ではない。
- sources/lae/** と sources/issue/** は取得テキストにリポジトリ規約の終端改行を一つ加えたもの。manifestのsource digestは、その一つを除いた取得本文に対して計算する。
- reference-seed.json は後続G2向けの識別子の種であり、行動候補や正解経路を定義しない。

分類は実在OSS、実在Issue、監査専用の後日コメント、架空企業draftを分離する。LAEの旧ケースA/B/Cは固定対象外で、LAE02/LAE04の設定を実行時の原因・課題として自動採用しない。Issue本文は演習開始時に利用可能とする一方、後日コメントは初期知識に含めない。E0のAPI文書は固定参照であり、報告者が特定版を実機実行した証拠ではない。

OSSリポジトリ3件は同梱ライセンスでMITを確認した。GitHub Issue本文・コメント、およびLAE文書には個別ライセンス宣言を確認できないため、manifestではNOASSERTIONと利用条件の観測事実だけを記録し、再許諾判断は行わない。

オフライン検証コマンド: uv run lae-sim validate-materials fixtures/g1/manifest.json
