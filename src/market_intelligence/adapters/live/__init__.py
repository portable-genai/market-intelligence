"""``live`` profile adapters: the laptop run, with real grounded research from Gemini.

An online search tool is this use case's core, so under ``live`` the research port runs
Gemini grounded with Google Search and the ``llm`` port narrates with Gemini (owner rule,
2026-09-23). Every other port reuses the SDK-free local adapter, so identity, the internal
corpus, audit and review routing stay on the machine with the laptop posture ``local`` has.

The profile needs the ``[live]`` extra (``google-genai``), ``GOOGLE_CLOUD_PROJECT`` and
Application Default Credentials. Without them the app still starts: the research leg
refuses each request with :class:`~market_intelligence.domain.errors.ResearchUnavailableError`
naming what is missing, which the API answers as a 503.
"""
