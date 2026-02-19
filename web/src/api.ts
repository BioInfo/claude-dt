const BASE = "";

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Types

export interface Scores {
  context: number;
  tools: number;
  prompts: number;
  health: number;
  composite: number;
}

export interface Recommendation {
  category: string;
  priority: "high" | "medium" | "low";
  title: string;
  description: string;
  action: string;
  prompt: string;
  impact?: string;
  data?: Record<string, unknown>;
}

export interface SessionSummary {
  session_id: string;
  project_name: string | null;
  summary: string | null;
  user_message_count: number;
  tool_call_count: number;
  models: string;
  first_message_at: string | null;
  minutes: number | null;
  message_count: number;
  tool_error_count: number;
  total_tokens: number;
  subagent_count: number;
}

export interface SessionDetail {
  session_id: string;
  project_name: string | null;
  summary: string | null;
  message_count: number;
  user_message_count: number;
  assistant_msg_count: number;
  tool_call_count: number;
  tool_error_count: number;
  duration_seconds: number | null;
  models_used: string[];
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read: number;
  subagent_count: number;
  tool_breakdown: { tool: string; count: number; errors: number }[];
}

export interface TrendsData {
  period_days: number;
  current: number[];
  previous: number[];
  daily: [string, number, number, number, number][];
  current_models: [string, number][];
  previous_models: [string, number][];
}

export interface OverviewData {
  0: number; // sessions
  1: number; // messages
  2: number; // tool_calls
  3: number; // tool_errors
  4: number; // tokens
  5: number; // cache_reads
  6: number; // avg_turns
  7: number; // projects
}

export interface ReportData {
  period_days: number;
  overview: OverviewData;
  model_usage: [string, number, number, number][];
  top_projects: [string, number, number, number][];
  subagent_model_usage: [string, number, number, number, number, number][];
  context: {
    repeat_reads: unknown[];
    hotspot_files: [string, number, number][];
    cache_efficiency: [string, number, number, number, number][];
  };
  tools: {
    tool_frequency: [string, number, number, number][];
    subagent_stats: unknown[];
  };
  prompts: {
    patterns: [string, number, number][];
  };
  antipatterns: {
    type: string;
    severity: string;
    description: string;
    suggestion: string;
    session_id?: string;
  }[];
  scores: Scores;
  recommendations: Recommendation[];
}

export interface StatusData {
  tables: Record<string, number>;
  db_size_mb: number;
  last_ingest: string | null;
}

// API functions

export const api = {
  scores: (days = 7) => fetchJSON<Scores>(`/api/scores?days=${days}`),
  report: (days = 7) => fetchJSON<ReportData>(`/api/report?days=${days}`),
  recommend: (days = 7, category = "all") =>
    fetchJSON<Recommendation[]>(
      `/api/recommend?days=${days}&category=${category}`
    ),
  trends: (days = 14) => fetchJSON<TrendsData>(`/api/trends?days=${days}`),
  sessions: (limit = 50) =>
    fetchJSON<SessionSummary[]>(`/api/sessions?limit=${limit}`),
  session: (id: string) => fetchJSON<SessionDetail>(`/api/sessions/${id}`),
  health: (days = 30) =>
    fetchJSON<Record<string, unknown>>(`/api/health?days=${days}`),
  status: () => fetchJSON<StatusData>("/api/status"),
};
