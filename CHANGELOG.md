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

## 0.2.1 - 2026-08-23

### Security

- Template, enum, and reference-distribution weights are scaled once per
  declaration rather than reparsed in record-count-multiplied hot loops. Pack
  entity lexicon references are unique and bounded, and their surfaces are
  composed once per mint.
- Mint generation streams records and label sidecars into the private staging
  directory. It retains only reference identifiers, enforces per-file and
  aggregate output-byte budgets, and still commits atomically after the safe
  identifier invariant succeeds.
- Dataset verification streams JSONL, CSV, and label sidecars under line, file,
  aggregate-byte, record, and diagnostic-count budgets. Semantic claims are
  accumulated without retaining every parsed record.
- Validator identifier mode now requires an affirmative caller choice even when
  a recipe requires it. An omitted CLI or API policy is always `safe`; recipe
  binding and exact-policy reproduction remain enforced.

No generated record or sidecar bytes move for the same pack, recipe, seed,
format, and explicit policy. Manifests record the patch engine version.

## 0.2.0 - 2026-08-23

A security and conformance review of the three sector packs found one defect
repeated in seven places: a field parsed, validated against the schema, asserted
by a test, and then read by nothing. Every item below closes one of those. Two of
them move emitted bytes for a fixed seed, which this project calls a major
version event, so the version moves rather than the golden files quietly.

### Hardened against a hostile pack and a hostile dataset

Fourteen commits landed before this release was cut and are recorded here rather
than left to the git log, because each one changes what the engine refuses.

- **Resource budgets on everything a pack declares.** Strict YAML parsing, pack
  declarations, document templates, and numeric work factors all carry explicit
  bounds now, so a pack cannot make the loader do unbounded work. Templates are
  compiled once before any record is generated, and a nesting depth limit refuses
  a template that recurses past what the parser supports.
- **Sampler bounds are checked rather than assumed.** An unsupported bound is
  refused instead of producing a draw nobody can reason about.
- **Atomic staging writes are isolated**, and the pack digest streams its inputs
  from a confined set of paths rather than reading whatever it is pointed at.
- **Untrusted dataset file access is hardened.** `verify` reads a dataset through
  a reader that bounds what it will open, and the whole verification body sits
  behind a boundary that turns a hostile input into a report rather than a
  traceback.
- **Every claim in a manifest is re-derived rather than trusted.** Record counts,
  distributions, entity coverage, the achieved counts and `met` flags on coverage
  targets, and the fixed-contract text are all recomputed from the data and
  compared.
- **Safe output and annotation invariants are enforced at mint time**, including
  the label a field may carry for its generator, so a pack cannot declare a
  document field or an identifier field with a label that contradicts it.
- **Pack compatibility is enforced deterministically.** `requires_core` is checked
  against the running core on every load rather than only when a caller asks.
- **CI and release trust boundaries are sealed**, and the pack layer keeps its
  dependency boundaries.

### Fixed, and it changes what a verifier reports

- **`verify` reported zero checksum-valid identifiers in datasets where every
  identifier was checksum-valid.** The sweep ran only under the safe policy while
  the counter it fills was printed under both, in the rendered report and in the
  `--json` payload. A validator-policy dataset therefore reported
  `checksum_valid_identifiers: 0`, and a script gating on that number let through
  exactly the datasets it was written to stop. The sweep now runs under both
  policies. Under safe a hit is still a problem, because safe mode is the
  product's safety claim; under validator the count is the expected outcome and
  is recorded as a fact.

- **A declared coverage target was recorded and never checked.** Every manifest
  carried the target, the achieved count, and a `met` flag, and nothing read any
  of them, so an evaluation set could ship without a whole label and still verify
  clean. `verify` now fails on a missed target. A mint that overrode its record
  counts is exempt: `packcheck` mini-mints twenty-five records against targets in
  the hundreds, and a deliberately shrunken run is not a claim the recipe made.

- **The validator warning claimed more than the engines deliver.** It said the
  values belong to no real person, account, or institution. That holds for an
  IBAN, a PAN, and an email address, each of which sits in a range nobody can
  hold. A TCKN and a VKN have no such reserved range, so a checksum-valid one is
  indistinguishable from an issued number. The fixed text now says which is
  which.

### Fixed, and it moves emitted bytes

- **Template weights were ignored.** Every template entry carries a required
  `weight`, the schema validates it as a decimal string, and the renderer picked
  uniformly regardless. A set declared at 0.35, 0.25, 0.25, 0.15 emitted an even
  quarter each. Selection now uses the same weighted draw the enum generators
  use.

- **A pack could not contribute entity surfaces.** `{entity:ORG}` drew from the
  core's curated list and nothing else, so every pack in the family shared one
  twelve-name organization vocabulary, and an evaluation set built on it could be
  passed by memorizing them. `pack.yaml` gains an optional `entity_lexicons` map
  from label to the pack's own lexicons. The core list stays the floor: pack
  surfaces are appended, never substituted.

