# G8 インタビュー生成・ローカル実行

対象: `build-reproducible-simulation-foundation` の6.3/6.5（D9、EP06/08–10/15/16）。
2026-11-08時点で6.3は **NOT READY**（選定モデルの実接続・意味評価未実施）、
6.5も依存6.3が未充足のため **NOT READY**。チェックボックスは更新しない。
オフラインの実装・契約検査と、生成器の実受入を分ける。VB/VC/VFの判定は更新しない。

## 実装境界と変更ファイル

| ファイル | 目的 |
|---|---|
| `simulation/interview_contract.py` | Provider共通のProtocol、発言型、JSON Schema、厳格なJSON/型検査 |
| `simulation/interview_validation.py` | 本人根拠catalog、参照権限、私的ID、引用・認識種別・episode・再質問の検査 |
| `simulation/interview.py` | FixedResponseGenerator、固定本人パッケージの読取り、試行監査と採用履歴の分離 |
| `adapters/interview_config.py` | Provider/モデル/プロンプト/生成設定/環境変数名、価格、上限、入力別承認の検証 |
| `adapters/interview_remote.py` | Gemini/OpenAI SDK接続、構造化出力、使用量、エラー分類、有限再試行 |
| `adapters/interview_budget.py` | リクエスト前予約、usage精算、評価run共通台帳・停止 |
| `interview_evaluation.py` | 同一入力での単独/比較実行、個別履歴、評価指標、別領域への保存 |
| `scenario_cli.py`, `cli.py` | Scenarioの実行/保存/Replay/公開取得/質問を既存CLIへ接続 |
| `fixtures/g8/*.json` | ローカル操作入力、11質問、fixed/Gemini/OpenAI/比較設定 |
| `tests/test_interview*.py`, `tests/test_g8_cli.py` | 固定応答、SDK形状/障害モック、履歴汚染防止、CLI/互換・保存・送信拒否 |
| `pyproject.toml`, `uv.lock` | SDK/Pydanticの固定依存、mypyの同期済み環境参照 |
| `.gitignore` | `.env*`と`.lae-runs/`をGit対象外にする |

`tests/test_async_collaboration.py`は既存のRuff違反（import順/重複import/未使用代入）
だけを修正した。呼出しとassertは維持した。開始時から存在したOpenSpec/skillsの差分は保持する。

Engine/Reducer/Scheduler/Policy/Run Store/G7 Projectorを変更しない。
LLMはEngine終了・保存再取得・Replay照合後にだけ使う。
LLMの文章、実応答時間、トークン、費用は正準イベント列やシミュレーション時間へ入れない。
新しい保存形式はインタビューのsidecarだけで、既存runのmanifestやartifact集合を変えない。

## オフラインの縦断手順

リポジトリrootで実行する。新規保存先を使い、既存runを上書きしない。

```sh
uv sync --locked
uv run --locked lae-sim run-scenario fixtures/g2/scenario-collaboration.json \
  --commands fixtures/g8/commands.json --output .lae-runs/simulation
```

出力JSONの`run_path`を`RUN`へ設定する。この固定入力例では次のパスになる。

```sh
RUN=.lae-runs/simulation/local-101217f59d4d49247749b05af54b18fc46d23b91eb8e43c3251b86409c5f9c88
uv run --locked lae-sim evidence "$RUN" \
  --scenario fixtures/g2/scenario-collaboration.json --id document:D01
uv run --locked lae-sim evidence "$RUN" \
  --scenario fixtures/g2/scenario-collaboration.json --query metadata
uv run --locked lae-sim interview "$RUN" \
  --scenario fixtures/g2/scenario-collaboration.json --config fixtures/g8/fixed.json \
  --questions fixtures/g8/questions.json --output .lae-runs/offline-1
```

最後のコマンドはfixed生成器がUNKNOWNで回答し、終了コード6になる。
これは配線の検査であり、実モデルの回答品質や自然な回答の実証ではない。
`run-scenario`は候補と操作パラメータを明示した有限コマンド入力を、既存の
`LocalSession.select/perform/finish`へ渡す。例は資料閲覧→検索→参照移動の
有効なINCOMPLETEで終了し、#1955の全解決・自律Policyの受入を主張しない。
対応するCLI操作はissue/document.read、code.search、symbol.navigate、
patch.apply/revert、check.model。既存操作の意味や未知操作を補完しない。

CF0入口は従来のまま:

```sh
uv run --locked lae-sim run fixtures/cf0/world.json --output .lae-runs/cf0
uv run --locked lae-sim public-log '<上記出力のrun_path>'
```

公開関連取得は`evidence ... --id <公開ID> --related`、検索は
`--issue/--target/--tick/--through-tick/--query`を使う。役割はresearcherのみ。
未知・非公開・他人のActorは同じ`unavailable`で拒否する。

## Providerと公式仕様の確認

2026-11-08に公式資料とインストールされたSDK型・実装を確認した。

