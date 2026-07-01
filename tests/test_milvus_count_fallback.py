from __future__ import annotations


def test_milvus_count_uses_query_result_length(monkeypatch):
    from app.retrieval import milvus_repo

    class FakeClient:
        def has_collection(self, name):
            return True

        def query(self, collection_name, filter, output_fields, limit):
            return [{"chunk_id": "a"}, {"chunk_id": "b"}]

    monkeypatch.setattr(milvus_repo, "get_milvus_client", lambda: FakeClient())

    repo = milvus_repo.MilvusRepository()

    assert repo.count() == 2
