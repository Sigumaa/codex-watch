# PROJECT_PLAN

## 目的
- openai/codex の `main` へマージされたPRを10分間隔で監視し、差分要約をDiscord Webhookへ送信する。
- 重複送信を防ぐため、`last_merged_at` と `processed_pr_ids` を `state.json` として管理する。

## スコープ
- GitHub APIから対象PRを取得し、`main` マージ済みイベントのみを抽出する処理を実装する。
- OpenAI Python SDKで要約文を生成し、Discord Webhookへ投稿する処理を実装する。
- GitHub Actions Cacheを使って `state.json` を保持し、次回実行へ状態を引き継ぐ。
- Python + uv + GitHub Actionsで継続実行できる構成を整備する。

## 非スコープ
- `openai/codex` 以外のリポジトリ監視は対象外とする。
- Discord双方向連携、ダッシュボード、DB保存は対象外とする。
- 監視間隔の動的変更や手動承認フローは対象外とする。

## 受け入れ基準
- 10分間隔のworkflowがpush/PRに加えて定期実行で起動可能な状態である。
- 直近実行からの新規マージPRのみを通知し、同一PRを再通知しない。
- 通知本文にPR番号、タイトル、マージ日時、要約が含まれる。
- 最低限のCI導線として `pytest` がpull_request/pushで実行される。

## フェーズ
- Phase 0: ブートストラップ（計画正本化、進捗正本化、チェックリスト、CI最小導線）。
- Phase 1: 監視処理実装（PR取得、状態管理、要約生成、Discord送信）。
- Phase 2: テスト拡充と運用安定化（失敗復旧、品質ゲート強化、運用手順確定）。
