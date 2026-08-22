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

## 0.1.1 - 2026-08-22

### Added

- Publication to PyPI, over trusted publishing. The release workflow was written
  and left disabled so its mechanics could be reviewed before they ever ran; this
  enables it. No long-lived token is stored in this repository and none is passed
  to a step, because PyPI verifies the workflow identity directly.

  Three gates stand between a tag and a published release, and none of them is a
  reviewer's attention. The tag must agree with the version in `pyproject.toml`
  and with the version the package reports. The full gate runs first and
  publication depends on it. The `pypi` environment requires the owner's approval
  and admits only `v*` tags, so a push to main cannot reach it.

### Notes

The package is unchanged from 0.1.0. This version exists because publication is a
repository change that needs a tag to carry it, and moving the 0.1.0 tag would
have broken the immutability that repository's own tag ruleset enforces.

A version already on PyPI cannot be replaced, and deleting a release does not
free its number. The workflow refuses on a version mismatch rather than resolving
one.

## 0.1.0 - 2026-08-22

### Changed, and it moved emitted bytes

- The manifest gained a `license` block and its schema version went to 2. A
  dataset leaves this project as a directory of files, and before this there was
  nothing in that directory saying under what terms it could be used. An
  attribution requirement a consumer cannot find in the artifact is not a
  requirement. The block carries the code license, the dataset license the pack
  declared, and a ready credit line; `verify` prints all three, and stripping the
  block fails verification like any other tampering.
- `pack.yaml` requires `dataset_license`, from a closed set. The engine writes
  this into every manifest it produces, and a free-text field would put a typo,
  or terms nobody vetted, onto a published artifact. Declaring it changes the
  pack digest, which changes emitted bytes for a fixed seed, which is why every
  pack in the family took a version bump alongside it.

- The special-category descriptor lexicons moved into a curated YAML file and
  grew to 90 entries. Expanding a lexicon changes the draw for every subsequent
  index, so emitted bytes moved for a fixed seed. **Under this project's own rule
  that is a major version event.** It is harmless only because nothing has been
  published: there is no manifest this breaks. The reason is recorded in
  `tests/golden/demo-run/DIGESTS.json` beside the regenerated goldens.
- `special_rate` now governs what it claimed to govern. A recipe declared it and
  nothing read it, so template authors fixed the density with literal
  probabilities and the recipe field was decoration. Templates now write
  `[?special: ...]` and the rate comes from the recipe.

### Added

- Turkish mirrors of every community document: contributing, conduct,
  governance, security, and support, each linked from its original and held in
  step by a test. The audience for this project reads Turkish, and a README
  mirror alone left a contributor reading the project's own rules in a second
  language. The conduct mirror records that it is our own rendering rather than
  the official one, because the Contributor Covenant publishes Turkish at 2.0
  while this repository adapts 2.1.
- `docs/kvkk.md` and its Turkish mirror: what this project produces and what it
  does not claim under law 6698, with a table mapping the taxonomy's
  special-category labels to the categories the law enumerates, and naming the
  three that no label covers.
- `LICENSE-DATASETS.md`, `CITATION.cff`, issue and pull request templates,
  `CODEOWNERS`, and grouped monthly dependency updates.

- The `derived:flag_unless` rule, which turns a sentinel enum value into a
  boolean so a row can carry both which anomaly it is and whether it is one,
  without two independent draws that can disagree.
- An optional `age_years: [low, high]` parameter on `datetime_window`, which
  draws from the span that would give a person that age at the start of the
  recipe window. Without it a birth date is drawn from the recipe window, so
  every person in a dataset describing one year was also born in that year. The
  field is a valid date, the label is right, the span aligns and the manifest
  verifies, so nothing in the suite caught it; it is only wrong to a reader. The
  parameter is optional and a field that omits it behaves exactly as before, so
  no existing declaration had to move. Declaring it on a field whose generator
  cannot read it is rejected by name at pack load, because a parameter nothing
  reads is worse than one that fails loudly.

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
