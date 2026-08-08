"""Unit tests for Evidence and Finding domain models."""

import unittest
from mtklab.core.evidence import (
    Evidence,
    EvidenceType,
    ConfidenceLevel,
    Finding,
    FindingKind,
    generate_logical_id,
)


class TestFindingSerialization(unittest.TestCase):
    """Test Finding dataclass serialization and deserialization."""

    def test_finding_auto_generates_logical_id_when_omitted(self):
        """Since MTKLAB-002, a Finding constructed without logical_id gets a
        canonical one auto-generated from experiment_id/kind/offset/size
        (DOMAIN_API.md 3.1: Finding auto-population via generate_logical_id).
        This supersedes the pre-MTKLAB-002 expectation that omitting
        logical_id left it None (see MTKLAB-002.md section 6)."""
        finding = Finding(
            experiment_id="exp01",
            kind=FindingKind.REGION,
            offset=1024,
            size=2048,
            confidence=ConfidenceLevel.CANDIDATE,
            label="Header",
            description="Test region finding",
        )
        expected = generate_logical_id("exp01", "region", 1024, 2048)
        self.assertEqual(finding.logical_id, expected)
        self.assertEqual(finding.logical_id, "exp01:region:0x00000400-0x00000c00")

        d = finding.to_dict()
        self.assertEqual(d["logical_id"], expected)

        reconstructed = Finding.from_dict(d)
        self.assertEqual(reconstructed.finding_id, finding.finding_id)
        self.assertEqual(reconstructed.experiment_id, "exp01")
        self.assertEqual(reconstructed.kind, FindingKind.REGION)
        self.assertEqual(reconstructed.offset, 1024)
        self.assertEqual(reconstructed.size, 2048)
        self.assertEqual(reconstructed.confidence, ConfidenceLevel.CANDIDATE)
        self.assertEqual(reconstructed.label, "Header")
        self.assertEqual(reconstructed.description, "Test region finding")
        self.assertEqual(reconstructed.logical_id, expected)

    def test_finding_auto_generates_global_logical_id_without_offset_or_size(self):
        """A Finding with no meaningful offset/size (e.g. size=None) falls
        back to the ':global' suffix rather than a fabricated range."""
        finding = Finding(
            experiment_id="exp01",
            kind=FindingKind.UNKNOWN,
            offset=0,
            size=None,
            confidence=ConfidenceLevel.CANDIDATE,
            description="No concrete region",
        )
        self.assertEqual(finding.logical_id, "exp01:unknown:global")

    def test_finding_to_dict_and_from_dict_with_logical_id(self):
        logical_id = "exp01:region:0x00000400-0x00000c00"
        finding = Finding(
            experiment_id="exp01",
            kind=FindingKind.REGION,
            offset=1024,
            size=2048,
            confidence=ConfidenceLevel.PROBABLE,
            label="Boot Header",
            description="Test region with logical id",
            logical_id=logical_id,
        )
        self.assertEqual(finding.logical_id, logical_id)

        d = finding.to_dict()
        self.assertEqual(d["logical_id"], logical_id)

        reconstructed = Finding.from_dict(d)
        self.assertEqual(reconstructed.logical_id, logical_id)
        self.assertEqual(reconstructed.finding_id, finding.finding_id)

    def test_finding_from_dict_legacy_without_logical_id_key(self):
        d = {
            "finding_id": "test-uuid-1234",
            "experiment_id": "exp01",
            "kind": "region",
            "offset": 0,
            "size": 512,
            "confidence": "CANDIDATE",
            "label": "Legacy",
            "description": "Legacy finding dict",
            "evidence_ids": [],
            "metadata": {},
            "versions": [],
        }
        reconstructed = Finding.from_dict(d)
        self.assertIsNone(reconstructed.logical_id)
        self.assertEqual(reconstructed.finding_id, "test-uuid-1234")


class TestGenerateLogicalId(unittest.TestCase):
    """Unit tests for the standalone generate_logical_id() helper (MTKLAB-002)."""

    def test_valid_offset_and_size(self):
        result = generate_logical_id("exp01_entropy_landscape", "region", 0, 0x8000)
        self.assertEqual(result, "exp01_entropy_landscape:region:0x00000000-0x00008000")

    def test_zero_padding_format(self):
        result = generate_logical_id("exp01", "header", 1024, 2048)
        self.assertEqual(result, "exp01:header:0x00000400-0x00000c00")

    def test_offset_none_falls_back_to_global(self):
        result = generate_logical_id("exp01", "region", None, 0x8000)
        self.assertEqual(result, "exp01:region:global")

    def test_size_none_falls_back_to_global(self):
        result = generate_logical_id("exp01", "region", 0, None)
        self.assertEqual(result, "exp01:region:global")

    def test_both_none_falls_back_to_global(self):
        result = generate_logical_id("exp01", "region", None, None)
        self.assertEqual(result, "exp01:region:global")

    def test_large_offset_beyond_32_bit(self):
        offset = 0x1_0000_0000  # > 32-bit
        result = generate_logical_id("exp01", "partition", offset, 0x1000)
        self.assertEqual(result, "exp01:partition:0x100000000-0x100001000")

    def test_hex_digits_are_lowercase(self):
        result = generate_logical_id("EXP01", "REGION", 0xAB, 0x10)
        # experiment_id/kind pass through as given; hex digits are lowercase.
        self.assertEqual(result, "EXP01:REGION:0x000000ab-0x000000bb")

    def test_zero_size_region(self):
        result = generate_logical_id("exp01", "boundary", 0x100, 0)
        self.assertEqual(result, "exp01:boundary:0x00000100-0x00000100")