- **PERSON surfaces were a list of twelve full names.** The descriptor note
  already said they came from the same common Turkish name pool the structured
  fields draw from, so they are now composed from it: 60 given names against 50
  surnames, 3000 surfaces, in a fixed order so the draw stays a plain index. A
  label entry in the descriptor file may declare `compose` instead of `values`.

### Added

- **`{lex:name}` in the template grammar.** A draw from a named lexicon, emitted
  without a label, so a template can vary its ordinary words instead of repeating
  one carrier sentence. Domain vocabulary is not personal data and carries no
  span.

- **Two reachability rules on pack loading.** A lexicon nothing draws from, and a
  template set no field renders, are refused by name. Three sector packs shipped
  eight lexicons between them that reached no generator at all: source-noted,
  denylist-tested, guarded by their own tests, and absent from every byte those
  packs emit.

### Changed

- **A recipe that names an identifier policy now decides it.** The field was
  parsed into the `Recipe` dataclass and read nowhere, so a recipe pinned to
  `safe` minted checksum-valid identifiers the moment a caller passed
  `--identifier-policy validator`. Naming a different policy than the recipe
  names is refused. Naming the same one is allowed, because `reproduce` replays
  what a manifest recorded and cannot know which of the two decided it.
  `--identifier-policy` now defaults to unset rather than to `safe`.

### Removed

- **`doc_mix` and `emit_child_outside_window` from the recipe schema.**
  `doc_mix` restated what the record counts already fix, and nothing read it;
  `emit_child_outside_window` carried a schema description of behaviour no code
  implemented. The template-set existence check `doc_mix` provided is replaced by
  the stronger reachability rule above.

## 0.1.3 - 2026-08-22

### Fixed, and it changes every manifest

- **The pack digest covered files that cannot affect what a pack emits.** It
  enumerated the whole pack directory minus a short denylist, which meant it
  covered README files, the changelog, the test suite, the lockfile, the vendored
  engine wheel, compiled `__pycache__` output, and `PLAN.md`, a file the sector
  packs deliberately keep out of git.

  Three consequences, all observed rather than reasoned about. A clean clone and
  a working checkout of the same commit produced different digests. Running the
  suite under a different pytest version changed the digest through the `.pyc`
  files. Editing documentation changed the digest of a pack whose declarations
  had not moved. One pack produced three different digests for one set of
  declarations: `9548e8fd` in a working tree, `144b703a` from a clean clone, and
  `a9552d15` in an already published dataset.

  A digest behaving that way cannot do the job it exists for, which is to let
  somebody holding a dataset tell whether a pack they have is the pack it came
  from. It now covers `pack.yaml` and the `fields/`, `recipes/`, `templates/`,
  `lexicons/`, and `assets/` directories, by allowlist rather than denylist,
  because every failure above was something nobody thought to deny.

  Every manifest this engine writes now records a different `pack.digest` for the
  same declarations. No emitted data moves: the digest seeds nothing.

- **`reproduce` could not find the pack the engine itself ships**, so the
  quickstart's own output could not be reproduced by the command the README
  advertises as the check that makes a manifest mean something.

- **`reproduce` reported `differs outside the excluded provenance block`**, which
  was true and useless. It now names each field that differs with both values. A
  difference confined to the engine version is reported as what it is rather than
  as a mismatch, because the determinism claim covers a fixed engine version and
  a newer engine reproducing every byte is a stronger result than the claim, not
  a failure of it.

### Notes

Found by auditing the published product rather than the source tree: cloning the
packs, installing the engine from PyPI, and running the documented commands
against the released datasets.

## 0.1.2 - 2026-08-22

### Fixed

- The example pack shipped in the wheel and could not be reached. It is there so
  the quickstart works without cloning anything, which is the whole reason it is
  shipped, but `--pack packs/example` is a path that exists only in a checkout.
  Anyone who installed 0.1.1 from PyPI and followed the README walked into
  `pack: not-a-directory`. Found by installing the published package and running
  the README's own first command against it.

  `--pack example` now resolves to the packaged pack. A local path always wins,
  so this cannot shadow a real directory, and an unrecognized name is returned
  untouched so the loader still fails with the path the user typed rather than
  rescuing a typo into some other pack.

### Changed

- Both READMEs install by package name again and the quickstart uses
  `--pack example`. The claim that nothing was published was true until 0.1.1
  and is not any more.

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

Nothing was published at the time 0.1.0 was cut: no package registry carried it
and the name was still provisional. Both changed later the same day, in 0.1.1 and
in the trademark clearance recorded in TRADEMARKS.md. This note is left as it was
written rather than edited, because a changelog that quietly updates itself stops
being a record.
