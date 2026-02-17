# PROPOSED_PLAN

## PP-01 Plan Commitment Summary
本計画の目的は、`openai/codex` の `main` へのマージPRを10分ごとに監視し、要約をDiscord Webhookへ送信する運用を成立させること。重複防止のため `last_merged_at` と `processed_pr_ids` を保持する状態管理を標準化する。
期限は Phase 0 ブートストラップを先行完了し、続く実装フェーズへ移行可能な状態を2026-02-17時点で確定すること。完了条件は、計画正本3ファイルと開始チェックリスト、`pytest` 導線付きCIを作成し、以後の委譲で参照可能にすること。
参照: `.codex/PROJECT_PLAN.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/proposed-plan-contract.md`

## PP-02 Current Plan Context
`PROJECT_PLAN` の対象フェーズは Phase 0 であり、今回タスクは実装前準備の固定化に限定する。`PLAN_PROGRESS` の現在対象と `PROPOSED_PLAN` のセクションIDを一致させ、参照元の一本化を行う。
差分判定として、リポジトリ内に `.codex` と `.github/workflows` の必須ファイルが欠落していたため新規作成を実施する。整合判定は、欠落補完のみを行い既存運用を上書きしない構成で一致している。
参照: `.codex/PROJECT_PLAN.md`, `.codex/PLAN_PROGRESS.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/bootstrap-file-contract.md`

## PP-03 Scope and Success Criteria
対象スコープは、計画正本化、進捗正本化、開始チェックリスト作成、最小CI導線作成の4点である。受け入れ基準は、`PP-01` から `PP-10` の契約順守と、`push/pull_request` で `pytest` が起動するworkflow定義が存在すること。
非対象スコープは、監視ロジック本体、OpenAI要約生成ロジック本体、Discord送信ロジック本体の実装である。これらは Phase 1 以降の機能部品として別タスクで実施する。
参照: `.codex/PROJECT_PLAN.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/proposed-plan-contract.md`

## PP-04 Dependencies and Constraints
依存関係は、GitHub Actions、Python実行環境、uvによる依存管理、OpenAI Python SDK、Discord Webhook設定である。外部要因としてGitHub APIとDiscord APIの可用性、認証情報の有効性が実行結果へ影響する。
環境制約として、重複防止状態を `state.json` で永続化し、実行間でキャッシュ復元できる設計が必要となる。運用制約として、監視対象は `openai/codex` の `main` に限定し、通知負荷を抑える。
参照: `.codex/PROJECT_PLAN.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/orchestration-rules.md`

## PP-05 Component Breakdown
- C-01 名前: Scheduler and Runner / 目的: 10分間隔起動とジョブ実行入口を定義する / 依存: なし / 担当: implementation
- C-02 名前: Merged PR Collector / 目的: `openai/codex` の `main` マージPRを取得し新規候補を抽出する / 依存: C-01 / 担当: implementation
- C-03 名前: State Cache Manager / 目的: `state.json` の読込・更新・保存を行い重複送信を防止する / 依存: C-01 / 担当: implementation
- C-04 名前: Summary and Discord Notifier / 目的: PR情報を要約しWebhookへ送信する / 依存: C-02, C-03 / 担当: implementation
本分解は実装・レビュー・テスト・コミット委譲の基準単位として使用し、以後のタスクID付与をこの4部品に一致させる。
参照: `/home/shiyui/.codex/skills/subagent-manager-workflow/references/proposed-plan-contract.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/orchestration-rules.md`

## PP-06 Subagent Assignment
- C-01 依頼タイミング: Phase 1開始直後 / 完了条件: 10分cronと手動実行の入口が定義される / 返却物: workflow差分と実行手順メモ
- C-02 依頼タイミング: C-01完了報告受領後 / 完了条件: マージPR取得と新規候補抽出ロジックがテスト付きで実装される / 返却物: 実装コード、単体テスト、変更ファイル一覧
- C-03 依頼タイミング: C-01完了報告受領後 / 完了条件: `state.json` の永続化I/Oと重複判定がテスト付きで実装される / 返却物: 実装コード、単体テスト、失敗時復旧メモ
- C-04 依頼タイミング: C-02/C-03の反映完了後 / 完了条件: 要約生成とDiscord投稿が統合され通知フォーマットが固定される / 返却物: 実装コード、統合テスト、サンプル通知本文
各依頼は `implementation -> review -> test -> commit` の順で担当分離し、同一部品に対する順序依存を維持する。
参照: `/home/shiyui/.codex/skills/subagent-manager-workflow/references/proposed-plan-contract.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/orchestration-rules.md`

## PP-07 Parallelism and Sequencing
並列判定: C-02とC-03は入出力依存がなく、更新対象ファイルを分離できる前提で並列実行可能とする。C-04はC-02/C-03の成果を入力として利用するため直列実行とする。
直列化理由: C-04はPR抽出結果と重複判定結果の双方が確定していないと通知正文が確定しない。品質ゲート順序を維持するため、部品ごとの `implementation -> review -> test -> commit` を崩さない。
待ち合わせ条件: レビュー委譲前に実装担当の完了報告と変更ファイル一覧を受領する。テスト委譲前にレビュー指摘反映完了を確認し、コミット委譲前に必須テスト結果と失敗時復旧ログを確認する。
参照: `/home/shiyui/.codex/skills/subagent-manager-workflow/references/orchestration-rules.md`

## PP-08 Quality Gates and Tests
必須テストは、C-02のPR抽出条件テスト、C-03の状態遷移テスト、C-04の通知フォーマットテストを最低ラインとする。CI品質ゲートは `pull_request` と `push` で `pytest` を実行し、失敗時は該当部品のimplementationへ戻して再委譲する。
品質ゲートは部品単位で結果を記録し、`PLAN_PROGRESS` の実施ログに反映する。例外運用を行う場合は `DG-05` の相談判定を実施し、承認なしでskipしない。
参照: `.github/workflows/ci.yml`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/bootstrap-file-contract.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/decision-gates.md`

## PP-09 Risks and Unknowns
リスクとして、GitHub APIの取得失敗、OpenAI APIコスト増加、Discord Webhook到達失敗がある。運用開始前に再試行方針と失敗時ログ項目を固定し、異常時の切り戻し経路を明示する。
DG-01 判定結果: no（仕様・優先度・期限の変更は発生していない）。DG-02 判定結果: no（欠落ファイルの追加のみで既存運用の破壊的変更はない）。DG-03 判定結果: no（外部契約条件は既定前提で許容されている）。
参照: `/home/shiyui/.codex/skills/subagent-manager-workflow/references/decision-gates.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/proposed-plan-contract.md`

## PP-10 Communication and Reporting
中間報告: 進捗は「正本化状況」「対象フェーズ」「並列実行中」「待機中」「ブロッカー」「相談要否」を固定項目として更新する。更新頻度は部品単位の状態変化時と待ち合わせ完了時とする。
最終報告: 「完了スコープ」「Proposed Plan更新要約」「変更ファイル一覧」「検証コマンド」「残課題」を固定項目として提出する。エスカレーション条件は `DG-xx` が yes となる判定が出た時点とする。
参照: `/home/shiyui/.codex/skills/subagent-manager-workflow/references/report-format.md`, `/home/shiyui/.codex/skills/subagent-manager-workflow/references/decision-gates.md`
