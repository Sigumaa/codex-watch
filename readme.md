# codexwatch

`openai/codex` の `main` マージPRとReleaseを監視し、要約をDiscord Webhookへ通知する。

## Requirements

- Python 3.12+
- `OPENAI_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `GITHUB_TOKEN`

## Environment Variables

`.env.example` を参照。

## Behavior

- stateが空の初回実行では最新マージPR時点を保存し、過去PR通知は送信しない。
- stateが空の初回実行では最新Release時点を保存し、過去Release通知は送信しない。
- 通知成功ごとにstateを保存する。
- 1回の実行通知件数は `CODEXWATCH_MAX_NOTIFICATIONS_PER_RUN`（default: 20）で制限する。
- `alpha/α` を含むRelease名・タグ、および `prerelease` / `draft` は通知しない。
- `--release-tag <tag>` で指定Releaseを要約表示できる。`--send-release-to-discord` 指定時はDiscordへ送信する。

## Local Run

```bash
python -m pip install -e .
python -m codexwatch.main --dry-run
python -m codexwatch.main --no-dry-run
python -m codexwatch.main --release-tag rust-v0.102.0
python -m codexwatch.main --release-tag rust-v0.102.0 --send-release-to-discord --no-dry-run
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
