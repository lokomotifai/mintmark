# Security policy

## Report privately

Use GitHub private vulnerability reporting on this repository's security tab.
That route lets us coordinate disclosure without exposing the report in a public
issue.

If that route is unavailable, email
[fatih@komunite.com.tr](mailto:fatih@komunite.com.tr?subject=Mintmark%20security%20contact)
and ask for a secure channel. Do not include exploit detail or secrets in
unencrypted email. Do not open a public issue to ask whether a report is in
scope; ask privately instead.

## Response targets

These are targets, not contractual service levels:

- acknowledgement within three business days;
- initial triage within seven business days; and
- a proposed remediation or coordination plan for a confirmed high-impact report
  within fourteen business days.

Reports are validated against synthetic data only, which is the entire subject
matter of this project. A regression test accompanies every fix.

## Security boundaries

Mintmark is a local generator. It reads a pack, writes files, and performs no
network input or output. Its threat model follows from that.

**In scope.** A pack that causes code execution, path traversal outside the
output directory, or resource exhaustion that a strict loader should have
refused. Safe-mode output that contains a checksum-valid identifier. A manifest
that verifies against tampered data. A `verify` or `reproduce` result that
reports success where the bytes differ. Any network call made during a mint. Any
path by which private material could reach a built artifact.

**Out of scope.** The realism of generated data, which is a quality question
rather than a security one. Coincidental resemblance between a generated phone
number and an assigned one, which is documented in the README as a known
limitation of the Turkish numbering plan. Anything a consumer does with a minted
dataset after it leaves this tool.

**Explicitly not a vulnerability.** That validator mode produces checksum-valid
identifiers. That is its stated purpose, it is opt-in per mint, and every such
dataset carries a warning block in its manifest. A report that validator mode
works as documented will be closed with a pointer to this paragraph.

## What this project does not claim

Mintmark makes no compliance guarantee under any regulation. It is not
anonymization of real data. Using it does not by itself make any downstream
system lawful.
