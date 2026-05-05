"""shared.vector_search のユニットテスト"""
from __future__ import annotations

import json


def test_keyword_similarity_basic(tmp_path, monkeypatch):
    """キーワードフォールバックで類似事例が返ること。"""
    from shared import vector_search as vs

    monkeypatch.setattr(vs, "_seed_cache", None)
    monkeypatch.setattr(
        vs,
        "_SEED_PATH",
        tmp_path / "seed.json",
    )
    seed = [
        {
            "case_id": "case-001",
            "title": "謝罪事例",
            "keywords": ["謝罪", "リコール"],
            "outcome": "成功",
            "lessons_learned": "速やかな謝罪が重要",
            "applicable_actions": ["謝罪文発表"],
        },
        {
            "case_id": "case-002",
            "title": "無関係事例",
            "keywords": ["海外展開", "価格"],
            "outcome": "中立",
            "lessons_learned": "情報開示が重要",
            "applicable_actions": ["説明文発表"],
        },
    ]
    (tmp_path / "seed.json").write_text(json.dumps(seed), encoding="utf-8")

    results = vs.search_similar_cases("謝罪が必要なリコール事案", top_k=2)

    assert len(results) >= 1
    assert results[0]["case_id"] == "case-001"
    assert "similarity_score" in results[0]
    assert 0.0 <= results[0]["similarity_score"] <= 1.0


def test_search_returns_empty_on_no_match(tmp_path, monkeypatch):
    """マッチなしの場合は空リストを返すこと。"""
    from shared import vector_search as vs

    monkeypatch.setattr(vs, "_seed_cache", None)
    monkeypatch.setattr(vs, "_SEED_PATH", tmp_path / "seed.json")
    (tmp_path / "seed.json").write_text(
        json.dumps([
            {
                "case_id": "case-001",
                "title": "謝罪事例",
                "keywords": ["謝罪", "リコール"],
                "outcome": "成功",
                "lessons_learned": "速やかな謝罪が重要",
                "applicable_actions": [],
            }
        ]),
        encoding="utf-8",
    )

    results = vs.search_similar_cases("全く関係のない内容 xyz abc", top_k=3)
    assert results == []


def test_normalize_handles_all_zero():
    """全スコア 0 でも ZeroDivisionError が発生しないこと。"""
    from shared.vector_search import _normalize

    assert _normalize([0.0, 0.0]) == [0.0, 0.0]


def test_search_similar_cases_uses_real_seed():
    """実際の seed ファイルが存在し、マッチする結果を返すこと。"""
    from shared.vector_search import search_similar_cases

    results = search_similar_cases("謝罪 リコール 健康被害", top_k=3)
    assert isinstance(results, list)
    assert results, "seed データが読み込めていないか、マッチがゼロです"
    assert "case_id" in results[0]
    assert "title" in results[0]
    assert "similarity_score" in results[0]
    assert 0.0 <= results[0]["similarity_score"] <= 1.0
