# CLAUDE.md — Claude Code 向け設定

このファイルは **Claude Code** がこのリポジトリで作業するときに自動で読み込む設定です。GitHub Copilot 用の [`.github/copilot-instructions.md`](.github/copilot-instructions.md) と等価な「ワークショップ全体の前提・既定値」を Claude にも与えるための入口です。

> [!IMPORTANT]
> 本リポジトリは **ハンズオン ワークショップ** です。Lab 0 → 1 → 2 → 3 → 4 → 5 の順に進む前提で書かれています。模範解答は [`solutions/`](solutions/) 配下にあります。詳細は [`docs/README.md`](docs/README.md) を参照してください。

## このリポジトリは何か

- **GitHub Copilot × Microsoft Agent Framework 1.8.1 × Microsoft Foundry のハンズオン**。
- 参加者は Lab 2 以降で [`src/`](src) 配下に Python コードを書き、Lab 3 で `azd up` し、Lab 4 で評価し、Lab 5 で CI/CD を組みます。
- Copilot だけでなく **Claude Code でも同じ Lab を進められる**ように、本ファイルと [`.claude/`](.claude/) を用意しています。

## 単一ソース ポリシー

ワークショップの規約・API 知識は **Copilot と Claude で共有**します。Claude Code は CLAUDE.md / サブエージェント / スラッシュ コマンドの本文に書かれた **`@相対パス`** を再帰的にインライン展開するため、以下では `@import` で既存ファイルを取り込みます (内容を重複させない)。

### ワークショップ全体の既定値 (必ず参照)

@.github/copilot-instructions.md

### コーディング規約 (ファイル別自動適用)

`.py` ファイルを編集するときは以下に従ってください。

@.github/instructions/python.instructions.md

`.md` ファイルを編集するときは以下に従ってください。

@.github/instructions/docs.instructions.md

### Agent Framework API ナレッジ ベース

エージェント実装や API パターンを書くときは、必ず [`kb-1.8.0/README.md`](kb-1.8.0/README.md) のルーティング表から該当ページを引いてから着手してください。網羅的に全件読まないこと (27 patterns / 13 anti-patterns / 多数の API 参照ページ)。

- [`kb-1.8.0/README.md`](kb-1.8.0/README.md) — ナビゲーション
- [`kb-1.8.0/patterns/`](kb-1.8.0/patterns/) — 検証済みパターン
- [`kb-1.8.0/anti-patterns/`](kb-1.8.0/anti-patterns/) — 提案してはいけない API / コード形
- [`kb-1.8.0/api-reference/1.8.0/`](kb-1.8.0/api-reference/1.8.0/) — API シンボル単位の詳細

## Claude 専用アセット

`.claude/` 配下に Claude Code 専用の **サブエージェント** と **スラッシュ コマンド** を置いています。Copilot の `.github/agents/` `.github/prompts/` と 1 対 1 で対応します。

| Claude 側 | Copilot 側 (相当物) | 用途 |
|---|---|---|
| [`.claude/agents/af-architect.md`](.claude/agents/af-architect.md) | [`.github/agents/af-architect.agent.md`](.github/agents/af-architect.agent.md) | 設計フェーズの advisor (コードを書かない) |
| [`.claude/agents/af-implementer.md`](.claude/agents/af-implementer.md) | [`.github/agents/af-implementer.agent.md`](.github/agents/af-implementer.agent.md) | KB に従って最小差分でコードを書く |
| [`.claude/commands/deploy-hosted-agent.md`](.claude/commands/deploy-hosted-agent.md) | [`.github/prompts/deploy-hosted-agent.prompt.md`](.github/prompts/deploy-hosted-agent.prompt.md) | Lab 3 のショートカット (`azd ai agent init` + `azd up`) |
| [`.claude/commands/add-cloud-evaluation.md`](.claude/commands/add-cloud-evaluation.md) | [`.github/prompts/add-cloud-evaluation.prompt.md`](.github/prompts/add-cloud-evaluation.prompt.md) | Lab 4 の評価スクリプト生成 |
| [`.claude/commands/add-mcp-tool.md`](.claude/commands/add-mcp-tool.md) | [`.github/prompts/add-mcp-tool.prompt.md`](.github/prompts/add-mcp-tool.prompt.md) | 既存エージェントに MCP を 1 つ追加 |

詳細は [`.claude/README.md`](.claude/README.md) を参照してください。

## Claude Code 利用上の注意

- **CLAUDE.md / サブエージェント / コマンドはすべて `@相対パス` で他ファイルを取り込めます** (再帰深度 5)。本リポジトリでは Copilot 用ファイルを source-of-truth として共有しています。Copilot 側を更新すれば Claude 側も自動的に反映されます。
- **削除されている API を生成しないこと** (1.8 系で削除済み): `agent.run_stream`、`Message(text=...)`、`AzureAIClient`、`HostedWebSearchTool` / `HostedCodeInterpreterTool` / `HostedFileSearchTool`、`select_toolbox_tools`、`WorkflowBuilder.register_agent` ほか。詳細は [`kb-1.8.0/anti-patterns/removed-apis-since-1.0.md`](kb-1.8.0/anti-patterns/removed-apis-since-1.0.md)。
- **既定リージョン・モデル・ロールを勝手に書き換えない**。`eastus` / `gpt-4o` 等を提案すると Lab 3 のデプロイが落ちます ([`.github/copilot-instructions.md`](.github/copilot-instructions.md) の表を参照)。
- **`.env` は自動ロードされません**。Python スクリプト先頭で `from dotenv import load_dotenv; load_dotenv()` を必ず呼ぶこと。
- **既存 `docs/` の Lab 手順を勝手に書き換えない**。参加者が混乱します。
- **Windows 環境では `AzureCliCredential` のタイムアウトに注意**。`az` のコールドスタートが遅く、既定 `process_timeout=10` 秒を超えて `Failed to invoke the Azure CLI` で落ちることがある。自分で書くスクリプトでは `AzureCliCredential(process_timeout=30)` を既定にする。また Agent Framework のスクリプトは Git Bash ではなく **PowerShell から実行**する (Git Bash 経由だと `cmd` に渡る PATH 形式の都合で `az` を発見できない)。詳細は [`docs/troubleshooting-windows.md`](docs/troubleshooting-windows.md)。

## 関連ドキュメント

- [`docs/README.md`](docs/README.md) — ワークショップ全体の Lab 一覧
- [`solutions/README.md`](solutions/README.md) — 模範解答へのインデックス
- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — Copilot 側の同等設定 (本ファイルが import する元)
