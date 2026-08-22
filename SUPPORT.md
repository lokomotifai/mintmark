# Support

## Choose the right route

| You want to | Use |
| --- | --- |
| Report a defect in behavior | A GitHub issue with the reproduction below |
| Ask how something is meant to work | A GitHub discussion |
| Report a security vulnerability | The private route in [SECURITY.md](SECURITY.md), never a public issue |
| Report conduct | The email route in [MAINTAINERS.md](MAINTAINERS.md) |
| Propose a change | A pull request, after reading [CONTRIBUTING.md](CONTRIBUTING.md) |

## What makes a useful report

A mint is a pure function of its declared inputs, which makes most defects
reproducible exactly. Include:

1. The exact command, with the pack, recipe, seed, identifier policy, and
   output format.
2. The `mintmark --version` output and your operating system and architecture.
3. `MINTMARK.json` from the run, or the parts of it you can share.
4. What you observed and what you expected instead.

A report carrying a seed and a manifest can usually be reproduced on the first
attempt. A report without them usually cannot be reproduced at all.

## Support boundary

This project is maintained by one person alongside other work. What that means
in practice, stated honestly rather than implied:

- There is no service level and no response time commitment for support.
  Security reports have targets, and those are in [SECURITY.md](SECURITY.md).
- There is no commercial support offering attached to this repository.
- Help with your own data pipeline, your own detector, or your own compliance
  position is out of scope. Mintmark produces data; what you conclude from it is
  yours to determine.
- Questions about whether using synthetic data satisfies a legal obligation
  cannot be answered here. This project is not legal advice.
