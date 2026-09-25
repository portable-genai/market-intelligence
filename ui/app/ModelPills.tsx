"use client";

import { useEffect, useState } from "react";

import { API_BASE } from "@/lib/api";

import { watchAnswers } from "../lib/answer-provenance.mjs";

/**
 * Two small pills at the top right of every page: the model that ANSWERED, and `Search` when
 * the answer used an online search tool (owner decision, 2026-09-23; they replace the
 * full-width provenance banner).
 *
 * The pill names what answered, not what configuration would call. Until an answer arrives it
 * shows the service's configured `generator_model` from `/healthz`, dimmed, with where the
 * runtime sits in its title. From then on it shows the `X-Answered-By` header of the console's
 * last answering response, solid, and `Search` appears only while that response carried
 * `X-Search-Used: true` (grounded research with Google Search). Both headers are emitted by the
 * service (`install_answer_provenance` in `api/app.py`), which also exposes them to this
 * console (`Access-Control-Expose-Headers`) when it runs standalone on another origin.
 *
 * **Every value comes from the service**, and nothing here infers one. A UI that read its own
 * runtime from `window.location` would be right until the deployment served through a proxy,
 * and wrong silently after that.
 *
 * This console has no same-origin route handler: it calls its backend directly on `API_BASE`,
 * resolved once in `lib/api` from NEXT_PUBLIC_API_BASE. Health and the answer watcher use that
 * same base, because a pill that named a transport its console does not use could only fail by
 * disappearing, which nobody notices.
 */

interface Configured {
  model: string;
  where: string;
}

interface Answer {
  model: string;
  search: boolean;
}

/**
 * Renders once the service has answered `/healthz`, and nothing before that.
 *
 * The null-until-known state is deliberate: a pill defaulting to a model or a runtime while the
 * fetch is in flight would state a falsehood on some page load, and a failed health call renders
 * nothing for the same reason. The page's own error surface owns the failure.
 */
export function ModelPills() {
  const [configured, setConfigured] = useState<Configured | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);

  useEffect(() => {
    let live = true;
    const stop = watchAnswers(window, API_BASE, (next) => {
      if (live) setAnswer(next);
    });
    fetch(`${API_BASE}/healthz`, { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!live || !body) return;
        setConfigured({
          model: String(body.generator_model ?? ""),
          where: body.runtime === "gcp" ? "running on GCP" : "running locally",
        });
      })
      .catch(() => undefined);
    return () => {
      live = false;
      stop();
    };
  }, []);

  if (!configured) return null;
  return (
    <div className="model-pills" data-testid="model-pills">
      {answer ? (
        <span className="model-pill answered" data-state="answered" title="answered the last request">
          {answer.model}
        </span>
      ) : (
        <span className="model-pill configured" data-state="configured" title={configured.where}>
          {configured.model}
        </span>
      )}
      {answer?.search ? (
        <span className="model-pill search" title="the last answer used an online search tool">
          Search
        </span>
      ) : null}
    </div>
  );
}