- [OpenAIモデル](https://developers.openai.com/api/docs/models/gpt-6.1-terra):
  `gpt-6.1-terra`。`openai==3.46.0`、Responses API
  `https://api.openai.com/v1/responses`。
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs):
  `text.format`の`json_schema/strict`を使用する。`store=False`、reasoning effortはnone。
- [Geminiモデル](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash):
  `gemini-2.5-flash`。`google-genai==3.0.0`、Gemini Developer APIの
  `https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`。
- [Google SDK](https://googleapis.github.io/python-genai/)、
  [Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output):
  `response_mime_type=application/json`と`response_json_schema`を使用する。
  thinking budget=0、candidate_count=1、AFCとautomatic_continuationを無効化、store=False。
  SDKの既定automatic_continuationはtrueなので省略しない。
- SDK自身のretryはOpenAI=0、Geminiのattempts=1。アプリ側だけが上限付きretryを管理する。
  OpenAIの環境変数によるbase URL差替え、GeminiのVertex/Enterprise自動選択を使わない。

両Providerの返却JSONを同じローカルスキーマで再検証する。
必要フィールド以外、重複JSONキー、不正型、空文字、不正認識種別、非有限数を拒否する。
`topic/value/episode`はnull可だが全フィールドを必須にする。API拒否とトークン打切りを
正常回答と扱わず、返却usageは拒否・不正JSONの場合も記録する。

Googleの[料金資料](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash)では
2026-12-01以降の別モデルへの自動転送が告知されている。
指定モデルを暗黙変更せず、例の価格設定は2026-11-30で失効する。
返却モデル名も保存し、要求モデルとの明らかな不一致は停止する。
接続可能性・アカウント権限・全パラメータの実API受理は未検証である。

## 外部送信の承認

**この作業では実APIを呼んでいない。下記は人間の明示的承認後の手順である。**
環境変数名だけを設定へ書き、キー値は環境変数に設定する。キーをコマンド引数、
ソース、設定JSON、レビュー資料へ記載しない。

単独Providerは`fixtures/g8/gemini.json`または`openai.json`、
比較は`comparative.json`を指定する。設定変更後は承認を作り直す。

```sh
uv run --locked lae-sim prepare-interview "$RUN" \
  --scenario fixtures/g2/scenario-collaboration.json --config fixtures/g8/openai.json \
  --questions fixtures/g8/questions.json --output .lae-runs/openai-evaluation-1 \
  > .lae-runs/openai-approval.json
```

これは送信も評価run作成も行わず、`approved:false`の承認対象だけを出力する。
人間が固定本人パッケージ、質問、Provider/モデル、設定・価格・上限を確認し、
承認した場合だけ`approved:true`と非空の`approval_reference`を設定する。
承認はProvider/モデル、本人パッケージdigest、全質問digest、設定digest、
評価ディレクトリの絶対パス（evaluation_id）へ束縛される。
別Provider・別設定・別入力・別出力先へ再利用できない。
比較実行では両Providerそれぞれへの承認が必要である。

```sh
# 人間の承認と環境変数設定が済んだ場合だけ実行する（課金・外部送信あり）
uv run --locked lae-sim interview "$RUN" \
  --scenario fixtures/g2/scenario-collaboration.json --config fixtures/g8/openai.json \
  --questions fixtures/g8/questions.json --output .lae-runs/openai-evaluation-1 \
  --approval .lae-runs/openai-approval.json
```

承認ファイルはローカル管理者が行う明示的承認の記録で、署名サービスやOS管理者に
対する防御ではない。今回、承認trueの実行用ファイルは作成していない。
承認・認証情報不足はNOT READYで試行監査を残し、ネットワークへ進まない。
`retrieved`も固定本人catalogと完全一致を検査し、任意の管理情報を追加できない。
CLIはReplayとG7公開境界を通った本人パッケージだけを生成器へ渡す。

## 監査と公開

sidecarディレクトリは0700、ファイルは0600で新規作成する。

- `inputs.json`: 固定本人パッケージ、質問、設定、承認。管理用。
- `ledger.jsonl`: 送信前の費用予約とusage精算をfsyncした台帳。管理用。
- `provider-N/attempts.jsonl`: 全質問試行。生成文、根拠、5検査、失敗分類、
  Run/Actor/質問ID、各digest、プロンプト/検査器/SDK版、リトライ、usage、時間、価格。
- `provider-N/public.json`: 採用した質問・回答だけ。private_support_idsや棄却文を含まない。
- `evaluation.json`: Provider別結果、機械指標、未評価の意味指標、受入限界。

試行を永続化してから公開履歴を書き出す。棄却/UNKNOWN意味判定/失敗回答は
後続の採用履歴へ登録せず、採用回答も本人パッケージやWorld Truthを更新しない。
生成器には過去回答を再入力しない。監査を消してから再試行する経路はない。
公開候補のtext内にも私的ID混入検査を行う。

現在の自動意味検査は「根拠の文章そのものと認識種別が一致する制限付き引用」および
固定の不明/記憶なし表現に限定する。引用でもepisodeの誤帰属、根拠にないvalue、
採用済みの同じ主張キーへの矛盾を通さない。異なる固定エピソード、明示された
誤認・曖昧さ・推測の引用は世界の正解と異なるだけでは棄却しない。
単なるvalue部分一致は自由文全体の意味の証明にしない。
任意の自然な言い換え・新しい推測・質問への適切性は自動で証明できず、
**INCONCLUSIVEとして公開を保留**する。逐語引用の限定PASSからG8全体のPASSを導かない。
独立した意味監査を追加するまでは、多くのリモート回答が保留され得る。

## 料金・通信の限界

例の価格はUSD/100万text tokenで、Gemini=入力0.30/出力2.50、
OpenAI=入力1.00/出力5.00。上記公式資料を出典として設定に保持し、コードへ固定しない。
キャッシュ割引は使わず入力通常料金で保守的に見積もる。
Geminiはtotal-promptでthinkingを含む出力を数え、OpenAIはAPIのoutput_tokensを使う。

上限はリクエスト数、1リクエスト/評価runのtoken、評価runの推定累積USD。
全Providerが一つの台帳を共有する。各送信前にUTF-8バイト数+schema/指示/余白と
最大出力数を予約し、API usageがあれば精算する。失敗時の不明usageは予約を残す。
応答にusageがなければ停止する。実usageが上限を超えた場合も以後を止める。
台帳の送信前保存失敗では通信せず、送信後保存失敗では既知の応答・usageを失敗監査に保持する。

**事前token推定は公式tokenizerの厳密上界ではなく、実請求額の完全な事前保証ではない。**
ネットワーク切断後のサーバー側処理、価格変更、Providerの再計算も完全には制御できない。
Provider側にも予算・クォータを設定し、余裕を持たせる必要がある。
費用はシミュレーションrunを参照する一回のインタビュー評価run単位で集計する。
別の評価run/別プロセス/アカウント全体の累積請求額を制御するサービスではない。
新評価には新出力先とそれに束縛された人間の承認が必要。中断runを再開して台帳を
初期化する機能はない。同じ出力先は上書きも再開もしない。

retry_onはtimeout/rate-limit/provider-unavailableだけを明示でき、最大3試行。
認証失敗・形式違反・監査棄却を別モデルで自動再生成する機能はない。
ハイブリッドはPhase 1単独とPhase 2比較まで。Primary/FallbackとGenerator/Verifierは
未実装で設定も拒否する。比較の順番は固定で共通上限による打切りも記録する。

## 終了コード

| code | 意味 |
|---|---|
| 0 | 内部検証済みrun/証拠取得、または制限付き採用回答の記録 |
| 2 | 入力/設定/CLI操作パラメータ不正 |
| 3 | 内部検証・保存/IO・生成API失敗 |
| 4 | 取得拒否、承認/認証/SDK/価格準備不足 |
| 5 | 費用/回数/token上限停止 |
| 6 | UNKNOWN・記憶なしの採用、または回答不能 |
| 7 | 監査棄却 |
| 8 | 意味確認不足（INCONCLUSIVE、非公開） |

業務INCOMPLETEは有効なrunならcode 0で、その業務状態をJSONへ別表示する。
API拒否・形式違反はcode 3、回答監査の棄却はcode 7と分ける。
評価のNOT READY/INCONCLUSIVEとコマンドの実行・記録成功は別の欄である。

## 評価・受入と未検証事項

固定11質問は通常/正当根拠/隠れた原因/誘導/新事実/言い換え/矛盾要求/誤認/曖昧さ/
UNKNOWN/回答不能を含む。実モデル比較では全試行（棄却・失敗を含む）を独立に保存する。
自動集計は引用IDの存在精度、API報告token、usage欠落数、応答時間、推定費用。
IDの存在精度と主張の意味的正しさは別である。
創作率、根拠の意味的支持、不明の適切性、誘導追従、言い換え整合性、日本語自然さは
人間の独立評価が必要で、未実施はnull。生成器の自己採点は使わない。
日本語自然さは1–5、他の分母・分子は`evaluation.json`のmetric_definitionsに残す。

対応要求: EP06の入力/公開境界、EP08/09の本人根拠と不明/誤認、EP10の試行追跡、
EP15の棄却公開防止、EP16の再質問監査、SE14/17のLLMと決定的世界の分離、
6.5の不正入力・取得拒否・回答不能の区別。実モデルでの意味保証は未充足である。

検証結果と独立レビューの対応は`g8-validation.md`を参照する。
次は、対象・予算・送信先を人間が承認した限定ライブ比較、独立した意味監査、
その結果を基にした運用方式選択。6.3の受入後に6.5を判定し、VC/VFは別作業で行う。
