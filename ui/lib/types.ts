/**
 * Domain shapes mirrored from the D1 FastAPI backend (the JSON shape of a cited
 * MarketBrief / CompetitorAnalysis produced by `to_jsonable`).
 */

export type Market = "JP" | "AU" | "SG";
export type Vertical = "banking" | "online_retail";

export interface Citation {
  source_id: string;
  source_type: string;
  title: string;
  url?: string;
  page?: number | null;
  published_date?: string | null;
  snippet?: string;
  score?: number | null;
}

export interface Claim {
  text: string;
  citations: Citation[];
  subject?: string;
  confidence?: number;
}

export interface TrendScore {
  topic: string;
  score: number;
  direction: string;
  mentions: number;
  distinct_sources: number;
  rationale?: string;
}

export interface MoveDelta {
  id: string;
  competitor: string;
  kind: string;
  status: string;
  summary: string;
  changed_fields: string[];
  before: Record<string, string>;
  after: Record<string, string>;
  severity: string;
  citations: Citation[];
}

export interface WhereToPlayOption {
  id: string;
  title: string;
  attractiveness: number;
  right_to_win: number;
  score: number;
  rationale?: string;
}

export interface SwotItem {
  kind: string;
  statement: string;
  weight?: number;
  citations: Citation[];
}

export interface CompetitorAnalysis {
  market: Market;
  vertical: Vertical;
  competitors: string[];
  diff: { market: Market; vertical: Vertical; deltas: MoveDelta[] };
  swot: {
    market: Market;
    vertical: Vertical;
    items: SwotItem[];
    options: WhereToPlayOption[];
  };
  narrative?: string;
  citations: Citation[];
  requires_human_review: boolean;
}

export interface ResearchSource {
  id: string;
  title: string;
  url: string;
  publisher?: string;
  published_date?: string | null;
}

export interface MarketBrief {
  id: string;
  topic: string;
  market: Market;
  vertical: Vertical;
  summary: string;
  key_claims: Claim[];
  trends: TrendScore[];
  competitor_analysis: CompetitorAnalysis | null;
  sources: ResearchSource[];
  citations: Citation[];
  requires_human_review: boolean;
}

export interface Health {
  status: string;
  profile: string;
  market: string;
  vertical: string;
}

// A seeded dev persona for the local-profile persona picker (GET /v1/personas).
export interface Persona {
  id: string;
  subject: string;
  tenant: string;
  principals: string;
}
