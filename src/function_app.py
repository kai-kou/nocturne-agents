"""Function App エントリポイント。

静的サイト・Agent-friendly エンドポイント・デモ用 anonymous API を含む。
既存 Blueprint（day_lane / night_lane）はそのまま function key 認証を維持する。
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import azure.functions as func

from blueprints.day_lane import bp as day_lane_bp
from blueprints.night_lane import bp as night_lane_bp

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

app.register_blueprint(day_lane_bp)
app.register_blueprint(night_lane_bp)

logger = logging.getLogger(__name__)
_STATIC_DIR = Path(__file__).parent / "static"


def _serve_static(rel_path: str, default_mime: str = "application/octet-stream",
                  cache_seconds: int = 0) -> func.HttpResponse:
    """静的ファイルを返す（パストラバーサル防止付き）。"""
    target = (_STATIC_DIR / rel_path).resolve()
    try:
        target.relative_to(_STATIC_DIR.resolve())
    except ValueError:
        return func.HttpResponse("Forbidden", status_code=403)
    if not target.is_file():
        return func.HttpResponse("Not Found", status_code=404)
    mime, _ = mimetypes.guess_type(str(target))
    headers = {}
    if cache_seconds > 0:
        headers["Cache-Control"] = f"public, max-age={cache_seconds}"
    return func.HttpResponse(
        target.read_bytes(),
        mimetype=mime or default_mime,
        status_code=200,
        headers=headers,
    )


@app.route(route="dashboard", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """ダッシュボード /api/dashboard を返す。"""
    return _serve_static("index.html", "text/html; charset=utf-8")


@app.route(route="home", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def home(req: func.HttpRequest) -> func.HttpResponse:
    """/api/home エイリアス（ダッシュボードと同じ）。"""
    return _serve_static("index.html", "text/html; charset=utf-8")


@app.route(route="console", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def console_dashboard(req: func.HttpRequest) -> func.HttpResponse:
    """稼働ダッシュボード /api/console を返す（リアルタイム表示）。"""
    return _serve_static("console.html", "text/html; charset=utf-8")


@app.route(route="console/live", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def console_live(req: func.HttpRequest) -> func.HttpResponse:
    """直近のヘルスチェック実データを返す（ANONYMOUS・匿名化済み）。

    Cosmos DB の post_history から最新 N 件を取得し、リスクスコア・主要要因・
    時刻・投稿短縮テキストのみを返す。author_id は @kinamocchi_tech /
    @k_aik_ou のラベルに置換（個人情報マスク）。
    """
    try:
        from shared.cosmos_client import SharedCoreRepository
    except Exception:
        return func.HttpResponse(
            json.dumps({"posts": [], "note": "cosmos client unavailable"}),
            mimetype="application/json", status_code=200,
        )

    limit = min(int(req.params.get("limit", "5")), 20)
    user_label = {
        "2035613655828717568": "@kinamocchi_tech",
        "984701174421966848": "@k_aik_ou",
    }
    try:
        repo = SharedCoreRepository()
        results = repo.query(
            "SELECT TOP @lim * FROM c WHERE c.container_type='post_history' "
            "AND NOT STARTSWITH(c.text, 'RT @') "
            "ORDER BY c.created_at DESC",
            [{"name": "@lim", "value": limit}],
        )
        posts = []
        for r in results or []:
            text = r.get("text", "") or ""
            # PostHistory モデル上のフィールド名は 'author'（author_id ではない）
            author = str(r.get("author", "") or r.get("author_id", ""))
            # tweet 本来の created_at がなければ retrieved_at をフォールバックに使う
            created = r.get("created_at") or r.get("retrieved_at", "")
            posts.append({
                "id": r.get("id", ""),
                "tweet_id": r.get("tweet_id", ""),
                "created_at": created,
                "author_label": user_label.get(author, "@anonymous"),
                "text_excerpt": (text[:120] + "…") if len(text) > 120 else text,
                "risk_score": r.get("risk_score", 0),
                "matched_keywords": r.get("matched_keywords", []) or r.get("keywords_matched", []),
            })
        return func.HttpResponse(
            json.dumps({"posts": posts, "count": len(posts)}, ensure_ascii=False),
            mimetype="application/json", status_code=200,
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("console_live error: %s", exc)
        return func.HttpResponse(
            json.dumps({"posts": [], "error": "fetch_failed"}),
            mimetype="application/json", status_code=200,
        )


_DATA_DIR = Path(__file__).parent / "data"


@app.route(route="static/data/{filename}", methods=["GET"],
           auth_level=func.AuthLevel.ANONYMOUS)
def static_data(req: func.HttpRequest) -> func.HttpResponse:
    """/api/static/data/* で incident-corpus.json などのデータ配信。"""
    filename = req.route_params.get("filename", "")
    target = (_DATA_DIR / filename).resolve()
    try:
        target.relative_to(_DATA_DIR.resolve())
    except ValueError:
        return func.HttpResponse("Forbidden", status_code=403)
    if not target.is_file():
        return func.HttpResponse("Not Found", status_code=404)
    return func.HttpResponse(
        target.read_bytes(),
        mimetype="application/json",
        status_code=200,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.route(route="static/{filename}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def static_files(req: func.HttpRequest) -> func.HttpResponse:
    """/api/static/* を配信（CSS / JS など）。"""
    filename = req.route_params.get("filename", "")
    return _serve_static(filename, cache_seconds=3600)


@app.route(route="static/img/{filename}", methods=["GET"],
           auth_level=func.AuthLevel.ANONYMOUS)
def static_img(req: func.HttpRequest) -> func.HttpResponse:
    """/api/static/img/* で画像を配信（長期キャッシュ・1 日）。"""
    filename = req.route_params.get("filename", "")
    return _serve_static(f"img/{filename}", "image/png", cache_seconds=86400)


@app.route(route="static/img/agents/{filename}", methods=["GET"],
           auth_level=func.AuthLevel.ANONYMOUS)
def static_img_agents(req: func.HttpRequest) -> func.HttpResponse:
    """/api/static/img/agents/* でエージェントアバターを配信。"""
    filename = req.route_params.get("filename", "")
    return _serve_static(f"img/agents/{filename}", "image/png", cache_seconds=86400)


@app.route(route="llms.txt", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def llms_txt(req: func.HttpRequest) -> func.HttpResponse:
    """LLM 向けサイト要約（Markdown）。/api/llms.txt で配信。"""
    return _serve_static("llms.txt", "text/markdown; charset=utf-8")


@app.route(route="robots.txt", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def robots_txt(req: func.HttpRequest) -> func.HttpResponse:
    """AI クローラー向け robots ポリシー。/api/robots.txt で配信。"""
    return _serve_static("robots.txt", "text/plain; charset=utf-8")


@app.route(
    route="ai-plugin.json",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def ai_plugin(req: func.HttpRequest) -> func.HttpResponse:
    """OpenAI Plugin 互換マニフェスト。/api/ai-plugin.json で配信。"""
    return _serve_static(".well-known/ai-plugin.json", "application/json")


@app.route(route="openapi.json", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def openapi_spec(req: func.HttpRequest) -> func.HttpResponse:
    """OpenAPI 3.1 仕様。Agent が機械可読でエンドポイントを発見できる。"""
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "After-Hours Agents API",
            "version": "0.9.0",
            "description": (
                "シフト制で働く 8 体の AI エージェントによる SNS ヘルスチェック・自律振り返り API。"
                "Microsoft Agent Hackathon 2026 提出作品。"
            ),
        },
        "servers": [{"url": "https://func-aha-dev.azurewebsites.net"}],
        "paths": {
            "/api/demo/analyze": {
                "post": {
                    "summary": "SNS ヘルスチェック（認証不要・デモ用）",
                    "operationId": "analyzeDemo",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["tweet_text"],
                                    "properties": {
                                        "tweet_text": {"type": "string", "maxLength": 500},
                                        "tweet_id": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "澪による診断結果",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/RiskAnalysis"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/night/summary": {
                "get": {
                    "summary": "最新の夜間振り返りサマリーを取得",
                    "operationId": "getNightSummary",
                    "responses": {"200": {"description": "夜間ノクターンの集計結果"}},
                }
            },
        },
        "components": {
            "schemas": {
                "RiskAnalysis": {
                    "type": "object",
                    "properties": {
                        "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "risk_factors": {"type": "array", "items": {"type": "string"}},
                        "suggested_actions": {"type": "array", "items": {"type": "string"}},
                        "predicted_escalation_hours": {"type": "integer"},
                        "summary": {"type": "string"},
                    },
                }
            }
        },
    }
    return func.HttpResponse(
        json.dumps(spec, ensure_ascii=False, indent=2),
        mimetype="application/json",
        status_code=200,
    )


# ===== Demo エンドポイント レート制限 =====
# 暴走時のコスト爆発を防ぐため、in-memory + Cosmos DB 二段の制限を入れる。
# - IP 単位: 5 分に 5 回まで（突発的なクリックスパム対策）
# - グローバル: 1 日 200 回まで（コスト上限・gpt 系 API の概算 $5/日 以下に抑える）

import threading
import time as _time
from collections import defaultdict, deque

_rate_lock = threading.Lock()
_ip_buckets: dict[str, deque] = defaultdict(deque)  # ip -> [timestamp, ...]
_global_bucket: deque = deque()
_RL_IP_LIMIT = 5
_RL_IP_WINDOW = 300  # 秒
_RL_GLOBAL_LIMIT = 200
_RL_GLOBAL_WINDOW = 86400  # 24 時間


def _get_client_ip(req: func.HttpRequest) -> str:
    fwd = req.headers.get("X-Forwarded-For") or req.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return req.headers.get("X-Real-IP") or "unknown"


def _check_rate_limit(ip: str) -> tuple[bool, str | None, int]:
    """戻り値: (allowed, reason, retry_after_seconds)"""
    now = _time.time()
    with _rate_lock:
        # IP ごと
        ip_q = _ip_buckets[ip]
        while ip_q and now - ip_q[0] > _RL_IP_WINDOW:
            ip_q.popleft()
        if len(ip_q) >= _RL_IP_LIMIT:
            wait = int(_RL_IP_WINDOW - (now - ip_q[0])) + 1
            return False, "ip_limit", wait
        # グローバル
        while _global_bucket and now - _global_bucket[0] > _RL_GLOBAL_WINDOW:
            _global_bucket.popleft()
        if len(_global_bucket) >= _RL_GLOBAL_LIMIT:
            wait = int(_RL_GLOBAL_WINDOW - (now - _global_bucket[0])) + 1
            return False, "global_limit", wait
        ip_q.append(now)
        _global_bucket.append(now)
        return True, None, 0


@app.route(
    route="demo/analyze",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def demo_analyze(req: func.HttpRequest) -> func.HttpResponse:
    """デモ用 anonymous エンドポイント。

    レート制限:
      - IP ごと: 5 分 5 回まで
      - グローバル: 1 日 200 回まで
    投稿テキストは Cosmos に保存しない（プライバシー配慮）。
    """
    ip = _get_client_ip(req)
    allowed, reason, retry = _check_rate_limit(ip)
    if not allowed:
        msg = (
            "アクセス頻度の上限に達しました。少し時間をおいて再度お試しください。"
            if reason == "ip_limit"
            else "本日のデモ枠上限に達しました。明日以降に再度お試しください（コスト保護のため）。"
        )
        return func.HttpResponse(
            json.dumps({"error": "rate_limited", "reason": reason, "message": msg}),
            mimetype="application/json",
            status_code=429,
            headers={"Retry-After": str(retry)},
        )

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400,
        )

    tweet_text = (body.get("tweet_text") or "").strip()
    tweet_id = body.get("tweet_id") or "demo"
    if not tweet_text:
        return func.HttpResponse(
            json.dumps({"error": "tweet_text is required"}),
            mimetype="application/json",
            status_code=400,
        )
    if len(tweet_text) > 500:
        return func.HttpResponse(
            json.dumps({"error": "tweet_text exceeds 500 characters"}),
            mimetype="application/json",
            status_code=413,
        )

    from agents.mio_01.agent import analyze_tweet

    try:
        result = asyncio.run(analyze_tweet(tweet_text, tweet_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("demo_analyze failed: %s", exc)
        return func.HttpResponse(
            json.dumps({"error": "analysis failed", "detail": str(exc)}),
            mimetype="application/json",
            status_code=500,
        )

    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        mimetype="application/json",
        status_code=200,
        headers={"Cache-Control": "no-store"},
    )
