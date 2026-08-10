"""Exp05 Crypto Header Validator - Validates the entropy/zero-fill
structural fingerprint of the crypto_header and padding regions found by
manual hex analysis of the Thundeal TD98 Pro (MT5889) OTA package (see
config/firmware.yaml known_structures -> crypto_header, padding).

Unlike exp03/exp04 (which extract specific field values), this region
isn't a value to parse: 160 bytes of what's presumed to be an RSA
signature look like uniform random noise by design, and the remaining
bytes are documented as zero padding. There is nothing to "read" out of a
signature blob without the corresponding public key and knowledge of the
signing scheme -- what CAN be checked, cheaply and without any of that, is
whether the region's statistical *shape* still matches what was observed
on the real image: high entropy where a signature is expected, exact zero
fill where padding is expected. That shape match is itself useful
evidence: a mismatch would mean either a different firmware variant/format
than assumed, or (as a distant possibility) that this region was patched
by something OTHER than the same crypto tooling.

Reuses shannon_entropy() from mtklab.adapters.mstar_entropy (the same
entropy primitive exp01 is built on) rather than duplicating it.
"""

from mtklab.experiments import Experiment, ExperimentContext, ExperimentResult
from mtklab.core.evidence import Evidence, EvidenceType, ConfidenceLevel, Finding, FindingKind
from mtklab.adapters.mstar_entropy import shannon_entropy


def _min_entropy_for_random_sample(sample_size: int) -> float:
    """A safe lower-bound estimate of the Shannon entropy a genuinely
    random sample of `sample_size` bytes (256-symbol alphabet) should
    reach, used as the default high-entropy threshold.

    exp01's own high_entropy_threshold default (7.2) is calibrated for its
    4096-byte scan windows and does NOT hold for a much smaller sample: a
    small sample simply cannot get close to the theoretical 8.0 bits/byte
    maximum. Empirically, 160 genuinely random bytes measure ~6.7-6.9
    bits/byte (verified during development: 30/30 trials fell below 7.2),
    not 7.2+ -- using exp01's fixed threshold here would misclassify a
    real signature as suspiciously low-entropy on every run.

    Derived empirically across sample sizes 32..4096: random samples reach
    roughly 88-97% of log2(min(sample_size, 256)) (the theoretical max for
    an all-distinct-byte sample of that size); 0.80 is used here for a
    safety margin below the observed minimum of that range.
    """
    import math
    return 0.80 * math.log2(min(max(sample_size, 2), 256))


