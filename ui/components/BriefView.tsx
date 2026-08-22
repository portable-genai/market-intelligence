import type { MarketBrief } from "@/lib/types";
import { CitationList } from "./CitationList";

const MARKET_LABEL: Record<string, string> = {
  JP: "Japan",
  AU: "Australia",
  SG: "Singapore",
};
const VERTICAL_LABEL: Record<string, string> = {
  banking: "Banking",
  online_retail: "Online retail",
};
const SEV_COLOR: Record<string, string> = {
  low: "bg-ink-100 text-ink-600",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-700",
  critical: "bg-red-100 text-red-700",
};

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-4 rounded-xl border border-ink-200 bg-white shadow-panel">
      <h2 className="border-b border-ink-100 px-4 py-2.5 text-[13px] font-semibold text-ink-800">
        {title}
      </h2>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Bar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-28 overflow-hidden rounded-md border border-ink-200 bg-ink-100">
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-brand-600"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink-500">{pct}%</span>
    </div>
  );
}

export function BriefView({ brief }: { brief: MarketBrief }) {
  const ca = brief.competitor_analysis;
  return (
    <div>
      <h1 className="text-lg font-semibold">Market brief — {brief.topic}</h1>
      <p className="mb-4 text-[13px] text-ink-500">
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {MARKET_LABEL[brief.market] ?? brief.market}
        </span>
        <span className="mr-1.5 inline-block rounded-full border border-brand-100 bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700">
          {VERTICAL_LABEL[brief.vertical] ?? brief.vertical}
        </span>
        id <b className="text-ink-800">{brief.id}</b>
      </p>

      {brief.requires_human_review ? (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          HUMAN REVIEW REQUIRED — maker-checker gate. Do not act on this brief until a
          qualified strategist signs off.
        </div>
      ) : null}

      <Panel title="Summary">
        <p className="leading-relaxed">{brief.summary}</p>
      </Panel>

      <Panel title="Key claims (cited)">
        {brief.key_claims.length === 0 ? (
          <div className="text-xs text-ink-400">none</div>
        ) : (
          brief.key_claims.map((claim, i) => (
            <div key={i} className="border-b border-ink-100 py-2 last:border-0">
              <div>{claim.text}</div>
              <CitationList citations={claim.citations} />
            </div>
          ))
        )}
      </Panel>

      <Panel title="Trends">
        {brief.trends.length === 0 ? (
          <div className="text-xs text-ink-400">none</div>
        ) : (
          brief.trends.map((t, i) => (
            <div key={i} className="flex items-center gap-3 border-b border-ink-100 py-2 last:border-0">
              <div className="flex-1">
                {t.topic}{" "}
                <span className="text-xs text-ink-400">
                  · {t.direction} · {t.mentions} mention(s), {t.distinct_sources} source(s)
                </span>
              </div>
              <Bar value={t.score} />
            </div>
          ))
        )}
      </Panel>

      {ca ? (
        <>
          <Panel title="Competitor moves (deterministic diff)">
            {ca.diff.deltas.filter((d) => d.status !== "unchanged").length === 0 ? (
              <div className="text-xs text-ink-400">no material moves</div>
            ) : (
              ca.diff.deltas
                .filter((d) => d.status !== "unchanged")
                .map((d, i) => (
                  <div key={i} className="flex gap-3 border-b border-ink-100 py-2 last:border-0">
                    <span
                      className={`h-fit rounded px-1.5 text-[11px] font-bold ${
                        SEV_COLOR[d.severity] ?? SEV_COLOR.medium
                      }`}
                    >
                      {d.severity}
                    </span>
                    <div className="flex-1">
                      <b>{d.competitor}</b>{" "}
                      <span className="text-xs text-ink-400">{d.status}</span> — {d.summary}
                      {d.changed_fields.length > 0 ? (
                        <div className="text-xs text-ink-400">
                          changed: {d.changed_fields.join(", ")}{" "}
                          {JSON.stringify(d.before)} → {JSON.stringify(d.after)}
                        </div>
                      ) : null}
                      <CitationList citations={d.citations} />
                    </div>
                  </div>
                ))
            )}
          </Panel>

          <Panel title="Where to play (ranked, deterministic)">
            {ca.swot.options.length === 0 ? (
              <div className="text-xs text-ink-400">none</div>
            ) : (
              ca.swot.options.map((o, i) => (
                <div key={i} className="flex items-center gap-3 border-b border-ink-100 py-2 last:border-0">
                  <div className="flex-1">
                    {o.title}{" "}
                    <span className="text-xs text-ink-400">
                      · attractiveness {o.attractiveness}, right-to-win {o.right_to_win}
                    </span>
                  </div>
                  <Bar value={o.score} />
                </div>
              ))
            )}
          </Panel>
        </>
      ) : null}

      <Panel title="Sources">
        {brief.sources.length === 0 ? (
          <div className="text-xs text-ink-400">none</div>
        ) : (
          brief.sources.map((s, i) => (
            <div key={i} className="border-b border-ink-100 py-2 last:border-0">
              <b>{s.id}</b> {s.title}{" "}
              <span className="text-xs text-ink-400">({s.publisher})</span>
            </div>
          ))
        )}
      </Panel>
    </div>
  );
}
