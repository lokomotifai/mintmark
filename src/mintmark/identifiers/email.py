"""Email addresses under reserved documentation names only.

Every address this engine emits sits under a name the IETF has reserved so that
it can never be registered by anyone: the `.example` top-level domain, and
`example.com`, `example.net`, and `example.org` (RFC 2606, RFC 6761). A generated
address therefore cannot reach a real mailbox, no matter who reads the dataset or
what they do with it.

This is the one identifier surface where a guarantee is actually available, and
it is worth having precisely because the phone engine cannot offer the same.
"""

from __future__ import annotations

from mintmark.engine.draws import bounded, bounded_range
from mintmark.engine.fold import fold_for_local_part
from mintmark.engine.prng import SplitMix64
from mintmark.identifiers.policy import IdentifierPolicy

LABEL = "EMAIL"

# RFC 2606 section 2 and RFC 6761 section 6.5. Nothing else may ever appear.
RESERVED_DOMAINS: tuple[str, ...] = ("example.com", "example.net", "example.org")
RESERVED_TLD = ".example"

_FALLBACK_LOCAL = "kullanici"


def derive_local_part(first_name: str, last_name: str) -> str:
    """Fold a name into a local part: lowercase, ASCII, dot-separated.

    A name that folds to nothing, which a name written entirely in punctuation
    would, falls back to a fixed placeholder rather than producing an address
    with an empty local part.
    """
    parts = [fold_for_local_part(first_name), fold_for_local_part(last_name)]
    parts = [p for p in parts if p]
    return ".".join(parts) if parts else _FALLBACK_LOCAL


def generate(
    stream: SplitMix64,
    policy: IdentifierPolicy,
    *,
    first_name: str = "",
    last_name: str = "",
    subdomain: str | None = None,
) -> str:
    """Emit one address under a reserved documentation name.

    `subdomain`, when given, produces `<subdomain>.example`, which is how an
    employer or institution domain is represented without leaving the reserved
    space. It is folded first, so a Turkish organization name yields a valid
    hostname label.
    """
    del policy
    local = derive_local_part(first_name, last_name)
    if not first_name and not last_name:
        local = f"{_FALLBACK_LOCAL}{bounded(stream, 10000):04d}"

    if subdomain:
        host = f"{fold_for_local_part(subdomain)}{RESERVED_TLD}"
    else:
        host = RESERVED_DOMAINS[bounded(stream, len(RESERVED_DOMAINS))]

    # A disambiguating suffix keeps two people with the same folded name from
    # sharing an address, which would break uniqueness a consumer may rely on.
    suffix = bounded_range(stream, 1, 9999)
    return f"{local}.{suffix}@{host}"


def is_reserved(address: str) -> bool:
    """Return True when the address sits under a reserved documentation name."""
    _, _, host = address.rpartition("@")
    if not host:
        return False
    host = host.lower()
    return host in RESERVED_DOMAINS or host.endswith(RESERVED_TLD)


def is_checksum_valid(value: str) -> bool:
    """Email addresses carry no checksum. See the note in the phone engine."""
    del value
    return False


def is_well_formed(value: str) -> bool:
    """Return True when `value` is one address under a reserved documentation name.

    Every emitted address sits under `.example` or the `example.com` family, so
    a span labeled EMAIL that reads anything else is not the value this engine
    placed there.
    """
    local, at, _ = value.partition("@")
    return bool(at) and bool(local) and " " not in value and is_reserved(value)
