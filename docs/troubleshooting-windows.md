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

## 3. `azd` が PATH に無い / `azd auth login` は `az login` とは別

### 症状

- `azd` を実行すると `The term 'azd' is not recognized ...` になる (一方 `az` は動く)。
- `azd ai agent init` が `not logged in, run 'azd auth login'` で失敗する (`az login` 済みなのに)。
- `azd` をフルパスで起動すると、今度は `AzureDeveloperCLICredential: executable not found on path` で失敗する。

### 原因

- **`azd` (Azure Developer CLI) は `az` (Azure CLI) とは別の実行ファイル・別のログイン**。`az login` と `azd auth login` はそれぞれ必要。
- Windows の winget 等で入れた `azd` は `%LOCALAPPDATA%\Programs\Azure Dev CLI\azd.exe` にあり、シェルの `PATH` に通っていないことがある。
- `azd` の内部処理 (Foundry プロジェクト照会など) は認証情報プロバイダ `AzureDeveloperCLICredential` を使い、これが**子プロセスで `azd` を PATH から探す**。そのため `azd` をフルパスで起動しただけでは内部認証が `executable not found on path` で失敗する。**`azd` 自体を PATH に通す**必要がある。

### 対処

`azd` を PATH に通す (新しいセッションでも有効にする例):

```powershell
$azdDir = "$env:LOCALAPPDATA\Programs\Azure Dev CLI"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -split ';' -notcontains $azdDir) {
    [Environment]::SetEnvironmentVariable('Path', $userPath.TrimEnd(';') + ';' + $azdDir, 'User')
}
$env:Path += ";$azdDir"   # 現在のセッションにも即反映
```

> [!NOTE]
> `setx` は `PATH` を 1024 文字で切り詰める既知の問題があるため、上記のように .NET の `SetEnvironmentVariable` で追記するのが安全。

その後、Azure へサインインする (ブラウザが開く):

```powershell
azd auth login
azd auth login --check-status   # ログイン済みか確認
```
