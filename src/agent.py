"""Microsoft 最新情報エージェント (MRC MCP / 会話継続できる対話モード)。

MRC (Microsoft Release Communications) の MCP エンドポイントを client-side
``MCPStreamableHTTPTool`` で接続し、Microsoft 365 / Azure の最新リリース情報を
日本語で出典付きに回答するシングル エージェント。

対話モードでは ``agent.create_session()`` で作った 1 つの session を使い回して
文脈を保持し、応答はストリーミングで逐次表示する。

実行:
    python src/agent.py               # 対話モードに入る (quit / exit / 終了 で終わり)
"""

import asyncio
import os
from pathlib import Path

from agent_framework import MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import dotenv_values


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
    "あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。\n"
    "回答時のルール:\n"
    "- 質問に答えるときは必ず MRC ツールを呼び出して一次情報を取得すること。\n"
    "- MRC で取得した一次情報に加えて、補足や関連ブログ (個別記事 / StackOverflow など) を"
    "探すときは Web 検索を使ってよい。ただし一次情報は MRC を優先すること。\n"
    "- 回答は必ず日本語で書くこと。\n"
    "- 取得した情報には出典 URL を必ず添えること。\n"
    "- ツールの呼び出しや情報取得に失敗した場合は、推測で回答せず、"
    "情報を取得できなかった旨を日本語で正直に伝えること。"
)

EXIT_WORDS = {"quit", "exit", "終了"}


# --- 3. 対話ループ: 1 つの session を使い回して文脈を保持しつつストリーミング応答 ---
async def run_interactive(agent: object) -> None:
    """対話モード: 同じ AgentSession を使い回して文脈を保持しつつストリーミング応答する。"""
    # session は会話開始時に 1 回だけ作り、以降のターンで使い回す。
    session = agent.create_session()
    print("MS Updates Agent。質問を入力してください (quit / exit / 終了 で終わり)")

    while True:
        try:
            user_input = input("\nあなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower() in EXIT_WORDS:
            break
        if not user_input:
            continue

        # 会話 ID を先頭に表示 (サービス側で採番されるまでは pending)。
        print(f"\n[conv:{getattr(session, 'conversation_id', 'pending')}]")
        print("エージェント: ", end="", flush=True)

        # anti-pattern の agent.run_stream(...) は使わず、stream=True で逐次受信する。
        async for chunk in agent.run(user_input, stream=True, session=session):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print()


# --- 4. エージェントを組み立てて対話モードを起動 ---
async def main() -> None:
    project_endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    mrc_mcp = MCPStreamableHTTPTool(
        name="MRC",
        url=MRC_MCP_URL,
        load_prompts=False,
    )

    # canonical pattern: credential は async with、client は代入のみ、
    # agent を async with で閉じる。
    # process_timeout: Windows では az のコールドスタートが既定 10 秒を
    # 超えてトークン取得が timeout することがあるため余裕を持たせる。
    async with AzureCliCredential(process_timeout=30) as credential:
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        )
        # Foundry の Hosted Web Search を併用 (MCP に無い個別ブログ等の補足用)。
        # get_web_search_tool() は client 生成後に取得する Stable な factory。
        # .as_dict() を付けるのが必須: 戻り値 WebSearchTool は dict ではなく
        # MutableMapping なので、そのまま tools= に渡すとフレームワークが
        # 「Can't parse tool.」と警告して黙って破棄してしまう。
        # 注意: Web 検索は Azure OpenAI モデル (例: gpt-4.1-mini) のみで動作する。
        web_search = client.get_web_search_tool().as_dict()
        async with client.as_agent(
            name="MSUpdatesAgent",
            instructions=INSTRUCTIONS,
            tools=[mrc_mcp, web_search],
        ) as agent:
            await run_interactive(agent)


if __name__ == "__main__":
    asyncio.run(main())
