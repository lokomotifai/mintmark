# Roadmap

Direction, and what is deliberately not promised. There are no dates here.
Ordering is by dependency.

## Now

The v0.1 core engine: deterministic generation, six identifier engines with a
safe default, span-level labeling against a closed taxonomy, strict fail-closed
pack loading, canonical emission, a provenance manifest with verification and
reproduction, and a command-line surface. An example fixture pack ships with it
so that the quickstart works with no other download.

## Next

The sector packs, which are separate repositories, not features of this one. The
first is banking, then insurance, then human resources. Health is deferred; its
special-category density needs a stricter governance review before a brief for it
is even written.

## Under consideration

Additional identifier systems as Turkish public registries make their check rules
available. Additional output formats where a consumer's pipeline cannot read
JSONL or CSV. Wider platform coverage for the determinism claim, each added
platform being a new promise to keep rather than a configuration change.

## Not promised

The following are not on the roadmap, and some are permanently excluded rather
than merely unscheduled:

- A model anywhere in the generation path. Permanently excluded.
- Synthesis fitted on real data, and ingestion of real data in any form.
  Permanently excluded from the core.
- Differential privacy claims of any kind.
- Locales other than Turkish in v0.x.
- A graphical interface, a hosted service, or a database loader.
- A plugin system that runs third-party generator code inside a mint.
- Any statistical realism guarantee beyond the distributions a pack declares.

Extension points may exist in the code for some of the above. Documentation will
never present an extension point as a shipped feature.

## How this file changes

An item moves between sections when its dependency is met, not when it becomes
interesting. Anything that moves into "now" has a milestone with an observable
exit condition behind it.
