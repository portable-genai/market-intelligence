"""``mkt-intel`` — the Typer CLI for the D1 Market Intelligence system.

A thin presentation layer over the domain services. It owns no business logic: every
command builds the wiring from :func:`market_intelligence.api.deps.make_brief_service`,
invokes one domain service, and pretty-prints the cited result.

Design constraints honoured here:

* **Import-safe.** Importing this module (the ``[project.scripts]`` entry point, or
  ``--help``) must never pull in FastAPI, uvicorn or the Google Cloud SDKs. They are
  imported lazily inside command bodies, so the on-prem / local / test profile (which
  installs no Google Cloud SDK) can still load the CLI.
* **Profile-aware.** ``MKT_INTEL_PROFILE`` selects the adapter stack. The ``onprem``
  profile binds placeholder adapters that raise ``NotImplementedError``; the CLI then fails
  clearly (exit code 2) naming the migration target.
* **Citations are first-class.** Every artifact prints with source-and-page provenance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..domain.models import Citation, MarketBrief

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "D1 Market Intelligence and Competitor Analysis — cited market briefs and "
        "competitor analysis from grounded deep research and an internal corpus, generic "
        "across banking and online retail and the JP/AU/SG markets."
    ),
)

_PROFILE_EXIT = 2
_RUNTIME_EXIT = 1
_CLI_ACTOR = "cli:operator"


def _fail(message: str, *, code: int = _RUNTIME_EXIT) -> Any:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _run(action: str, fn: Any) -> Any:
    """Execute ``fn`` and translate adapter failures into clean CLI errors."""
    from ..config import Settings

    profile = Settings.load().profile
    try:
        return fn()
    except NotImplementedError as exc:
        detail = str(exc) or "method not implemented"
        _fail(
            f"'{action}' is not available under profile '{profile}'. "
            f"This profile uses placeholder adapters (migration target): {detail}",
            code=_PROFILE_EXIT,
        )
    except KeyError as exc:
        _fail(f"'{action}' has no adapter wired for profile '{profile}': {exc}", code=_PROFILE_EXIT)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks to operators
        _fail(f"'{action}' failed: {type(exc).__name__}: {exc}", code=_RUNTIME_EXIT)


# --------------------------------------------------------------------------- #
# Pretty-printing
# --------------------------------------------------------------------------- #
def _fmt_citation(c: Citation) -> str:
    page = f" p.{c.page}" if c.page is not None else ""
    st = c.source_type.value if hasattr(c.source_type, "value") else str(c.source_type)
    url = f" — {c.url}" if c.url else ""
    return f"[{c.source_id}, {st}{page}]{url}"


def _echo_citations(citations: tuple[Citation, ...], indent: str = "  ") -> None:
    if not citations:
        typer.secho(f"{indent}(no citations)", fg=typer.colors.YELLOW)
        return
    typer.secho(f"{indent}Citations:", bold=True)
    for c in citations:
        typer.echo(f"{indent}  - {_fmt_citation(c)}")


def _echo_review_banner(requires_review: bool) -> None:
    if requires_review:
        typer.secho(
            "  [HUMAN REVIEW REQUIRED] maker-checker gate — do not act on this brief until "
            "a qualified strategist signs off.",
            fg=typer.colors.YELLOW,
            bold=True,
        )


def _echo_brief(brief: MarketBrief) -> None:
    typer.secho(f"\nMARKET BRIEF: {brief.topic}", bold=True)
    typer.echo(f"  id        : {brief.id}")
    typer.echo(f"  market    : {brief.market.value}")
    typer.echo(f"  vertical  : {brief.vertical.value}")
    _echo_review_banner(brief.requires_human_review)

    typer.secho("\n  Summary:", bold=True)
    typer.echo(f"    {brief.summary}")

    if brief.trends:
        typer.secho("\n  Trends:", bold=True)
        for t in brief.trends:
            typer.echo(
                f"    - {t.topic}: {t.direction.value} (score {t.score:.2f}, "
                f"{t.mentions} mention(s), {t.distinct_sources} source(s))"
            )

    ca = brief.competitor_analysis
    if ca is not None:
        typer.secho("\n  Competitor moves (diff):", bold=True)
        for d in ca.diff.material_deltas:
            typer.echo(f"    - [{d.severity.value}] {d.competitor}: {d.status.value} — {d.summary}")
            if d.changed_fields:
                fields = ", ".join(d.changed_fields)
                typer.echo(f"        changed: {fields} {d.before} -> {d.after}")
        typer.secho("\n  Where to play (ranked):", bold=True)
        for o in ca.swot.options:
            typer.echo(
                f"    - {o.title}: score {o.score:.2f} "
                f"(attractiveness {o.attractiveness:.2f}, right-to-win {o.right_to_win:.2f})"
            )

    typer.secho("\n  Sources:", bold=True)
    for s in brief.sources:
        typer.echo(f"    - {s.id}: {s.title} ({s.publisher})")

    typer.secho("", nl=True)
    _echo_citations(brief.citations)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def brief(
    topic: str = typer.Argument(..., help="The topic to brief on, e.g. 'savings rates'."),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
    competitor: list[str] = typer.Option(  # noqa: B008 - Typer's documented Option-in-default idiom
        None, "--competitor", "-c", help="Restrict to these competitor names (repeatable)."
    ),
) -> None:
    """Build a cited market brief for a topic in a market and vertical."""
    from ..api.deps import make_brief_service
    from ..domain.models import BriefRequest, Market, Vertical

    def go() -> MarketBrief:
        request = BriefRequest(
            topic=topic,
            market=Market(market),
            vertical=Vertical(vertical),
            competitors=tuple(competitor or ()),
        )
        return make_brief_service().build_brief(request, actor=_CLI_ACTOR)

    result = _run("brief", go)
    _echo_brief(result)


@app.command("competitor-analysis")
def competitor_analysis(
    topic: str = typer.Argument(..., help="The topic / area to analyse."),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
) -> None:
    """Run a deterministic competitor-move diff + SWOT / where-to-play synthesis."""
    from ..api.deps import make_brief_service
    from ..domain.models import BriefRequest, Market, Vertical

    def go() -> Any:
        request = BriefRequest(topic=topic, market=Market(market), vertical=Vertical(vertical))
        return make_brief_service().competitor_analysis(request, actor=_CLI_ACTOR)

    analysis = _run("competitor-analysis", go)
    header = f"\nCOMPETITOR ANALYSIS: {analysis.market.value}/{analysis.vertical.value}"
    typer.secho(header, bold=True)
    _echo_review_banner(analysis.requires_human_review)
    typer.echo(f"\n  {analysis.narrative}")
    typer.secho("\n  SWOT:", bold=True)
    for item in analysis.swot.items:
        typer.echo(f"    - [{item.kind.value}] {item.statement}")
    _echo_citations(analysis.citations)


if __name__ == "__main__":  # pragma: no cover
    app()
