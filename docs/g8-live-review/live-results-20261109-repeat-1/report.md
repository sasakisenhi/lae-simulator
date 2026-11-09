# G8 ライブ評価 再実行1（2026-11-09）

判定: **INCONCLUSIVE**。Tasks 6.3・6.5は未完了。

ユーザーの再実行指示に基づき同一設定・同一質問・22要求を実施。前回記録は保持し、今回内の再試行・補充・条件変更は行っていない。

| Provider | 状態別件数 | 失敗分類 |
|---|---|---|
| gemini | {'generation-failed': 4, 'rejected': 3, 'inconclusive': 4} | {'incomplete-output': 1, 'rate-limit': 2, 'provider-unavailable': 1} |
| openai | {'rejected': 2, 'accepted': 1, 'generation-failed': 8} | {'rate-limit': 8} |

台帳: {"accounted_tokens": 251117, "boundary": "evaluation-run; reservations include failed requests with unknown usage; provider billing is not guaranteed", "estimated_cost_usd": "0.2373678", "limits": {"max_estimated_cost_usd": "2.00", "max_request_tokens": 500000, "max_requests": 22, "max_total_tokens": 2000000}, "requests": 22, "stopped": false}

台帳推定は失敗時の保守的予約を含み、実請求額ではない。usage不明の失敗を無料とは扱わない。

モデル品質の一次・独立意味評価は未実施。棄却/保留の自動判定と創作等の意味評価は区別する。回答欠測が残り、モデル間の品質優劣やG8のPASSは判定しない。

原記録保存先: `/home/sengakuhisai/dev/lae-simulator/.lae-runs/g8-live-comparison-20261109-repeat-1`。CLI終了コード3 / not-accepted。

認証値の出力混入検査成功。コード・プロンプト・設定・旧証拠・タスクチェックは変更していない。

確認対象: answers.mdの全生成文、Provider別attempts.jsonlの監査、evaluation.jsonのusage/台帳、human-scorecard.csvの意味評価欄。
