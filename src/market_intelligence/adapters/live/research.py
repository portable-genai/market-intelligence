"""Live grounded-research adapter (ResearchPort): Gemini with Google Search, on a laptop.

The research itself is the managed adapter's, unchanged:
:class:`~market_intelligence.adapters.gcp.deep_research.GeminiDeepResearchAdapter` builds the
prompt, calls Gemini with the ``google_search`` tool in the market's residency region and maps
the structured answer onto cited sources, claims and competitor moves. What this adapter adds
is the laptop's failure mode. A deployment has its credentials provisioned; a laptop often
does not, and a demo that 500s with a stack trace from inside ``google.auth`` tells nobody
what to do. So every way the backend can be unreachable (grounding switched off, the client
library not installed, no project named, no or expired credentials, credentials refused) is
turned into :class:`ResearchUnavailableError` with the remedy in its message.

Nothing here imports a Google SDK at module level, and nothing is checked at construction:
the app starts without credentials, and only a research request finds out.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from ...config import Settings
from ...domain.errors import ResearchUnavailableError
from ...domain.models import CompetitorMove, Market, ResearchQuery, ResearchResult, Vertical
from ..gcp.deep_research import GeminiDeepResearchAdapter

_T = TypeVar("_T")

#: The placeholder ``config/settings.yaml`` writes when ``GOOGLE_CLOUD_PROJECT`` is unset.
#: Read off the dataclass rather than restated, so the two cannot disagree.
_PLACEHOLDER_PROJECT: str = str(Settings.__dataclass_fields__["project_id"].default)

#: HTTP statuses from the Gemini API that mean "these credentials may not call this", as
#: opposed to a bad request: the backend is unavailable to this operator, not broken.
_REFUSED_STATUSES: frozenset[int] = frozenset({401, 403})

_ADC_REMEDY = "run `gcloud auth application-default login`"


def _raised_from(exc: BaseException, module_prefix: str) -> bool:
    """Whether ``exc`` is an instance of a class defined under ``module_prefix``.

    Matched by the defining module across the MRO rather than by importing the SDK's
    exception types, so the check works (and is testable) with no Google SDK installed.
    """
    return any(klass.__module__.startswith(module_prefix) for klass in type(exc).__mro__)


class LiveGroundedResearchAdapter:
    """Gemini grounded research that reports itself unavailable instead of crashing."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._delegate = GeminiDeepResearchAdapter(settings)

    # ------------------------------------------------------------------ #
    # ResearchPort
    # ------------------------------------------------------------------ #
    def research(self, query: ResearchQuery) -> ResearchResult:
        return self._call(lambda: self._delegate.research(query))

    def competitor_snapshots(
        self, market: Market, vertical: Vertical, competitors: tuple[str, ...]
    ) -> tuple[tuple[CompetitorMove, ...], tuple[CompetitorMove, ...]]:
        return self._call(
            lambda: self._delegate.competitor_snapshots(market, vertical, competitors)
        )

    # ------------------------------------------------------------------ #
    # Availability
    # ------------------------------------------------------------------ #
    def _call(self, fn: Callable[[], _T]) -> _T:
        self._require_configured()
        try:
            return fn()
        except ImportError as exc:
            raise ResearchUnavailableError(
                "grounded research needs the Gemini client, which is not installed: "
                "pip install -e '.[live]'"
            ) from exc
        except Exception as exc:
            if _raised_from(exc, "google.auth"):
                raise ResearchUnavailableError(
                    f"no usable Google credentials for Gemini ({type(exc).__name__}: {exc}); "
                    f"{_ADC_REMEDY}"
                ) from exc
            if _raised_from(exc, "google.genai") and getattr(exc, "code", None) in (
                _REFUSED_STATUSES
            ):
                raise ResearchUnavailableError(
                    f"Gemini refused the credentials for project "
                    f"{self._settings.project_id!r} ({exc}); check the project and "
                    f"{_ADC_REMEDY}"
                ) from exc
            raise

    def _require_configured(self) -> None:
        if not self._settings.grounding_enabled:
            raise ResearchUnavailableError(
                "grounded research is switched off (MKT_GROUNDING_ENABLED=false); the live "
                "profile's research is Google Search grounding, so turn it on to use it"
            )
        project = self._settings.project_id.strip()
        if not project or project == _PLACEHOLDER_PROJECT:
            raise ResearchUnavailableError(
                "grounded research calls Gemini on Vertex AI and no project is named: "
                f"set GOOGLE_CLOUD_PROJECT and {_ADC_REMEDY}"
            )