class Exp05CryptoHeaderValidator(Experiment):
    """Validates the entropy/zero-fill fingerprint of the crypto_header
    (likely RSA signature + zero pad) and the adjacent zero padding region."""

    experiment_id = "exp05_crypto_header_validator"
    display_name = "Crypto Header Validator"
    description = "Validates the entropy/zero-fill structural fingerprint of the crypto_header and padding regions"
    version = "1.0.0"
    requires = []
    parameters = {
        # Defaults sourced from manual hex-editor analysis of the real
        # Thundeal TD98 Pro (MT5889) firmware -- see
        # config/firmware.yaml known_structures[crypto_header, padding].
        # Offsets relative to ctx.firmware_path (the OTA .pkg), same
        # reasoning as exp03/exp04: this region is before the REE payload.
        "crypto_header_offset": 0x0,
        "crypto_header_signature_size": 160,
        "crypto_header_zero_padding_size": 96,
        # None (default) means: derive a size-appropriate minimum from
        # _min_entropy_for_random_sample(crypto_header_signature_size)
        # rather than reusing exp01's fixed 7.2 (which is calibrated for
        # 4096-byte windows and is too strict for a 160-byte sample -- see
        # _min_entropy_for_random_sample's docstring). Set explicitly to
        # override with a fixed value instead.
        "high_entropy_threshold": None,
        "padding_region_offset": 0x100,
        "padding_region_size": 512,
    }

    def run(self, ctx: ExperimentContext) -> ExperimentResult:
        # Deliberately ctx.firmware_path (the OTA package), not
        # ctx.ree_payload_path -- see module docstring / exp03 / exp04.
        fw_path = ctx.firmware_path
        if not fw_path.exists():
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="failed",
                summary=f"OTA package not found at {fw_path}",
                errors=[f"File not found: {fw_path}"],
            )

        crypto_offset = self.parameters.get("crypto_header_offset", 0x0)
        sig_size = self.parameters.get("crypto_header_signature_size", 160)
        zero_size = self.parameters.get("crypto_header_zero_padding_size", 96)
        threshold = self.parameters.get("high_entropy_threshold")
        if threshold is None:
            threshold = _min_entropy_for_random_sample(sig_size)
        padding_offset = self.parameters.get("padding_region_offset", 0x100)
        padding_size = self.parameters.get("padding_region_size", 512)

        needed = max(crypto_offset + sig_size + zero_size, padding_offset + padding_size)
        file_size = fw_path.stat().st_size
        if file_size < needed:
            return ExperimentResult(
                experiment_id=self.experiment_id,
                status="failed",
                summary=f"OTA package is {file_size:,} bytes, too small to contain the checked regions (need {needed:,})",
                errors=[f"File too small: {file_size} < {needed}"],
            )

        with fw_path.open("rb") as f:
            f.seek(crypto_offset)
            signature_bytes = f.read(sig_size)
            zero_pad_bytes = f.read(zero_size)
            f.seek(padding_offset)
            padding_bytes = f.read(padding_size)

        findings = []
        evidences = []

        # --- crypto_header: signature portion (expected high entropy) ---
        sig_entropy = shannon_entropy(signature_bytes)
        sig_high_entropy = sig_entropy >= threshold
        evidences.append(Evidence(
            experiment_id=self.experiment_id,
            evidence_type=EvidenceType.ENTROPY_BOUNDARY,
            confidence=ConfidenceLevel.PROBABLE if sig_high_entropy else ConfidenceLevel.CANDIDATE,
            description=(
                f"Signature region at 0x{crypto_offset:X} ({sig_size}B): entropy={sig_entropy:.4f} "
                f"({'>=' if sig_high_entropy else '<'} threshold {threshold})"
            ),
            data={"offset": crypto_offset, "size": sig_size, "entropy": sig_entropy, "threshold": threshold},
            source_offset=crypto_offset,
            source_size=sig_size,
            tags=["crypto_header", "entropy_check"],
        ))

        # --- crypto_header: zero-fill portion ---
        zero_pad_offset = crypto_offset + sig_size
        zero_pad_is_zero = zero_pad_bytes.count(0) == len(zero_pad_bytes)
        zero_pad_ratio = zero_pad_bytes.count(0) / len(zero_pad_bytes) if zero_pad_bytes else 1.0
        evidences.append(Evidence(
            experiment_id=self.experiment_id,
            evidence_type=EvidenceType.STRUCTURAL_PATTERN,
            confidence=ConfidenceLevel.PROBABLE if zero_pad_is_zero else ConfidenceLevel.CANDIDATE,
            description=(
                f"Zero-fill region at 0x{zero_pad_offset:X} ({zero_size}B): "
                f"{'fully zero' if zero_pad_is_zero else f'{zero_pad_ratio:.1%} zero bytes'}"
            ),
            data={"offset": zero_pad_offset, "size": zero_size, "zero_ratio": zero_pad_ratio},
            source_offset=zero_pad_offset,
            source_size=zero_size,
            tags=["crypto_header", "zero_fill_check"],
        ))

        crypto_confidence = (
            ConfidenceLevel.PROBABLE if (sig_high_entropy and zero_pad_is_zero) else ConfidenceLevel.CANDIDATE
        )
        findings.append(Finding(
            experiment_id=self.experiment_id,
            kind=FindingKind.HEADER,
            offset=crypto_offset,
            size=sig_size + zero_size,
            confidence=crypto_confidence,
            label="Crypto Header (signature + zero-fill)",
            description=(
                f"Crypto header at 0x{crypto_offset:X}: signature entropy={sig_entropy:.2f} "
                f"({'matches' if sig_high_entropy else 'does NOT match'} expected high-entropy signature), "
                f"zero-fill {'confirmed' if zero_pad_is_zero else 'NOT confirmed'}"
            ),
            metadata={
                "signature_entropy": sig_entropy,
                "signature_high_entropy": sig_high_entropy,
                "zero_pad_is_zero": zero_pad_is_zero,
                "zero_pad_ratio": zero_pad_ratio,
                "entropy_threshold": threshold,
            },
        ))

        # --- separate documented padding region (0x100, 512B, all-zero) ---
        padding_is_zero = padding_bytes.count(0) == len(padding_bytes)
        padding_zero_ratio = padding_bytes.count(0) / len(padding_bytes) if padding_bytes else 1.0
        evidences.append(Evidence(
            experiment_id=self.experiment_id,
            evidence_type=EvidenceType.STRUCTURAL_PATTERN,
            confidence=ConfidenceLevel.PROBABLE if padding_is_zero else ConfidenceLevel.CANDIDATE,
            description=(
                f"Padding region at 0x{padding_offset:X} ({padding_size}B): "
                f"{'fully zero' if padding_is_zero else f'{padding_zero_ratio:.1%} zero bytes'}"
            ),
            data={"offset": padding_offset, "size": padding_size, "zero_ratio": padding_zero_ratio},
            source_offset=padding_offset,
            source_size=padding_size,
            tags=["padding_region", "zero_fill_check"],
        ))
        findings.append(Finding(
            experiment_id=self.experiment_id,
            kind=FindingKind.REGION,
            offset=padding_offset,
            size=padding_size,
            confidence=ConfidenceLevel.PROBABLE if padding_is_zero else ConfidenceLevel.CANDIDATE,
            label="Zero Padding Region",
            description=(
                f"Padding region at 0x{padding_offset:X}: "
                f"{'fully zero (matches documented structure)' if padding_is_zero else f'only {padding_zero_ratio:.1%} zero bytes'}"
            ),
            metadata={"is_zero": padding_is_zero, "zero_ratio": padding_zero_ratio},
        ))

        all_match = sig_high_entropy and zero_pad_is_zero and padding_is_zero
        status = "success" if all_match else "partial"

        return ExperimentResult(
            experiment_id=self.experiment_id,
            status=status,
            summary=(
                f"crypto_header signature entropy={sig_entropy:.2f} "
                f"({'OK' if sig_high_entropy else 'below threshold'}), "
                f"zero-fill {'OK' if zero_pad_is_zero else 'FAILED'}, "
                f"padding region {'OK' if padding_is_zero else 'FAILED'}"
            ),
            findings=findings,
            evidences=evidences,
            metadata={
                "signature_entropy": sig_entropy,
                "signature_high_entropy": sig_high_entropy,
                "zero_pad_is_zero": zero_pad_is_zero,
                "padding_is_zero": padding_is_zero,
                "all_checks_passed": all_match,
            },
        )
