<p align="center">
  <img src="assets/brand/mintmark-logo.svg" width="112" height="112" alt="Mintmark">
</p>

<h1 align="center">Mintmark</h1>

<p align="center"><strong>Turkish-first synthetic datasets that carry the mark of where they were struck.</strong></p>

<p align="center">
  Declare what to mint, hand it a seed, and get labeled data back with a manifest<br>
  that lets anyone else re-derive the same bytes and check them against you.
</p>

<p align="center">
  <a href="https://github.com/lokomotifai/mintmark/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/lokomotifai/mintmark/ci.yml?branch=main&amp;style=flat-square&amp;label=CI"></a>
  <img alt="983 tests" src="https://img.shields.io/badge/tests-983-3C873A?style=flat-square">
  <img alt="18 invariants, each with a named test" src="https://img.shields.io/badge/invariants-18%20tested-3C873A?style=flat-square">
  <a href="https://github.com/lokomotifai/mintmark/releases/tag/v0.3.3"><img alt="Release v0.3.3" src="https://img.shields.io/badge/release-v0.3.3-3C873A?style=flat-square"></a>
  <a href="https://pypi.org/project/mintmark/"><img alt="On PyPI" src="https://img.shields.io/pypi/v/mintmark?style=flat-square&amp;label=PyPI&amp;color=3C873A"></a>
  <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/license-Apache--2.0-3B3F46?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square"></a>
  <img alt="Two runtime dependencies" src="https://img.shields.io/badge/runtime%20deps-2-17191F?style=flat-square">
  <img alt="No model in the generation path" src="https://img.shields.io/badge/models-none-D11F26?style=flat-square">
  <img alt="No network at mint time" src="https://img.shields.io/badge/network-none-D11F26?style=flat-square">
  <a href="docs/taxonomy.md"><img alt="18 labels in a closed taxonomy" src="https://img.shields.io/badge/taxonomy-18%20labels-17191F?style=flat-square"></a>
  <a href="README.tr.md"><img alt="Türkçe" src="https://img.shields.io/badge/belgeler-Türkçe-D11F26?style=flat-square"></a>
</p>

<p align="center">
  <a href="#start-in-two-minutes"><strong>Start in two minutes</strong></a>
  ·
  <a href="#the-determinism-claim-stated-exactly"><strong>Read the claim</strong></a>
  ·
  <a href="#verified-rather-than-assumed"><strong>See what was verified</strong></a>
  ·
  <a href="README.tr.md"><strong>Türkçe</strong></a>
</p>

---

> **No model is anywhere in the generation path.** Not to write a sentence, not
> to pick a name, not to smooth a distribution. Every value comes from a seeded
> stream, a curated lexicon, or a declared grammar, so the provenance of every
> character is traceable to a file you can read.

Turkish enterprises cannot move production data into test, evaluation, or AI
pilot environments without KVKK exposure, and have had nothing realistic to use
instead. Mintmark mints that data: fully synthetic, Turkish-first, deterministic,
span-labeled, and sealed by a provenance manifest.

The name is numismatic. A mint mark is the small letter a mint strikes into a
coin to say where it was made. A Mintmark dataset carries the same thing in its
manifest, so a dataset that turns up six months later can still say what produced
it.

