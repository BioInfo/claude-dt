import { useEffect, useState } from "react";
import { api } from "../api";
import type { Recommendation } from "../api";
import RecommendationCard from "../components/RecommendationCard";
import InfoBox from "../components/InfoBox";
import Pagination from "../components/Pagination";

const categories = ["all", "context", "session", "model", "prompt", "tools"];
const priorities = ["all", "high", "medium", "low"] as const;

const categoryDescriptions: Record<string, string> = {
  all: "All categories",
  context: "File re-reads, cache efficiency, CLAUDE.md improvements",
  session: "Session length, edit retries, workflow hygiene",
  model: "Subagent model routing optimization",
  prompt: "Prompt clarity, specificity, and action verbs",
  tools: "Tool error rates and failure patterns",
};

export default function Recommendations() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [category, setCategory] = useState("all");
  const [priority, setPriority] = useState<string>("all");
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 6;

  useEffect(() => {
    setLoading(true);
    api
      .recommend(days, category)
      .then(setRecs)
      .finally(() => setLoading(false));
  }, [days, category]);

  // Reset page on filter change
  useEffect(() => setPage(1), [priority, category, days]);

  const filtered = priority === "all" ? recs : recs.filter((r) => r.priority === priority);
  const high = recs.filter((r) => r.priority === "high").length;
  const med = recs.filter((r) => r.priority === "medium").length;
  const low = recs.filter((r) => r.priority === "low").length;
  const totalPages = Math.ceil(filtered.length / pageSize);
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Recommendations</h2>
        <p className="text-sm text-gray-500 mt-1">
          Actionable suggestions to improve your Claude Code workflow, each with a ready-to-paste prompt.
        </p>
      </div>

      <InfoBox variant="tip">
        Each recommendation includes a prompt you can copy and paste directly into Claude Code.
        Start with <strong className="text-gray-300">high priority</strong> items for the biggest impact.
      </InfoBox>

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-2 border border-gray-700 focus:border-indigo-500 focus:outline-none"
        >
          {[7, 14, 30].map((d) => (
            <option key={d} value={d}>
              Last {d} days
            </option>
          ))}
        </select>

        {/* Category filter */}
        <div className="flex gap-1">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              title={categoryDescriptions[c]}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                category === c
                  ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                  : "text-gray-400 hover:bg-gray-800 border border-transparent"
              }`}
            >
              {c}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-gray-700" />

        {/* Priority filter */}
        <div className="flex gap-1">
          {priorities.map((p) => {
            const colors: Record<string, string> = {
              all: "bg-gray-500/20 text-gray-300 border-gray-500/30",
              high: "bg-red-500/20 text-red-300 border-red-500/30",
              medium: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
              low: "bg-blue-500/20 text-blue-300 border-blue-500/30",
            };
            const counts: Record<string, number> = {
              all: recs.length,
              high,
              medium: med,
              low,
            };
            return (
              <button
                key={p}
                onClick={() => setPriority(p)}
                className={`text-xs px-2.5 py-1.5 rounded-lg font-medium transition-colors border ${
                  priority === p ? colors[p] : "text-gray-500 border-transparent hover:bg-gray-800"
                }`}
              >
                {p} ({counts[p]})
              </button>
            );
          })}
        </div>
      </div>

      {/* Summary bar */}
      <div className="flex gap-4 text-sm items-center">
        <span className="text-gray-400">{filtered.length} recommendations</span>
        {high > 0 && (
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-400" />
            <span className="text-red-400">{high} high</span>
          </span>
        )}
        {med > 0 && (
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-yellow-400" />
            <span className="text-yellow-400">{med} medium</span>
          </span>
        )}
        {low > 0 && (
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-blue-400" />
            <span className="text-blue-400">{low} low</span>
          </span>
        )}
      </div>

      {loading ? (
        <div className="text-gray-500 animate-pulse">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-8 text-center">
          <div className="text-2xl mb-2">{"\u2705"}</div>
          <div className="text-emerald-400 font-medium">No recommendations. Looking good.</div>
          <div className="text-xs text-gray-500 mt-1">Your workflow is efficient for this period.</div>
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {paged.map((r, i) => (
              <RecommendationCard key={i} rec={r} />
            ))}
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            totalItems={filtered.length}
            pageSize={pageSize}
          />
        </>
      )}
    </div>
  );
}
