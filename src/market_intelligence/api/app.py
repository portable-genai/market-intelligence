"""FastAPI app — thin HTTP boundary over the domain services.

Owns no business logic: it translates a request into a domain call and serialises the cited
result with ``to_jsonable``. Heavy / cloud imports stay lazy so importing this module under
the local profile needs no Google Cloud SDK.

Identity is server-verified: every route depends on :data:`CurrentPrincipal`, so the audit
actor is the verified end-user (never a client-asserted value). The embedding surface is
controlled by an env-driven CORS allowlist and a CSP ``frame-ancestors`` header, so the UI
can drop into a client's existing web app same-origin or run standalone. See
``docs/embedding-and-identity.md``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from hex_service_kit import cors_allowlist, resolve_bind_host
from hex_service_kit.web import add_loopback_exposure_guard

from ..config import end_user_auth_kind
from ..domain.errors import GuardrailBlockedError, ResearchEmptyError
from ..domain.identity import IdentityError
from ..domain.models import BriefRequest, Market, Vertical
from ..domain.serialization import to_jsonable
from ..envread import read_env_setting
from ..ports.identity import VERIFIED
from . import deps
from .deps import make_brief_service
from .schemas import AgentCardModel, BriefRequestModel, HealthModel
from .security import CurrentPrincipal

_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Embedding-surface controls. In secure/embedded mode the agent is served same-origin via
# the parent app's reverse-proxy (no CORS needed); for the cross-origin / standalone dev
# case, MKT_INTEL_CORS_ORIGINS is an explicit per-tenant allowlist (never "*").
# MKT_INTEL_FRAME_ANCESTORS is the CSP frame-ancestors allowlist of parent origins permitted
# to iframe the agent UI.
_FRAME_ANCESTORS_ENV = "MKT_INTEL_FRAME_ANCESTORS"
_CORS_ORIGINS_ENV = "MKT_INTEL_CORS_ORIGINS"

_LOGGER = logging.getLogger(__name__)


#: Entries that are a wildcard by BEHAVIOUR rather than by spelling, so the asterisk test below
#: cannot see them. ``null`` is the one that matters: a SANDBOXED iframe presents the origin
#: ``null``, so allowing it hands framing and credentialed cross-origin rights to any page able
#: to open one. ``'*'`` is what a quoted Terraform variable or a YAML string renders, and ``*.*``
#: is a host pattern matching every name with a dot in it. The same set is refused on the
#: document half, in ``ui/lib/csp.mjs``.
_WILDCARD_TOKENS = frozenset({"*", "'*'", "null", "*.*"})


def _refuse_wildcard(values: Sequence[str], env_name: str) -> None:
    """Refuse a resolved origin policy that names a wildcard, at boot rather than per request.

    Both allowlists were resolved carefully in three states and then handed on verbatim, with
    the "never ``*``" rule living only in the comment above and in the runbook. A comment does
    not fail a build: ``frame-ancestors *`` lets ANY page frame the console, and ``*`` in the
    CORS allowlist grants every origin on the internet the trust the allowlist exists to
    restrict, on responses that carry credentials.

    Any token CONTAINING ``*`` is refused, not only a bare one. ``https://*.client.example``
    is a real CSP host-source wildcard covering every subdomain, including whichever one an
    attacker manages to register, and an allowlist is only worth having when each entry names
    an origin somebody decided to trust.

    The character test is necessary and not sufficient, so :data:`_WILDCARD_TOKENS` covers the
    spellings that carry no asterisk and behave as one anyway. A real origin never contains the
    character and is never one of those tokens, so this refuses nothing a deployment could
    correctly hold.
    """
    offending = [value for value in values if "*" in value or value in _WILDCARD_TOKENS]
    if offending:
        raise ValueError(
            f"{env_name} resolved to {offending}: the origin policy must never contain a "
            "wildcard. Name the exact parent origins that may frame or call this service, or "
            f"unset {env_name} to keep the restrictive default."
        )


def _frame_ancestors(raw: str | None) -> str:
    """Three-state read of ``MKT_INTEL_FRAME_ANCESTORS``; an emptied value REFUSES all framing.

    Unset keeps the shipped ``'self'``. A value naming no origin would emit the header
    ``Content-Security-Policy: frame-ancestors`` with an EMPTY directive, which is a CSP parse
    error, so browsers dropped the directive; and the ``== "'self'"`` branch below was skipped
    too, so no ``X-Frame-Options`` went out either and the clickjacking control disappeared
    entirely. An operator who empties the allowlist means "nobody may frame this", which is
    spelled ``'none'``, so that is what the emptied state now produces: the most restrictive
    value, logged, rather than a silently absent header.

    A value that DOES name something is used as given, once :func:`_refuse_wildcard` has
    established that it names origins rather than everybody.
    """
    if raw is None:
        return "'self'"
    normalised = " ".join(raw.split())
    if not normalised:
        _LOGGER.warning(
            "%s is set to an empty value, which names no permitted parent origin: emitting "
            "frame-ancestors 'none' (no framing at all). Unset it to take the 'self' default.",
            _FRAME_ANCESTORS_ENV,
        )
        return "'none'"
    _refuse_wildcard(normalised.split(), _FRAME_ANCESTORS_ENV)
    return normalised


# ``.raw`` and not ``.value``: this is one of the few reads that needs the UNSTRIPPED string,
# because :func:`_frame_ancestors` distinguishes all three states itself and ``None`` is what
# tells it "nobody configured an allowlist". Sourcing it from the commons reader keeps the
# shape out of the scanner's sights without pretending the three states are two.
_FRAME_ANCESTORS = _frame_ancestors(read_env_setting(_FRAME_ANCESTORS_ENV).raw)

# The two frame-ancestors policies the pre-CSP header can also express.
_LEGACY_FRAME_OPTIONS = {"'self'": "SAMEORIGIN", "'none'": "DENY"}


def _cors_origins() -> list[str]:
    """Explicit allowlist, never "*"; the localhost dev fallback applies ONLY under a
    DELIBERATELY chosen local profile (shared hex-service-kit rule).

    Keyed on ``exposure_profile``, not ``profile``: granting dev origins is a relaxation, so a
    run that never named a profile must not look like ``local`` here (see
    ``config.ProfileChoice``).

    The commons resolver used to document that it never returns ``*`` and then return what the
    variable said, so :func:`_refuse_wildcard` is what turned that documented rule into a
    refusal. It now refuses the same union itself, which is why the local rule runs FIRST, on
    the raw configured value, rather than on what the resolver hands back: on the old order the
    commons raised its own ``InsecureCorsError`` before this module's rule was reached, and the
    policy changed owner without anybody editing it. Refusing on the way in keeps
    :func:`_refuse_wildcard` the one authority over both allowlists, with one exception type
    and one message naming the variable to fix, and leaves the commons check as an unreachable
    backstop.
    """
    configured = read_env_setting(_CORS_ORIGINS_ENV).value
    _refuse_wildcard(
        [origin.strip() for origin in configured.split(",") if origin.strip()], _CORS_ORIGINS_ENV
    )
    return cors_allowlist(
        deps.get_settings().exposure_profile,
        origins_env=_CORS_ORIGINS_ENV,
        dev_origins=tuple(_DEV_ORIGINS),
    )


app = FastAPI(
    title="D1 Market Intelligence and Competitor Analysis",
    version="0.1.0",
    description=(
        "Cited market briefs and competitor analysis from grounded deep research and an "
        "internal corpus, generic across banking and online retail and the JP/AU/SG markets."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Dev-Persona"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Any:
    """Emit embedding-surface headers: CSP frame-ancestors (who may iframe the agent).

    ``X-Frame-Options`` is the pre-CSP equivalent, so it accompanies the two policies it can
    express: ``'self'`` maps to ``SAMEORIGIN`` and ``'none'`` to ``DENY``. A named allowlist has
    no ``X-Frame-Options`` spelling, so none is sent there rather than one that contradicts the
    CSP.
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = f"frame-ancestors {_FRAME_ANCESTORS}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if deps.get_settings().exposure_profile in {"gcp", "platform", "onprem"}:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    legacy = _LEGACY_FRAME_OPTIONS.get(_FRAME_ANCESTORS)
    if legacy is not None:
        response.headers["X-Frame-Options"] = legacy
    return response


