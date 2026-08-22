# Governance

This file describes how decisions are made in this repository today, not how we
would like them to be made eventually.

## Current state, stated plainly

Mintmark is founder-led and has one maintainer. Independent maintainer review is
not currently possible. This is a real limitation and it is recorded here rather
than disguised by a review process that has only one participant.

## Governing principles

1. Authority stays outside the model. Nothing in this project delegates a
   decision to a generated output.
2. Every claim about behavior is backed by an observation that was recorded.
3. Settled decisions are reopened only when implementation evidence contradicts
   them, and the change is recorded as a new decision rather than as an edit to
   the old one.
4. Understatement is the default register, especially where a regulation is
   nearby.

## Roles

**Contributor.** Anyone who opens an issue or a pull request. No prior
relationship is required.

**Reviewer.** A contributor invited to review in a named scope after sustained,
accurate review work. Reviewers do not merge.

**Maintainer.** Holds merge authority and release authority in a named scope.
Listed in `MAINTAINERS.md` with that scope.

## Decision classes

| Class | Examples | Who decides |
| --- | --- | --- |
| Routine | Bug fix, test, documentation correction, dependency bump | Maintainer merge |
| Substantive | New CLI surface, schema change, new runtime dependency, invariant change | Maintainer decision recorded in the changelog and, where architectural, as a numbered decision |
| Settled family decision | Topology, identifier policy defaults, taxonomy pin, licensing, the no-model rule | Not decided here. These come from the family charter and change only by an explicit family-level decision |
| External authority | Repository creation, publication, releases, name freeze, any sentence referencing a regulation | Not a maintainer decision. Requires the owner's recorded approval |

## Founder-led merge rule, and the control that replaces it

While there is one maintainer, that maintainer may merge their own changes. The
compensating control is that no merge passes without required CI green, and the
invariant suite is written so that the checks, rather than the reviewer, are what
stands between a defect and the main branch.

When a second maintainer joins, this rule is removed and two-party review
applies to substantive changes. That is the trigger, not a date.

## Releases

Releases are cut by a maintainer, are immutable once published, and sit behind
the owner's recorded approval. Publication credentials are never long-lived
tokens in this repository; publication uses trusted publishing over OIDC.

## Continuity

If the sole maintainer becomes unavailable, the repository is archived rather
than transferred silently. An archived repository with an honest notice is
better for its users than an unmaintained one that looks alive.
