"""Identity value objects for server-side, verified principals, re-exported not redeclared.

The agent never trusts a client-asserted ``actor``. A :class:`Principal` is resolved
server-side by an :class:`~market_intelligence.ports.identity.IdentityPort` adapter (local
dev persona, GCP IAP-verified assertion, or an on-prem client IdP) from the inbound
transport context, and becomes the audit actor plus the entitlement principals a future
governed-retrieval path would consume.

Nothing is declared in this module. ``IdentityError``, ``RequestContext``, ``Principal`` and
``ANONYMOUS`` all come from ``hex_service_kit.identity``, which is where the fleet's single copy
lives. This repo's hand-copied versions were field-for-field identical to it, which is precisely
the state in which a copy is cheapest to retire and most likely to drift next. That package is
pure standard library, so the domain core stays framework-free and cloud-SDK-free.

The import site stays here so every caller keeps its existing
``from ..domain.identity import Principal`` and the hexagon still names its own boundary.
"""

from __future__ import annotations

from hex_service_kit.identity import (
    ANONYMOUS as ANONYMOUS,
)
from hex_service_kit.identity import (
    IdentityError as IdentityError,
)
from hex_service_kit.identity import (
    Principal as Principal,
)
from hex_service_kit.identity import (
    RequestContext as RequestContext,
)

__all__ = ["ANONYMOUS", "IdentityError", "Principal", "RequestContext"]