# A request arrives with nothing authenticating the END USER unless BOTH of these hold, and
# the guard bounds every case where either fails:
#
#   1. a profile was chosen. Absent that, nobody selected an identity scheme, the seeded
#      persona adapter refuses to construct, and every end-user route answers 401; but
#      /healthz, /v1/personas and the agent card would still answer a stranger, and a
#      deployment in that state has no business being reachable at all. It is also the one
#      case where a settings file that bound a verifying adapter must NOT buy the relaxation:
#      unset is not consent, whatever the binding says;
#   2. the identity adapter the ACTIVE binding names DECLARES that it verifies the end user.
#      Seeded personas arrive on the X-Dev-Persona header the caller wrote (client-asserted)
#      and the on-premises placeholder resolves nobody at all (unimplemented); neither
#      authenticates anyone, so neither may switch this off. Read from the binding rather than
#      from the profile string, so a client that rebinds ``onprem`` to its own verifying IdP
#      adapter is answered about the adapter it actually runs.
_END_USER_AUTHENTICATED = deps.get_settings().profile_explicit and end_user_auth_kind() == VERIFIED

# Registered LAST, so it is the OUTERMOST middleware: an off-loopback caller is refused before
# CORS, before the header baseline above and before any route or dependency runs. Bound to the
# APP OBJECT, not to `main()`: the Dockerfile CMD is
# `exec uvicorn market_intelligence.api.app:app --host 0.0.0.0 --port ${PORT}`, so the
# `resolve_bind_host(...)` call down in `main()` never runs in a shipped process and
# GET /v1/personas served the full seeded-persona list to any LAN peer. Do not delete this:
# without it the container's own CMD re-opens that hole.
add_loopback_exposure_guard(
    app,
    unauthenticated=not _END_USER_AUTHENTICATED,
    # The SAME opt-in `main()` passes to resolve_bind_host, so an operator who accepts the
    # exposure accepts it once, for both the bind and the request-time guard.
    insecure_demo_env="MKT_INTEL_ALLOW_INSECURE_DEMO",
    # The EXPOSURE profile, so a run nobody configured names itself 'unconfigured' in the
    # refusal rather than borrowing the name of a profile an operator never chose.
    posture=deps.get_settings().exposure_profile,
)


