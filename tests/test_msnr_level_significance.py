from pipslayer.strategies.msnr.level_significance import build_level_catalogue  # type: ignore[import-not-found]


def sample_report():
    return {
        "dataset_id": "test-dataset",
        "timeframe": "H4",
        "method": "test-method",
        "structure_count": 2,
        "structures": [
            {
                "structure_id": "av-test-a",
                "kind": "A",
                "price": 4300.0,
                "anchor_timestamp": "2026-05-01T08:00:00+00:00",
                "formed_at": "2026-05-01T12:00:00+00:00",
                "recognised_at": "2026-05-01T16:00:00+00:00",
                "gap_context": {"gap_before_candidate": True},
            },
            {
                "structure_id": "av-test-v",
                "kind": "V",
                "price": 4200.0,
                "anchor_timestamp": "2026-05-02T08:00:00+00:00",
                "formed_at": "2026-05-02T12:00:00+00:00",
                "recognised_at": "2026-05-02T16:00:00+00:00",
                "gap_context": {"gap_after_candidate": False},
            },
        ],
    }


def test_catalogue_preserves_every_source_structure():
    catalogue = build_level_catalogue(sample_report(), symbol="XAUUSD")

    assert catalogue["source_structure_count"] == 2
    assert catalogue["level_count"] == 2
    assert [level["kind"] for level in catalogue["levels"]] == ["A", "V"]


def test_catalogue_preserves_identity_price_and_gap_context():
    catalogue = build_level_catalogue(sample_report(), symbol="XAUUSD")

    first = catalogue["levels"][0]

    assert first["source_structure_ids"] == ["av-test-a"]
    assert first["reference_price"] == 4300.0
    assert first["gap_context"]["gap_before_candidate"] is True


def test_new_levels_start_unclassified():
    catalogue = build_level_catalogue(sample_report(), symbol="XAUUSD")

    for level in catalogue["levels"]:
        assert level["structural_scale"] == "unclassified"
        assert level["importance_tier"] == "unclassified"
        assert level["evidence"] == []
        assert level["assessment_status"] == "catalogued"


def test_duplicate_structure_ids_are_rejected():
    report = sample_report()
    report["structures"][1]["structure_id"] = "av-test-a"

    try:
        build_level_catalogue(report, symbol="XAUUSD")
    except ValueError as exc:
        assert "Duplicate structure ID" in str(exc)
    else:
        raise AssertionError("Duplicate structure ID was accepted")
