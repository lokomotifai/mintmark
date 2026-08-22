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

- Repository foundation: licensing, trademark, attribution, and governance file
  set; contribution model under the Developer Certificate of Origin 1.1 with no
  contributor license agreement.
- Engineering baseline: CPython 3.12 pinned, `uv` and `hatchling` packaging,
  `ruff` format and lint, `mypy --strict`, `pytest` with `hypothesis`, and
  `import-linter` contracts encoding the module dependency direction.
- `tools/mdlint.py`, enforcing sentence-case headings, the banned vocabulary of
  the repository standard in English and Turkish, and the ban on the em dash and
  en dash in repository prose, with a documented allowlist for quoted text.
- `tools/canary.py`, proving that private planning material is absent from the
  tree and from built artifacts.

### Notes

No release has been published. No package exists on any registry. Nothing in
this file should be read as a claim that an installable artifact is available.
