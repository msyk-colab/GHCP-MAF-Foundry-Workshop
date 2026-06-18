"""Lab 4: Foundry Cloud Evaluation を Lab 3 の Hosted Agent に対して実行する。

``data/eval_inputs.json`` の各 query を Hosted Agent (``azure_ai_agent`` ターゲット) に
投げ、builtin の ``intent_resolution`` 評価器で採点する Cloud Evaluation run を作成する。
run 完了までポーリングし、最後に Foundry の評価結果 URL を表示する。
このスクリプトは Lab 5 の CI/CD パイプラインからもそのまま再利用する。

実行:
    python src/evaluate.py
"""

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import dotenv_values


TERMINAL_STATUSES = {"completed", "failed", "canceled"}
POLL_INTERVAL_SECONDS = 60
MAX_POLL_ATTEMPTS = 30


def load_dotenv_fill_only() -> None:
    """既存の (非空) 環境変数を上書きせずに .env を読み込む (fill-only)。"""
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    for key, value in dotenv_values(dotenv_path).items():
        if value is None:
            continue
        if not (os.getenv(key) or "").strip():
            os.environ[key] = value


def require_env(name: str) -> str:
    """必須環境変数を取得する。未設定 / 空文字なら fail-fast で RuntimeError。"""
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"{name} が未設定または空です。.env に {name} を設定してから再実行してください。"
        )
    return value


def load_eval_inputs(path: Path) -> list[dict[str, str]]:
    """ワークショップの JSON 配列から評価入力を読み込む。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"評価データが見つかりません: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"評価データの JSON が不正です: {path}") from exc

    if not isinstance(data, list):
        raise RuntimeError(f"評価データは JSON 配列にしてください: {path}")

    inputs: list[dict[str, str]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("query"), str):
            raise RuntimeError(f"評価データ {index} 件目には文字列の query が必要です。")
        query = item["query"].strip()
        if not query:
            raise RuntimeError(f"評価データ {index} 件目の query が空です。")
        inputs.append({"query": query})

    return inputs


def build_testing_criteria(model_deployment: str) -> list[dict[str, Any]]:
    """Cloud Evaluation 用の intent_resolution 評価器定義を組み立てる。"""
    return [
        {
            "type": "azure_ai_evaluator",
            "name": "intent_resolution",
            "evaluator_name": "builtin.intent_resolution",
            "initialization_parameters": {"deployment_name": model_deployment},
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        }
    ]


def build_data_source(
    inputs: list[dict[str, str]], agent_name: str, agent_version: str
) -> dict[str, Any]:
    """Hosted Agent ターゲットとインラインの評価入力ソースを組み立てる。"""
    return {
        "type": "azure_ai_target_completions",
        "source": {
            "type": "file_content",
            "content": [{"item": item} for item in inputs],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": {
                        "type": "input_text",
                        "text": "与えられた質問に出典付きで簡潔に答えてください。",
                    },
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": {"type": "input_text", "text": "{{item.query}}"},
                },
            ],
        },
        "target": {
            "type": "azure_ai_agent",
            "name": agent_name,
            "version": agent_version,
        },
    }


def main() -> None:
    """Foundry Cloud Evaluation の run を作成して実行する。"""
    load_dotenv_fill_only()

    project_endpoint = require_env("FOUNDRY_PROJECT_ENDPOINT")
    model_deployment = require_env("FOUNDRY_MODEL")
    agent_name = require_env("HOSTED_AGENT_NAME")
    agent_version = os.getenv("HOSTED_AGENT_VERSION", "1").strip() or "1"
    inputs = load_eval_inputs(Path("data/eval_inputs.json"))
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    # process_timeout: Windows では az のコールドスタートが既定 10 秒を超えることがある。
    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=AzureCliCredential(process_timeout=30),
    )
    client = project_client.get_openai_client()

    eval_definition = client.evals.create(
        name=f"ms-updates-eval-{timestamp}",
        data_source_config={
            "type": "custom",
            "item_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "include_sample_schema": True,
        },
        testing_criteria=build_testing_criteria(model_deployment),
    )
    print(f"Evaluation definition: {eval_definition.id}")

    run = client.evals.runs.create(
        eval_id=eval_definition.id,
        name=f"run-{timestamp}",
        data_source=build_data_source(inputs, agent_name, agent_version),
    )
    print(f"Run started: {run.id}")

    final_status = "unknown"
    for _ in range(MAX_POLL_ATTEMPTS):
        status = client.evals.runs.retrieve(eval_id=eval_definition.id, run_id=run.id)
        final_status = status.status
        print(f"  status={final_status}")
        if final_status in TERMINAL_STATUSES:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    result_url = f"https://ai.azure.com/evaluation/{eval_definition.id}/runs/{run.id}"
    print(f"\nResult: {result_url}")

    if final_status != "completed":
        raise RuntimeError(f"Cloud Evaluation run が completed になりませんでした: {final_status}")

    # ★Stretch (5-6): 合格率が閾値未満なら CI を fail させる品質ゲート。
    # 閾値は EVAL_PASS_THRESHOLD で上書き可能 (既定 0.7)。
    final = client.evals.runs.retrieve(eval_id=eval_definition.id, run_id=run.id)
    counts = getattr(final, "result_counts", None)
    passed = getattr(counts, "passed", 0) or 0
    failed = getattr(counts, "failed", 0) or 0
    errored = getattr(counts, "errored", 0) or 0
    skipped = getattr(counts, "skipped", 0) or 0
    total = getattr(counts, "total", 0) or 0
    ratio = passed / total if total else 0.0
    # errored = 採点不能 (例: エージェントが空応答 → evaluator が "Response string cannot
    # be empty")。pass_ratio は errored も分母に含める (= 厳しめ)。Foundry ポータルの
    # 評価器スコア (%) は採点済み件数 passed+failed を分母にするため値がズレる点に注意。
    print(
        f"result_counts: passed={passed} failed={failed} errored={errored} "
        f"skipped={skipped} total={total}"
    )
    print(f"pass_ratio={ratio:.2f} ({passed}/{total})")

    # 未設定 / 空文字 (GitHub Actions の vars 未設定時) は既定 0.7。
    threshold = float((os.getenv("EVAL_PASS_THRESHOLD") or "0.7").strip())
    if ratio < threshold:
        # ::error:: は GitHub Actions の注釈構文 (PR の Files changed に警告マーカー)。
        print(f"::error::pass_ratio {ratio:.2f} < threshold {threshold}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