class TestComputeContentHash(unittest.TestCase):
    """Unit tests for Evidence.compute_content_hash() (MTKLAB-005 / ADR-002)."""

    def _make(self, **overrides):
        kwargs = dict(
            experiment_id="exp01",
            evidence_type=EvidenceType.SIGNATURE_MATCH,
            confidence=ConfidenceLevel.CANDIDATE,
            description="test",
            data={"a": 1, "b": 2},
            source_offset=0x100,
            source_size=0x10,
        )
        kwargs.update(overrides)
        return Evidence(**kwargs)

    def test_identical_payloads_produce_identical_hash(self):
        e1 = self._make()
        e2 = self._make()
        self.assertEqual(e1.compute_content_hash(), e2.compute_content_hash())

    def test_hash_is_64_char_lowercase_hex(self):
        h = self._make().compute_content_hash()
        self.assertEqual(len(h), 64)
        self.assertEqual(h, h.lower())
        int(h, 16)  # raises ValueError if not valid hex

    def test_modified_field_produces_different_hash(self):
        base = self._make().compute_content_hash()
        self.assertNotEqual(base, self._make(source_offset=0x200).compute_content_hash())
        self.assertNotEqual(base, self._make(source_size=0x20).compute_content_hash())
        self.assertNotEqual(base, self._make(experiment_id="exp02").compute_content_hash())
        self.assertNotEqual(
            base, self._make(evidence_type=EvidenceType.CRC_VALIDATION).compute_content_hash()
        )
        self.assertNotEqual(base, self._make(data={"a": 1, "b": 3}).compute_content_hash())

    def test_dict_key_order_does_not_alter_hash(self):
        e1 = self._make(data={"a": 1, "b": 2, "c": 3})
        e2 = self._make(data={"c": 3, "a": 1, "b": 2})
        self.assertEqual(e1.compute_content_hash(), e2.compute_content_hash())

    def test_description_and_tags_and_confidence_do_not_affect_hash(self):
        """Only experiment_id, evidence_type, source_offset, source_size,
        and data are hash ingredients per the spec (section 4) -- these
        fields are deliberately excluded."""
        e1 = self._make(description="first description", confidence=ConfidenceLevel.CANDIDATE)
        e2 = self._make(description="a totally different description", confidence=ConfidenceLevel.VERIFIED)
        e1.tags = ["x"]
        e2.tags = ["y", "z"]
        self.assertEqual(e1.compute_content_hash(), e2.compute_content_hash())

    def test_none_source_offset_and_size_handled(self):
        h = self._make(source_offset=None, source_size=None).compute_content_hash()
        self.assertEqual(len(h), 64)
        # Distinguishable from a real offset of 0.
        h_zero = self._make(source_offset=0, source_size=0).compute_content_hash()
        self.assertNotEqual(h, h_zero)

    def test_hash_stable_across_recomputation(self):
        """Same object, computed twice, must be identical (determinism /
        stability -- ticket's own review checklist item)."""
        e = self._make()
        self.assertEqual(e.compute_content_hash(), e.compute_content_hash())


class TestEvidenceAutoContentAddressing(unittest.TestCase):
    """Evidence.__post_init__ auto-population (MTKLAB-005)."""

    def test_evidence_id_auto_populated_when_omitted(self):
        ev = Evidence(
            experiment_id="exp01",
            evidence_type=EvidenceType.SIGNATURE_MATCH,
            confidence=ConfidenceLevel.CANDIDATE,
            data={"x": 1},
            source_offset=0,
            source_size=16,
        )
        self.assertIsNotNone(ev.evidence_id)
        self.assertEqual(ev.evidence_id, ev.compute_content_hash())

    def test_explicit_evidence_id_is_preserved(self):
        """Backward compatibility requirement (section 6): an explicitly
        provided evidence_id -- including a legacy UUID-format string -- is
        never overwritten."""
        ev = Evidence(
            evidence_id="legacy-uuid-1234-not-a-hash",
            experiment_id="exp01",
            evidence_type=EvidenceType.SIGNATURE_MATCH,
        )
        self.assertEqual(ev.evidence_id, "legacy-uuid-1234-not-a-hash")

    def test_two_identical_evidence_objects_get_the_same_id(self):
        """The point of content-addressing: submitting the same evidence
        twice (e.g. across two runs) yields the same evidence_id, which is
        what lets storage-layer INSERT OR IGNORE (MTKLAB-006) deduplicate."""
        kwargs = dict(
            experiment_id="exp01",
            evidence_type=EvidenceType.ENTROPY_BOUNDARY,
            confidence=ConfidenceLevel.PROBABLE,
            data={"k": "v"},
            source_offset=0x1000,
            source_size=0x100,
        )
        ev1 = Evidence(**kwargs)
        ev2 = Evidence(**kwargs)
        self.assertEqual(ev1.evidence_id, ev2.evidence_id)

    def test_from_dict_with_explicit_id_round_trips_unchanged(self):
        ev = Evidence(experiment_id="exp01", evidence_type=EvidenceType.SIGNATURE_MATCH)
        d = ev.to_dict()
        reconstructed = Evidence.from_dict(d)
        self.assertEqual(reconstructed.evidence_id, ev.evidence_id)


if __name__ == "__main__":
    unittest.main()
