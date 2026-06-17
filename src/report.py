"""Lab 2 ★Stretch: 構造化出力でリリース レポートを生成する (Pydantic + JSON 保存)。

``src/agent.py`` と同じエージェント構成 (MRC MCP) のまま、自然言語ではなく
Pydantic モデルで応答を受け取り、後段の処理 (メール / Slack / CI 評価器など) に
そのまま渡せる構造化 JSON を ``data/report_<YYYYMMDD-HHMMSS>.json`` に書き出す。

実行:
    python src/report.py
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError


# --- 1. .env をロード (fill-only: 既存の環境変数は上書きしない) ---
_DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"
for _k, _v in dotenv_values(_DOTENV_PATH).items():
    if _v is None:
        continue
    if not (os.getenv(_k) or "").strip():
        os.environ[_k] = _v


def _require_env(name: str) -> str:
    """必須環境変数を取得する。未設定 / 空文字なら fail-fast で RuntimeError。"""
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"必須の環境変数が未設定または空です: {name}. "
            ".env / export / Codespaces secrets を確認して再実行してください。"
        )
    return value


# --- 2. MRC MCP (認証不要のパブリック エンドポイント) ---
MRC_MCP_URL = "https://www.microsoft.com/releasecommunications/mcp"

INSTRUCTIONS = (
    "あなたは Microsoft 365 と Azure のリリース情報を構造化して返す日本語アシスタントです。\n"
    "回答時のルール:\n"
    "- 必ず MRC ツールを呼び出して一次情報を取得すること (推測で埋めない)。\n"
    "- 出力は要求された ReleaseReport スキーマに厳密に一致させること。\n"
    "- 各 item の url には MRC から得た出典 URL を入れること。\n"
    "- summary 系のテキストは日本語で書くこと。"
)

QUERY = "直近 GA になった主要な Microsoft 365 / Azure 更新を 5 件、構造化して返してください。"


# --- 3. 構造化出力のスキーマ (Pydantic v2) ---
class ReleaseItem(BaseModel):
    """1 件のリリース更新項目。"""

    product: str = Field(description="製品 / サービス名 (例: Azure Functions, Microsoft Teams)")
    title: str = Field(description="更新のタイトル")
    status: str = Field(description="ステータス (GA / Public Preview / Retiring など)")
    released_at: str = Field(description="GA / プレビュー化された日付 (YYYY-MM-DD 推奨)")
    url: str = Field(description="出典 URL (MRC から取得したもの)")
    summary: str = Field(description="50 文字程度の日本語サマリ")


class ReleaseReport(BaseModel):
    """レポート全体。後段処理はこの構造を読む。"""

    period: str = Field(description="レポート対象期間 (例: 2026年5月)")
    summary: str = Field(description="3〜5 行の日本語総括")
    items: list[ReleaseItem] = Field(description="主要な更新項目 (5 件程度)")


# --- 4. エージェントを組み立てて構造化レポートを生成・保存 ---
async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    mrc_mcp = MCPStreamableHTTPTool(
        name="MRC",
        url=MRC_MCP_URL,
        load_prompts=False,
    )

    # canonical pattern: credential は async with、client は代入のみ、agent を async with。
    # process_timeout: Windows では az のコールドスタートが既定 10 秒を超えることがある。
    async with AzureCliCredential(process_timeout=30) as credential:
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        )
        async with client.as_agent(
            name="MSUpdatesReporter",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp],
        ) as agent:
            # 構造化出力は per-run override の options={"response_format": ...} で要求する
            # (1.8.0 では streaming で構造化フィールドは取れないため非ストリーミング)。
            response = await agent.run(QUERY, options={"response_format": ReleaseReport})

    # .text は生 JSON 文字列、.value が parse 済みの Pydantic インスタンス。
    try:
        report = response.value
    except ValidationError as err:
        print("構造化応答の parse に失敗しました:", err, file=sys.stderr)
        print("--- 生レスポンス ---", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"report_{stamp}.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"Saved: {out_path}")
    print(f"  period={report.period}  items={len(report.items)}")


if __name__ == "__main__":
    asyncio.run(main())
