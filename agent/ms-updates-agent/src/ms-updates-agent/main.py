"""Lab 3 完成版: Foundry Hosted Agent (Microsoft Updates Agent)

このファイルは ``azd ai agent init --deploy-mode code`` で生成される
``main.py`` テンプレートを Lab 2 のロジックで置き換えたものです。
``azd up`` でソースコードがそのまま Foundry にデプロイされ、サービス側でホストされます。
"""

import os

from dotenv import load_dotenv
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

load_dotenv()

INSTRUCTIONS = """あなたは Microsoft 365 と Azure の最新リリース情報を回答する日本語アシスタントです。
必ず MRC MCP のツール (https://www.microsoft.com/releasecommunications/mcp) を使って一次情報を取得し、
回答に出典 URL を添えてください。MRC で取得できない技術詳細や手順は Microsoft Learn MCP
(https://learn.microsoft.com/api/mcp) で補足してかまいません。"""

MRC_URL = "https://www.microsoft.com/releasecommunications/mcp"
LEARN_URL = "https://learn.microsoft.com/api/mcp"


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        # ローカル実行は .env の FOUNDRY_MODEL を使う。デプロイ後の Hosted Agent コンテナには
        # FOUNDRY_MODEL は注入されないため、Foundry が注入する AZURE_AI_MODEL_DEPLOYMENT_NAME に
        # フォールバックする (どちらか一方は必ず設定される)。
        model=os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        name="MSUpdatesAgent",
        instructions=INSTRUCTIONS,
        tools=[
            client.get_mcp_tool(
                name="MRC",
                url=MRC_URL,
                approval_mode="never_require",
            ),
            client.get_mcp_tool(
                name="Learn",
                url=LEARN_URL,
                approval_mode="never_require",
            ),
        ],
        # Hosted Agent では会話履歴を Foundry が管理するため store=False を推奨
        default_options={"store": False},
    )

    # localhost:8088/responses を公開。コンテナ側で Foundry が呼び出す。
    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
