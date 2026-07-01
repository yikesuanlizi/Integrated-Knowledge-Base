from app.eval.retrieval_eval import score_golden_retrieval_cases


def test_score_golden_retrieval_cases_calculates_recall_and_mrr():
    report = score_golden_retrieval_cases(
        [
            {
                "question": "粗燃油滤清器拆卸步骤是什么",
                "expected_chunk_ids": ["chunk-a"],
                "intent": "procedure",
                "retrieved": [
                    {"chunk_id": "chunk-a", "source_type": "chunk"},
                    {"chunk_id": "chunk-b", "source_type": "chunk"},
                ],
            },
            {
                "question": "燃油系统有哪些 Wiki 卡片",
                "expected_card_ids": ["card-z"],
                "intent": "general_lookup",
                "retrieved": [
                    {"card_id": "card-a", "source_type": "wiki_card"},
                    {"card_id": "card-z", "source_type": "wiki_card"},
                ],
            },
            {
                "question": "不存在的问题",
                "expected_doc_ids": ["doc-missing"],
                "intent": "general_lookup",
                "retrieved": [{"chunk_id": "chunk-x", "doc_id": "doc-x", "source_type": "chunk"}],
            },
        ]
    )

    assert report["total_queries"] == 3
    assert report["recall_at_1"] == 0.3333
    assert report["recall_at_3"] == 0.6667
    assert report["recall_at_10"] == 0.6667
    assert report["mrr"] == 0.5
    assert report["missed_count"] == 1
    assert report["channel_contribution"] == {"chunk": 1, "wiki_card": 1}
    assert report["intent_breakdown"]["procedure"]["recall_at_10"] == 1.0
