# codexwatch

`openai/codex` の `main` マージPRを監視し、要約をDiscord Webhookへ通知する。

## Requirements

- Python 3.12+
- `OPENAI_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `GITHUB_TOKEN`（未設定時は匿名リクエスト）

## Environment Variables

`.env.example` を参照。

## Local Run

```bash
python -m pip install -e .
python -m codexwatch.main --dry-run
python -m codexwatch.main --no-dry-run
```

## Tests

```bash
python -m pytest
```

## GitHub Actions

`.github/workflows/watch-codex-pr.yml` は以下を実行する。

- 10分ごとの定期実行
- `workflow_dispatch` 手動実行
- `state/state.json` のキャッシュ復元・保存
