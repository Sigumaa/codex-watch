# STARTUP_CHECKLIST

## 作業開始前
- [ ] `.codex/PROPOSED_PLAN.md` が存在し、対象タスクの参照セクションIDが明記されている。
- [ ] `.codex/PLAN_PROGRESS.md` の「現在の実施対象」が最新タスクIDと一致している。
- [ ] `.codex/PROJECT_PLAN.md` のスコープと受け入れ基準に矛盾がない。

## 実装前
- [ ] 担当部品の `task_id` と `depends_on` を確認し、前提依存が解決済みである。
- [ ] 更新対象ファイルに競合予定がなく、直列化が必要な場合は理由を記録した。
- [ ] 必要なシークレット名と環境変数名を一覧化し、未設定項目を明示した。

## 実装後
- [ ] 追加した機能部品ごとに対応テストを作成した。
- [ ] `pytest` を実行し、結果を作業ログへ記録した。
- [ ] 失敗時は復旧手順と再実行結果を作業ログへ記録した。

## コミット前
- [ ] `pre-commit run --all-files` を実行した、または未実施理由を記録した。
- [ ] `PROJECT_PLAN` `PLAN_PROGRESS` `PROPOSED_PLAN` の整合を確認した。
- [ ] コミットメッセージがconventional commit準拠の英語1文である。
