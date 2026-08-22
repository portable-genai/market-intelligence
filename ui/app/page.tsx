"use client";

import { useEffect, useState } from "react";
import { BriefView } from "@/components/BriefView";
import { api, API_BASE, ApiError, setDevPersona } from "@/lib/api";
import type { Health, Market, MarketBrief, Persona, Vertical } from "@/lib/types";

const IS_EMBED = process.env.NEXT_PUBLIC_EMBED === "1";

const MARKETS: { value: Market; label: string }[] = [
  { value: "JP", label: "Japan (asia-northeast1)" },
  { value: "AU", label: "Australia (australia-southeast1)" },
  { value: "SG", label: "Singapore (asia-southeast1)" },
];
const VERTICALS: { value: Vertical; label: string }[] = [
  { value: "banking", label: "Banking" },
  { value: "online_retail", label: "Online retail" },
];

export default function Page() {
  const [topic, setTopic] = useState("savings and account fees");
  const [market, setMarket] = useState<Market>("SG");
  const [vertical, setVertical] = useState<Vertical>("banking");
  const [competitors, setCompetitors] = useState("");
  const [brief, setBrief] = useState<MarketBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const status = await api.healthz();
      if (cancelled) return;
      setHealth(status);
      // The persona picker is a local-profile-only convenience; secure profiles resolve
      // identity from the IAP assertion, so /v1/personas is empty there.
      if (status?.profile !== "local") return;
      const list = await api.listPersonas();
      if (cancelled || list.length === 0) return;
      setPersonas(list);
      setSelectedPersona(list[0].id);
      setDevPersona(list[0].id);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onPersonaChange(id: string) {
    setSelectedPersona(id);
    setDevPersona(id);
  }

  async function onBuild() {
    setLoading(true);
    setError(null);
    setBrief(null);
    try {
      const result = await api.buildBrief({
        topic,
        market,
        vertical,
        competitors: competitors
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      });
      setBrief(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-6xl gap-6 p-6">
      <aside className="w-80 shrink-0">
        {/* EMBED mode: the host page owns the chrome, so drop our own title block. */}
        {!IS_EMBED ? (
          <>
            <h1 className="text-base font-semibold">Mkt1 Market Intelligence</h1>
            <p className="mb-4 text-xs text-ink-500">
              Cited market briefs and competitor analysis, generic across banking and online
              retail and the JP/AU/SG markets.
            </p>
          </>
        ) : null}

        {personas.length > 0 ? (
          <div className="mb-3 rounded-xl border border-ink-200 bg-white p-4 shadow-panel">
            <label className="mb-1 block text-xs font-semibold text-ink-600">
              Demo identity
            </label>
            <select
              className="w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
              value={selectedPersona}
              onChange={(e) => onPersonaChange(e.target.value)}
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.subject} · {p.tenant}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-panel">
          <label className="mb-1 block text-xs font-semibold text-ink-600">Topic</label>
          <input
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />

          <label className="mb-1 block text-xs font-semibold text-ink-600">Market</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={market}
            onChange={(e) => setMarket(e.target.value as Market)}
          >
            {MARKETS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>

          <label className="mb-1 block text-xs font-semibold text-ink-600">Vertical</label>
          <select
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={vertical}
            onChange={(e) => setVertical(e.target.value as Vertical)}
          >
            {VERTICALS.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>

          <label className="mb-1 block text-xs font-semibold text-ink-600">
            Competitors (comma-separated, optional)
          </label>
          <input
            className="mb-3 w-full rounded-md border border-ink-200 px-2.5 py-1.5 text-sm"
            value={competitors}
            onChange={(e) => setCompetitors(e.target.value)}
            placeholder="e.g. Acme Bank SG, Merlion"
          />

          <button
            onClick={onBuild}
            disabled={loading || !topic.trim()}
            className="w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {loading ? "Building…" : "Build cited brief"}
          </button>
        </div>

        <div className="mt-3 rounded-xl border border-ink-200 bg-white p-3 text-xs text-ink-500 shadow-panel">
          <div>
            API <span className="font-mono">{API_BASE}</span>
          </div>
          {health ? (
            <div className="mt-1">
              profile <b className="text-ink-700">{health.profile}</b> · status{" "}
              <b className="text-ink-700">{health.status}</b>
            </div>
          ) : (
            <div className="mt-1 text-amber-700">backend not reachable (start the API)</div>
          )}
        </div>
      </aside>

      <section className="min-w-0 flex-1">
        {error ? (
          <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        {!brief && !error ? (
          <div className="rounded-xl border border-dashed border-ink-200 bg-white p-10 text-center text-sm text-ink-400">
            Configure a topic, market and vertical, then build a cited brief.
          </div>
        ) : null}
        {brief ? <BriefView brief={brief} /> : null}
      </section>
    </main>
  );
}
