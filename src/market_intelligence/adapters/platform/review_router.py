"""Platform ReviewRouterPort: submit the routed brief review to Hrz7 via ``review-kit``.

Builds the review from the escalated brief and submits it to the Hrz7 service intake
(``POST /v1/service/reviews``), S2S-authenticated. The Hrz7 base URL comes from
``HRZ_HUMAN_REVIEW_URL`` and the S2S credentials from this repo's shared platform envs
(``HRZ_S2S_TOKEN`` / ``HRZ_S2S_SIGNING_KEY``, reused from ``adapters/platform/_s2s.py`` so a fix
to the S2S transport rule stays a single edit). No cloud SDK is involved (the kit uses stdlib
``urllib`` + the wire-compatible S2S headers), so this module imports cleanly with no Google Cloud
SDK; it binds under the ``gcp`` and ``platform`` profiles because it makes a real network call to
a sibling service.
"""

from __future__ import annotations

from review_kit import ReviewClient

from ...config import Settings
from ...domain.models import MarketBrief
from ...envread import read_env_setting
from .._review_payload import brief_to_review
from ._s2s import SIGNING_KEY_ENV, TOKEN_ENV


class PlatformReviewRouter:
    """Submit escalated market briefs to Hrz7 (rule R8), reusing the shared S2S envs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(  # pragma: no cover - needs live Hrz7
        self, brief: MarketBrief, *, maker: str, tenant: str = ""
    ) -> None:
        # Unset and set-but-empty collapse DELIBERATELY: both are closed in the same direction,
        # because there is no default Hrz7 to fall back to and the routing refuses below either
        # way. A localhost default here would be the dangerous shape; there isn't one.
        base_url = read_env_setting("HRZ_HUMAN_REVIEW_URL").value
        if not base_url:
            raise RuntimeError("HRZ_HUMAN_REVIEW_URL must be set to route reviews to Hrz7")
        client = ReviewClient(
            base_url,
            token_env=TOKEN_ENV,
            signing_key_env=SIGNING_KEY_ENV,
        )
        client.submit(
            brief_to_review(brief, maker=maker, tenant=tenant),
            actor="mkt1-market-intelligence",
        )
