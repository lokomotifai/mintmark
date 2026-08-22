# Changelog

All notable changes to this project are documented here. The format follows
[keep a changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

The public surface under semantic versioning is: the command-line grammar, the
exit codes, every `--json` payload, the library's exported functions and their
returned dataclasses, the pack schema, the manifest schema, and the byte-level
output for a fixed set of inputs. A change that alters emitted bytes for a fixed
seed is a major version event even when no signature changed, because it breaks
the reproducibility of every published manifest.

## Unreleased

### Added

- Deterministic generation engine: SplitMix64 over 64-bit modular arithmetic,
  per-site stream derivation, unbiased bounded and weighted draws, and
  continuous distributions sampled from committed fixed-point inverse-CDF tables
  so that no transcendental function runs in the mint path.
- Six identifier engines, each with a `safe` default that emits provably
  checksum-invalid values and an opt-in `validator` mode that is watermarked in
  the manifest.
- A closed eighteen-label taxonomy pinned by digest, span recording that
  survives whitespace normalization, and a label sidecar format that binds spans
  to the exact text they index.
- Strict, fail-closed pack loading: duplicate keys, anchors, aliases, merge
  keys, multi-document files, non-mapping roots, tab indentation, and unknown
  fields are each rejected by name.
- Canonical JSONL and CSV emission with no float in emitted data, and atomic
  output so an interrupted mint leaves no directory that looks like a dataset.
- A provenance manifest with checksums, `verify` that recomputes every claim it
  makes, and `reproduce` that re-mints from the manifest and compares bytes.
- A command-line surface of seven verbs with a five-value exit-code contract and
  stable `--json` payloads, plus a two-function library API.
- An example fixture pack, shipped in both the wheel and the sdist, used by the
  quickstart and the test suite.
- A real-institution denylist built from a verified public registry, scanned in
  required CI over lexicons, templates, and golden outputs.
- English and Turkish READMEs, kept in step by a test that compares their
  structure and checks the quickstart's promised output against what `verify`
  actually prints.

### Verified rather than assumed

The VKN check-digit algorithm, against two independent open implementations
cross-checked over 200 000 inputs. The unassigned status of IBAN bank code
99999, against the TCMB participant list. Turkey's permanent UTC+3 status,
against the IANA time zone database. The institution denylist, against the same
TCMB list. Each record, with its source and retrieval date, is in
`docs/normative-verification.md`.

### Notes

No release has been published. Nothing exists on any package registry, and
nothing in this file should be read as a claim that an installable artifact is
available. The name Mintmark is provisional pending trademark screening.