def _to_request(body: BriefRequestModel) -> BriefRequest:
    try:
        return BriefRequest(
            topic=body.topic,
            market=Market(body.market),
            vertical=Vertical(body.vertical),
            competitors=tuple(body.competitors),
            max_sources=body.max_sources,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/healthz", response_model=HealthModel)
def healthz() -> HealthModel:
    """Liveness/readiness probe. Reports the active profile (the UI persona picker gates on
    ``profile == "local"``) plus the active market and vertical."""
    settings = deps.get_settings()
    return HealthModel(
        status="ok",
        # The EXPOSURE profile, so a run that never named one reports "unconfigured" rather
        # than the "local" that would switch the UI's persona picker on.
        profile=settings.exposure_profile,
        market=settings.market,
        vertical=settings.vertical,
        runtime=settings.runtime,
        generator_model=settings.generator_model,
    )


@app.get(
    "/.well-known/agent-card.json",
    response_model=AgentCardModel,
    tags=["governance"],
)
def agent_card() -> AgentCardModel:
    """Serve the A2A AgentCard for this agent (Hrz3 discovery, rule R4).

    Pure and identity-agnostic: the card advertises the agent's governed skills so a peer
    agent or the registry sees one capability surface. Built from ``agent.agent_card`` with
    no ADK import.
    """
    from ..agent.agent_card import build_agent_card

    return AgentCardModel.from_domain(build_agent_card(deps.get_settings()))


@app.get("/v1/personas")
def personas() -> list[dict[str, str]]:
    """List seeded dev personas for the local persona picker (empty outside local profile).

    Local mode runs with no IdP; the UI uses this to let a demo/test pick an identity
    (and thus exercise per-user authorization) via the ``X-Dev-Persona`` header. Secure
    profiles resolve identity from the IAP assertion, so this returns an empty list, and so
    does a run that never named a profile: the persona adapter refuses to construct there.
    """
    try:
        identity = deps.get_container().identity
    except IdentityError:
        return []
    lister = getattr(identity, "personas", None)
    if lister is None:
        return []
    return [dict(p) for p in lister()]


@app.post("/v1/brief")
def build_brief(body: BriefRequestModel, principal: CurrentPrincipal) -> dict:
    request = _to_request(body)
    try:
        brief = make_brief_service().build_brief(request, actor=principal.actor)
    except GuardrailBlockedError as exc:
        raise HTTPException(status_code=400, detail=f"guardrail blocked: {exc}") from exc
    except ResearchEmptyError as exc:
        raise HTTPException(status_code=404, detail=f"no grounding evidence: {exc}") from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return to_jsonable(brief)


@app.post("/v1/competitor-analysis")
def competitor_analysis(body: BriefRequestModel, principal: CurrentPrincipal) -> dict:
    request = _to_request(body)
    try:
        analysis = make_brief_service().competitor_analysis(request, actor=principal.actor)
    except GuardrailBlockedError as exc:
        raise HTTPException(status_code=400, detail=f"guardrail blocked: {exc}") from exc
    except ResearchEmptyError as exc:
        raise HTTPException(status_code=404, detail=f"no grounding evidence: {exc}") from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return to_jsonable(analysis)


def main() -> None:
    """Run the API locally with uvicorn."""
    import uvicorn

    uvicorn.run(
        "market_intelligence.api.app:app",
        # Fail-closed bind (shared hex-service-kit rule): the no-auth local
        # profile binds loopback unless MKT_INTEL_ALLOW_INSECURE_DEMO=1; secure profiles keep
        # 0.0.0.0 (container-local; ingress is fronted by the platform). Keyed on
        # ``bind_profile``, the OPPOSITE direction from CORS: here ``local`` is the restrictive
        # case, so a run that never named a profile must look like ``local`` and stay on loopback.
        host=resolve_bind_host(
            deps.get_settings().bind_profile,
            host_env="MKT_INTEL_API_HOST",
            insecure_demo_env="MKT_INTEL_ALLOW_INSECURE_DEMO",
        ),
        port=int(os.environ.get("PORT", "8100")),
        # Unset and set-but-empty collapse DELIBERATELY, closed in the same direction: no
        # auto-reload. Only a non-empty value turns the file watcher on, so an operator who
        # empties the variable gets the quieter behaviour, never the noisier one.
        reload=bool(read_env_setting("MKT_API_RELOAD").value),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
