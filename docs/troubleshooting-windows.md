# Windows 環境での既知のハマりどころ (Claude Code / ローカル実行)

Windows + Azure CLI のローカル環境で Agent Framework のスクリプトを動かすときに遭遇しうる、環境固有の注意点をまとめます。Lab 手順そのものではなく、**実行環境のクセ**に関するメモです。

## 1. `AzureCliCredential` が `Failed to invoke the Azure CLI` で落ちる

### 症状

`FoundryChatClient` + `AzureCliCredential` を使うスクリプト (例: [`solutions/lab0/scripts/check_setup.py`](../solutions/lab0/scripts/check_setup.py)) を実行すると、認証段階で次の例外が出る:

```text
azure.identity._exceptions.CredentialUnavailableError: Failed to invoke the Azure CLI
subprocess.TimeoutExpired: Command '[... 'az.cmd', 'account', 'get-access-token', ...]' timed out after 10 seconds
```

### 原因

`AzureCliCredential` は内部で `az account get-access-token` を **サブプロセスとして起動**し、既定の `process_timeout=10` 秒で待つ。Windows では `az` の実体が `az.cmd` (バッチ → Python 起動) のため**コールドスタートが遅く**、マシンによってはトークン取得に 10 秒前後かかり、既定タイムアウトをギリギリ超えて失敗することがある。Azure へのサインインや権限自体は正常でも発生する、純粋な**起動性能の問題**。

### 対処

credential 生成時に `process_timeout` を明示的に延ばす:

```python
from azure.identity.aio import AzureCliCredential

credential = AzureCliCredential(process_timeout=30)  # 既定 10 秒 → 30 秒
```

自分で書くスクリプト (Lab 2 以降) ではこの形を既定にしておくと安定する。

> [!NOTE]
> 模範解答 [`solutions/`](../solutions/) のスクリプトは標準的な環境を想定して `process_timeout` を指定していない。上記の症状が出る環境では、各自のスクリプト側で `process_timeout` を足すこと。

## 2. Git Bash から Python を起動すると `az` を見つけられない

### 症状

Git Bash 経由で `python script.py` を実行すると、`AzureCliCredential` が `az` を呼べず失敗する。一方、シェルで直接 `az` コマンドは動く。

### 原因

Git Bash の `PATH` は POSIX 形式 (`/c/...`)。Python が認証時に `cmd` 経由で `az` を起動しようとすると、Windows の `cmd` がこの POSIX 形式 `PATH` を解釈できず、`az` を発見できない。

### 対処

Agent Framework のスクリプトは **PowerShell (または VS Code の統合ターミナル)** から実行する。`az login` と `azd auth login` も同じシェルで済ませておく。