**Published as [`mintmark`](https://pypi.org/project/mintmark/) on PyPI.** 983
tests pass, all eighteen invariants have named tests, and the byte-level
determinism claim is observed on three platforms in a single CI run rather than
asserted from one.

> [!IMPORTANT]
> **What Mintmark is not.** It is not anonymization or masking of real data; it
> ingests no real data and cannot make yours safe. It is not legal advice and not
> a compliance guarantee. Synthetic realism has limits: the data follows declared
> distributions and curated lexicons, not any real population, so conclusions
> drawn from it are conclusions about the declarations. Generated phone numbers
> can coincide with assigned ones, because the Turkish numbering plan reserves no
> fictional range. This data is for testing systems. It is never for contacting
> anyone.

## The unit of value in one picture

![Diagram of the Mintmark pipeline: declared inputs enter a deterministic mint with no model, no network, no floating point and no transcendental call; the output is data, label sidecars, a manifest and checksums; verify and reproduce close the loop back to the same inputs](assets/readme/mint-pipeline.png)

<p align="center"><sub><a href="assets/readme/mint-pipeline.svg">View the accessible SVG source</a></sub></p>

Most synthetic data tools make plausible records easy. Mintmark is concerned with
what happens around that:

| Question | Mintmark's answer |
| --- | --- |
| Can this identifier belong to a real person? | No. Safe mode emits provably checksum-invalid values, and `verify` runs the same validator a consumer would to prove it. |
| Will I get the same data next month? | Yes, byte for byte, from the same engine version, pack digest, recipe, seed, policy, and format. |
| What produced this directory of files? | `MINTMARK.json`, which binds the engine, the pack digest, the recipe, the seed, the policy, the taxonomy pin, and every checksum. |
| How do I know the labels line up? | Every span is recorded as its surface is placed. `verify` re-slices every one from the text it indexes, checks bounds, overlap and label, and requires an identifier span to read like the identifier its label names. |
| Can I check any of this without trusting you? | Yes. `mintmark reproduce` re-mints from the manifest alone and compares bytes. |
| What did the data actually contain? | The manifest records achieved distributions and label coverage next to the targets, whether or not they were met. |

## Start in two minutes

Offline after dependency bootstrap. No keys, no accounts, no network. The engine
runs on CPython 3.12 only; `uv tool install` fetches that interpreter for you,
while `pip` needs a 3.12 environment to install into.

```bash
uv tool install mintmark        # or, inside a Python 3.12 environment: pip install mintmark
mintmark mint --pack example --recipe demo --seed 42 --out ./demo-run
mintmark verify ./demo-run
```

`demo-run/` will contain:

```
customer.jsonl                 100 records, one JSON object per line
transaction.jsonl              100 records, each with a rendered description
transaction.labels.jsonl       span offsets into each description
MINTMARK.json                  the provenance manifest
SHA256SUMS                     a checksum per emitted file
```

and `mintmark verify` prints exactly this:

```
manifest schema: valid
checksums: 3/3 match
identifier policy: safe (confirmed)
checksum-valid identifiers found: 0
coverage targets: 0 checked
taxonomy: hushmark-tr v0.1, pin af11b31e4916
label alignment: 100 documents, 89 spans
dataset license: CC-BY-4.0
attribution: mintmark-example 0.1.0 reference dataset (recipe demo, seed 42), lokomotifai, licensed CC-BY-4.0
authenticity: self-consistency only; no trusted manifest digest supplied
```

A test asserts that block against what `verify` actually prints, so this example
cannot go stale while looking current.

One record, as emitted:

```json
{"customer_id":"CUST-00000000","first_name":"Kaan","last_name":"Kılıç","national_id":"71773625043","email":"kaan.kilic.1256@example.org","phone":"+90 525 886 73 05","il":"Batman","segment":"affluent","balance_kurus":277663,"currency":"TRY"}
```

Every field there is synthetic. The national identity number fails its own check
digit rule. The address sits under a domain nobody can register. The balance is
integer kuruş, because a float would put the emitted bytes at the mercy of the
platform.

## Identifiers cannot be real

Six engines, each with a `safe` default and an opt-in `validator` mode. Safe mode
is not a promise; it is a property the verifier re-checks on the artifacts.

| Engine | What makes a safe value unable to be real |
| --- | --- |
| **TCKN** | Both public check rules are computed correctly, then the second is corrupted by a nonzero offset. The number's visible shape is untouched and the invalidity sits exactly where a checker looks. |
| **VKN** | The same, over an algorithm verified against two independent open implementations across 200 000 inputs before a line of it was written. |
| **IBAN** | Check digits are shifted within the admissible 02 to 98 window, and the bank code is `99999`, verified absent from the TCMB participant list. Even a validator-mode IBAN names no real institution. |
| **PAN** | Sixteen digits beginning with `9`, a major industry identifier no commercial card network uses. That holds under both policies. Default emission is masked. |
| **PHONE** | Format-correct only. The Turkish numbering plan reserves no fictional mobile range, so coincidence is possible. This is documented rather than hidden, and the purpose limitation follows: test systems, never contact anyone. |
| **EMAIL** | Only `.example` and the `example.com` family, reserved by RFC 2606 and RFC 6761 so that nobody can ever register them. |

`validator` mode exists so you can test your own validation logic against
something that passes. It is opt-in per mint, and every dataset minted under it
carries a warning block that `verify` refuses to accept as missing.

## The determinism claim, stated exactly

> Identical engine version, pack digest, recipe, seed, identifier policy, and
> output format produce byte-identical data files and label sidecars, on CPython
> 3.12 on Linux x86_64, Linux arm64, and macOS arm64.

The manifest's `provenance` block, meaning the creation timestamp and the
invocation line, is excluded. Everything else in the manifest is included.
Windows is not claimed and is not tested.

Every term is load-bearing, and the claim is narrow because keeping it is
someone's job. What makes it hold:

| Constraint | Why |
| --- | --- |
| No float in emitted data | A float's text form depends on the platform's formatting of a binary approximation. Money is integer kuruş; rates are decimal strings. |
| No transcendental call in the mint path | libm results differ across platforms and libm versions. Log-normal amounts come from 1024-knot inverse-CDF tables generated offline and interpolated with integer arithmetic. |
| A stream per generation site | Adding a field shifts no other field's values. One shared stream would shift everything after the insertion point and silently invalidate every published manifest. |
| A NUL separator in stream derivation | Without it, a pack named `ab` at version `c` hashes identically to a pack named `a` at version `bc`, aliasing two streams into one. |
| Rejection sampling, not modulo | Modulo over-represents the first residues. A fixture whose purpose is fairness cannot carry a skew nobody declared. |
| Declaration order in serialization | Not sorted, not insertion order. A serializer change must not report a mismatch that is not one. |

`tests/golden/demo-run/` holds committed bytes, not a re-execution. Minting twice
in one process proves the code is a function of its inputs; only committed bytes
prove today's code is the same function yesterday's was.

## What Mintmark protects, and what it does not

| It does | It does not |
| --- | --- |
| Produce data that contains no real personal information, because it ingests none | Anonymize or mask your real data. That is [Hushmark](https://github.com/lokomotifai/hushmark)'s side of the boundary |
| Give you a record that lets a third party re-derive and check the dataset | Certify that dataset for any purpose, or make any compliance claim |
| Label spans against a closed taxonomy so a detector can be scored | Tell you whether your detector is good enough |
| State exactly which platforms the byte claim covers | Cover platforms it has not been observed on |
| Keep every generated organization fictional and scanned against a real-institution list | Guarantee a name is unclaimed in every jurisdiction and register |
| Emit checksum-invalid identifiers by default | Prevent a phone number from coinciding with an assigned one; no fictional range exists to draw from |

Mintmark is not legal advice and not a compliance guarantee. It describes what
the software does. Mapping that to your obligations is your work.

## One hub, thin spokes

![Diagram of the Mintmark family: a single engine repository with three sector pack repositories hanging from it, banking, insurance and human resources, plus a fourth drawn dashed and marked deferred for health](assets/readme/family-topology.png)

<p align="center"><sub><a href="assets/readme/family-topology.svg">View the accessible SVG source</a></sub></p>

This repository is the engine. Sector packs are separate repositories carrying
declarations and data with no engine code at all: their only Python lives in
tests and imports nothing beyond the public API.

| Repository | Status | Contents |
| --- | --- | --- |
| **mintmark** | this repository | generation, identifiers, annotation, manifests, the CLI, one example fixture pack |
| **[mintmark-banking](https://github.com/lokomotifai/mintmark-banking)** | first spoke | customers, accounts, cards, transactions, complaints, KYC notes, support transcripts |
| **[mintmark-insurance](https://github.com/lokomotifai/mintmark-insurance)** | second spoke | policyholders, policies, claims, payments, claim notes, call transcripts |
| **[mintmark-hr](https://github.com/lokomotifai/mintmark-hr)** | third spoke | employees, position history, leave, payroll, performance and recruiter notes, HR requests |
| health | deferred | Its special-category density needs a stricter governance review before a brief is even written |

Each pack pins this engine by a version range with a closed upper bound, so a
future engine cannot silently change what a published manifest reproduces.

## Verified rather than assumed

Four facts this project depends on live in public registries and specifications
rather than in any document here. Coding them from memory would have produced
software that is confidently wrong, so each was checked against primary sources
and the record kept.

| Fact | Source | Outcome |
| --- | --- | --- |
| The VKN check-digit algorithm | Two independent open implementations, in different languages by different authors | Zero disagreements across 200 000 random inputs; both reproduce the published test vector |
| IBAN bank code `99999` is unassigned | TCMB payment systems participant list, revision 072025 | 71 participants, codes 0001 to 0807, nothing in the 9xxxx range |
| Turkey is permanently UTC+3 | The IANA time zone database | One offset across 2017 to 2030, daylight saving zero at every sampled instant |
| The institution denylist | The same TCMB list | 70 entries covering all 71 participants, each matched back against its source by a test |

Full records with retrieval dates are in
[docs/normative-verification.md](docs/normative-verification.md). The two that
drift are re-checked weekly by a separate, network-labeled workflow that opens an
issue and never updates anything on its own.

## Repository map

```
src/mintmark/
  engine/         streams, SplitMix64, unbiased draws, fixed-point tables, templates
  identifiers/    tckn, vkn, iban, pan, phone, email; safe and validator modes
  annotate/       the closed taxonomy, span capture, rendering, sidecars
  packs/          strict fail-closed loading, schemas, the canonical pack digest
  emit/           canonical JSONL and CSV, atomic output
  manifest/       MINTMARK.json, checksums, verify
  lexicons/       Turkish base lexicons and the institution denylist
  minting.py      the composition root, where the layers meet
  cli.py          seven verbs, five exit codes, stable JSON payloads
schemas/          pack and manifest JSON Schemas, versioned
packs/example/    the fixture pack the quickstart uses
assets/           committed distribution tables and the denylist
tools/            the offline table generator, the prose lint, the canary check
tests/            unit, property, golden, adversarial, conformance
```

Module dependency direction is enforced by `import-linter` in required CI, and
`engine` imports only the standard library. That is not tidiness: it is what
makes the determinism claim checkable, because every value the engine produces
comes from arithmetic this repository specifies rather than from a dependency's
release schedule.

## Develop the repository

```bash
uv sync
uv run ruff format --check . && uv run ruff check .
uv run mypy --strict src/
uv run lint-imports
uv run pytest
uv run python tools/mdlint.py .
```

All of it runs offline once dependencies are installed. Two checks are worth
knowing about before you meet them.

`tools/mdlint.py` enforces the language rules on prose in both languages:
sentence-case headings, a banned promotional vocabulary, and no em dash or en
dash anywhere. Quoted third-party text is exempted with a marker that has to
carry a reason.

`tools/canary.py` proves that private planning material is absent from the tree
and from built artifacts. The canary string is never committed, because
committing it would plant the very thing the check looks for; it arrives through
`MINTMARK_CANARY` and only its digest lives here.

## Project status

Version 0.1, pre-release. The public surface under semantic versioning is the
command-line grammar, the exit codes, the `--json` payloads, the library's two
functions, both JSON Schemas, and the bytes a fixed seed produces.

That last one deserves emphasis. **A change that alters emitted bytes for a fixed
seed is a major version event even when no signature moved**, because it breaks
the reproducibility of every published manifest. While the major version is
zero, that event is carried by the minor version, as 0.3.0 did; a patch release
never moves bytes.

Published on PyPI as [`mintmark`](https://pypi.org/project/mintmark/), and
released on GitHub with the wheel, the source distribution, and a software bill
of materials attached. Publication runs through trusted publishing over OIDC
behind an approval gate, so no long-lived token exists in this repository.

The name is frozen. Trademark screening cleared on 2026-08-22, and the PyPI
namespace is held by the project.

## Community contract

Contributions are accepted under the Developer Certificate of Origin 1.1 with no
contributor license agreement. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
checks to run and the language rules to follow, [GOVERNANCE.md](GOVERNANCE.md)
for how decisions are made and what the single-maintainer rule currently is, and
[SECURITY.md](SECURITY.md) for the private reporting route and what counts as a
vulnerability here.

`README.md` is canonical and [README.tr.md](README.tr.md) is a full mirror, not a
summary. A change to one without the other fails review, and a test compares
their structure.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/determinism.md](docs/determinism.md) | The claim, why each term is narrow, and how to reproduce a published dataset |
| [docs/taxonomy.md](docs/taxonomy.md) | The eighteen labels, the pin, and what happens when upstream moves |
| [docs/normative-verification.md](docs/normative-verification.md) | What was verified, against which source, on what date, with what outcome |
| [docs/engineering-notes.md](docs/engineering-notes.md) | Build quirks, environment traps, and the invariant-to-test map |

## Why this exists

The hushmark-tr model card asks adopters to evaluate the detector on
representative data before production use. That is an honest limitation, and it
had no honest answer in Turkish: the representative data did not exist, and
production data could not be used to make it.

Mintmark is that answer. One sibling's stated limitation is the other sibling's
product definition.

## License and trademark

Code is Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Datasets minted by this engine carry the terms their pack declares, written into
`MINTMARK.json` and printed by `verify`. Every pack in this family declares
**CC BY 4.0**: any use including commercial, with credit. See
[LICENSE-DATASETS.md](LICENSE-DATASETS.md).

What a synthetic dataset does and does not mean under Turkish data
protection law is set out in [docs/kvkk.md](docs/kvkk.md).

The license grants no right to the Mintmark name or logo. See
[TRADEMARKS.md](TRADEMARKS.md) for what fair community use covers.

<p align="center"><sub>Part of the lokomotifai family: <a href="https://github.com/lokomotifai/pactmark">Pactmark</a> seals agent execution · <a href="https://github.com/lokomotifai/hushmark">Hushmark</a> seals data egress · <a href="https://github.com/lokomotifai/permitmark">Permitmark</a> seals secret ingress · Mintmark seals data supply</sub></p>
