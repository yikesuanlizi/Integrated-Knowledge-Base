from __future__ import annotations


def test_clean_for_search_strips_page_numbers_and_headers():
    from app.ingest.cleaning import clean_for_search

    raw = """
AMM 32-41-00 Page 201
Landing gear inspection procedure
Page 1 of 200
"""

    cleaned = clean_for_search(raw)

    assert "AMM 32-41-00 Page 201" not in cleaned
    assert "Page 1 of 200" not in cleaned
    assert "Landing gear inspection procedure" in cleaned


def test_clean_for_search_fixes_hyphenation_breaks():
    from app.ingest.cleaning import clean_for_search

    raw = "Perform mainte-\nnance check before operation."

    cleaned = clean_for_search(raw)

    assert "mainte-\nnance" not in cleaned
    assert "maintenance check" in cleaned


def test_clean_for_embedding_strips_ocr_garbage_and_table_fragments():
    from app.ingest.cleaning import clean_for_embedding

    raw = """
ATA 32 landing gear servicing
!@##$%^&*(
| | | |
"""

    cleaned = clean_for_embedding(raw)

    assert "ATA 32 landing gear servicing" in cleaned
    assert "!@##$%^&*(" not in cleaned
    assert "| | | |" not in cleaned


def test_clean_for_embedding_deduplicates_boilerplate():
    from app.ingest.cleaning import clean_for_embedding

    raw = """
WARNING: DO NOT APPLY HYDRAULIC POWER.
WARNING: DO NOT APPLY HYDRAULIC POWER.
Removal procedure starts here.
"""

    cleaned = clean_for_embedding(raw)

    assert cleaned.count("WARNING: DO NOT APPLY HYDRAULIC POWER.") == 1
    assert "Removal procedure starts here." in cleaned


def test_clean_for_embedding_merges_sentence_breaks():
    from app.ingest.cleaning import clean_for_embedding

    raw = "Remove the wheel assembly\nfrom the axle and inspect bolts."

    cleaned = clean_for_embedding(raw)

    assert "Remove the wheel assembly from the axle and inspect bolts." in cleaned

