from pathlib import Path

from medical_rag.config import Settings
from medical_rag.terminology.concept_linker import (
    ONTOLOGICAL_NOTICE,
    ConceptLinker,
    _TR_CLINICAL_RULES,
)
from medical_rag.terminology.snomed_importer import SnomedImporter


def test_snomed_ips_snapshot_import_counts_and_headache_graph() -> None:
    settings = Settings()
    importer = SnomedImporter(Path(":memory:"))
    counts = importer.ensure_imported(settings.snomed_package_dir)

    assert counts.active_concepts == 19697
    assert counts.active_descriptions == 60114
    assert counts.active_relationships == 66017
    assert counts.ips_refset_members == 12899
    assert counts.distinct_relationship_types == 70

    linker = ConceptLinker(importer.connection)

    # Every curated Turkish rule must point to a real active SNOMED concept in the IPS package
    for rule in _TR_CLINICAL_RULES:
        verified = linker.get_concept(rule.concept_id)
        assert verified is not None, f"Eksik SNOMED concept_id: {rule.concept_id}"

    # Verify Turkish headache query -> 25064002 Headache (finding)
    tr_hits = linker.link_text("Başım ağrıyor, son uyku ve kalp kayıtlarımda ne var?")
    assert len(tr_hits) >= 1
    headache = tr_hits[0]
    assert headache.concept_id == "25064002"
    assert headache.preferred_term == "Headache"
    assert headache.fsn == "Headache (finding)"
    assert headache.in_ips_refset is True
    assert headache.ontological_notice == ONTOLOGICAL_NOTICE
    assert "sleep" in headache.cco_families and "cardio" in headache.cco_families

    outgoing = [
        (edge.type_id, edge.type_label, edge.target_concept_id, edge.target_preferred_term)
        for edge in headache.relationships
        if edge.direction == "outgoing"
    ]
    assert ("116680003", "Is a", "22253000", "Pain") in outgoing
    assert ("116680003", "Is a", "406122000", "Head finding") in outgoing
    assert ("363698007", "Finding site", "69536005", "Head structure") in outgoing

    # Verify English synonym lookup ("Cephalalgia" -> 25064002)
    en_hits = linker.link_text("Patient reports cephalalgia")
    assert any(item.concept_id == "25064002" for item in en_hits)

    importer.close()


def test_snomed_importer_ignores_inactive_rows(tmp_path: Path) -> None:
    term_dir = tmp_path / "Snapshot" / "Terminology"
    lang_dir = tmp_path / "Snapshot" / "Refset" / "Language"
    content_dir = tmp_path / "Snapshot" / "Refset" / "Content"
    term_dir.mkdir(parents=True)
    lang_dir.mkdir(parents=True)
    content_dir.mkdir(parents=True)

    (term_dir / "sct2_Concept_IPSSnapshot_TEST.txt").write_text(
        "id\teffectiveTime\tactive\tmoduleId\tdefinitionStatusId\n"
        "116680003\t20240701\t1\t999991001000101\t900000000000074008\n"
        "25064002\t20240701\t1\t999991001000101\t900000000000074008\n"
        "22253000\t20240701\t1\t999991001000101\t900000000000074008\n"
        "99999999\t20240701\t0\t999991001000101\t900000000000074008\n",
        encoding="utf-8",
    )
    (term_dir / "sct2_Description_IPSSnapshot-en_TEST.txt").write_text(
        "id\teffectiveTime\tactive\tmoduleId\tconceptId\tlanguageCode\ttypeId\tterm\tcaseSignificanceId\n"
        "1\t20240701\t1\t999991001000101\t116680003\ten\t900000000000003001\tIs a (attribute)\t900000000000448009\n"
        "2\t20240701\t1\t999991001000101\t25064002\ten\t900000000000003001\tHeadache (finding)\t900000000000448009\n"
        "3\t20240701\t1\t999991001000101\t25064002\ten\t900000000000013009\tHeadache\t900000000000448009\n"
        "4\t20240701\t0\t999991001000101\t25064002\ten\t900000000000013009\tObsolete headache term\t900000000000448009\n"
        "5\t20240701\t1\t999991001000101\t22253000\ten\t900000000000003001\tPain (finding)\t900000000000448009\n"
        "6\t20240701\t1\t999991001000101\t99999999\ten\t900000000000003001\tInactive concept (finding)\t900000000000448009\n",
        encoding="utf-8",
    )
    (term_dir / "sct2_Relationship_IPSSnapshot_TEST.txt").write_text(
        "id\teffectiveTime\tactive\tmoduleId\tsourceId\tdestinationId\trelationshipGroup\ttypeId\tcharacteristicTypeId\tmodifierId\n"
        "10\t20240701\t1\t999991001000101\t25064002\t22253000\t0\t116680003\t900000000000011006\t900000000000451002\n"
        "11\t20240701\t0\t999991001000101\t25064002\t22253000\t0\t116680003\t900000000000011006\t900000000000451002\n",
        encoding="utf-8",
    )
    (lang_dir / "der2_cRefset_IPSLanguageSnapshot-en_TEST.txt").write_text(
        "id\teffectiveTime\tactive\tmoduleId\trefsetId\treferencedComponentId\tacceptabilityId\n"
        "20\t20240701\t1\t999991001000101\t900000000000509007\t3\t900000000000548007\n",
        encoding="utf-8",
    )
    (content_dir / "der2_Refset_IPSSimpleSnapshot_TEST.txt").write_text(
        "id\teffectiveTime\tactive\tmoduleId\trefsetId\treferencedComponentId\n"
        "30\t20240701\t1\t999991001000101\t816080008\t25064002\n"
        "31\t20240701\t0\t999991001000101\t816080008\t22253000\n",
        encoding="utf-8",
    )

    importer = SnomedImporter(Path(":memory:"))
    counts = importer.import_snapshot(tmp_path)
    assert counts.active_concepts == 3
    assert counts.active_descriptions == 4
    assert counts.active_relationships == 1
    assert counts.ips_refset_members == 1

    linker = ConceptLinker(importer.connection)
    assert linker.get_concept("99999999") is None
    assert linker.link_text("Obsolete headache term") == [
        linker.get_concept("25064002", matched_phrase="headache", match_source="en_exact_description")
    ] or all("Obsolete" not in s for c in linker.link_text("headache") for s in c.synonyms)
    importer.close()
