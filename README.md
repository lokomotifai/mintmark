# Mintmark

**Mint deterministic, fully synthetic, Turkish-first datasets with span-level
personal-data labels and a provenance manifest.**

> **Important: what this is not.**
>
> Mintmark is not anonymization or masking of real data. It never reads real
> data, and it cannot make real data safe.
>
> It is not legal advice and not a compliance guarantee. It describes what the
> software does; mapping that to your obligations is your work, not this tool's.
>
> Synthetic realism has limits. The data is shaped by declared distributions and
> curated lexicons, not fitted to any real population. Treat statistical
> conclusions drawn from it as conclusions about the declarations.
>
> Generated phone numbers can coincide with assigned ones. The Turkish numbering
> plan reserves no fictional mobile range, so this cannot be engineered away.
> This data is for testing systems. It is never for contacting anyone.

## Quickstart

Offline after dependency bootstrap. No keys, no accounts, no network.

    uv tool install mintmark        # or: pip install mintmark
    mintmark mint --pack packs/example --recipe demo --seed 42 --out ./demo-run
    mintmark verify ./demo-run

`demo-run/` will contain:

    customer.jsonl                 100 records, one JSON object per line
    transaction.jsonl              100 records, each with a rendered description
    transaction.labels.jsonl       span offsets into each description
    MINTMARK.json                  the provenance manifest
    SHA256SUMS                     a checksum per emitted file

and `mintmark verify` reports:

    manifest schema: valid
    checksums: 3/3 match
    identifier policy: safe (confirmed)
    checksum-valid identifiers found: 0
    taxonomy: hushmark-tr v0.1, pin af11b31e4916
    label alignment: 100 documents, 81 spans

Run the same command twice and the data files are byte-identical. Run
`mintmark reproduce ./demo-run` and it re-mints from the manifest and compares.

## What you get

A minted dataset is data files, a label sidecar per document type, a manifest,
and checksums. The manifest binds the engine version, the pack identity and
digest, the recipe, the seed, the identifier policy, the taxonomy pin, every
output checksum, and the distributions the mint actually achieved. A dataset
without its manifest is not a Mintmark deliverable, because nothing then
connects the files to what produced them.

Labels come from a closed set of eighteen: the twelve named-entity types of the
hushmark-tr v0.1 taxonomy, plus TCKN, VKN, IBAN, PAN, PHONE, and EMAIL. An
unknown label anywhere fails closed.

## Identifiers are checksum-invalid by default

Every identifier engine has two modes.

`safe` is the default. It emits values that are format-plausible and provably
checksum-invalid, so a generated identifier cannot be a real one. IBANs carry a
bank code verified as unassigned; card numbers begin with a major industry
identifier no commercial network uses; email addresses sit only under reserved
documentation names that nobody can register.

`validator` emits checksum-valid values. It exists so you can test your own
validation logic against something that passes. It is opt-in per mint, and every
dataset minted under it carries a warning block in its manifest that `verify`
refuses to accept as missing.

## Determinism, and exactly what is claimed

Identical engine version, pack digest, recipe, seed, identifier policy, and
output format produce byte-identical data files and label sidecars, on CPython
3.12 on Linux x86_64, Linux arm64, and macOS arm64.

The manifest's `provenance` block, meaning the creation timestamp and the
invocation line, is excluded. Everything else in the manifest is included.

Windows is not claimed and is not tested.

That claim is why generation uses no floating point in emitted data, no
transcendental function anywhere in the mint path, and no model of any kind.

## Project status

Version 0.1, pre-release. The public surface under semantic versioning is the
command-line grammar, the exit codes, the `--json` payloads, the library's two
functions, the pack schema, the manifest schema, and the bytes a fixed seed
produces. That last one deserves emphasis: a change that alters emitted bytes
for a fixed seed is a major version event even when no signature changed,
because it breaks the reproducibility of every published manifest.

The name Mintmark is provisional pending trademark screening. Nothing is
published to any package registry yet, and this README makes no claim that
anything is.

## Sector packs

The engine ships one example fixture pack, used by the quickstart and the tests.
It is explicitly not a sector pack.

Sector packs are separate repositories carrying declarations and data with no
engine code: `mintmark-banking`, then `mintmark-insurance`, then `mintmark-hr`.
Each pins this engine by a version range with a closed upper bound and ships a
versioned reference dataset as release artifacts.

## Why this exists

The hushmark-tr model card asks adopters to evaluate the detector on
representative data before production use. Turkish enterprises cannot use
production data for that without KVKK exposure, and have had nothing realistic
to use instead. Mintmark produces exactly that evaluation data, labeled against
the same closed taxonomy, with no real personal data involved at any point.

## Documentation

- [docs/determinism.md](docs/determinism.md), the claim and how to reproduce a dataset
- [docs/taxonomy.md](docs/taxonomy.md), the label set, the pin, and the drift procedure
- [docs/normative-verification.md](docs/normative-verification.md), what was verified against which source and when
- [docs/engineering-notes.md](docs/engineering-notes.md), operational know-how for contributors

## License and trademark

Code is Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The license grants no right to the Mintmark name or logo. See
[TRADEMARKS.md](TRADEMARKS.md).

Türkçe için [README.tr.md](README.tr.md) dosyasına bakın.
