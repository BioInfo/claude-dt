import { useState } from "react";
import Pagination from "./Pagination";

interface Antipattern {
  type: string;
  severity: string;
  description: string;
  suggestion: string;
  session_id?: string;
}

interface Props {
  items: Antipattern[];
  pageSize?: number;
}

const severityStyles: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/20",
  warning: "bg-yellow-500/15 text-yellow-400 border-yellow-500/20",
  info: "bg-gray-500/15 text-gray-400 border-gray-500/20",
};

const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };

export default function AntipatternList({ items, pageSize = 10 }: Props) {
  const [page, setPage] = useState(1);
  const [filterSeverity, setFilterSeverity] = useState<string>("all");

  if (!items.length) {
    return (
      <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-4 text-center">
        <span className="text-emerald-400 text-sm font-medium">
          No anti-patterns detected. Nice work.
        </span>
      </div>
    );
  }

  const sorted = [...items].sort(
    (a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3)
  );
  const filtered = filterSeverity === "all"
    ? sorted
    : sorted.filter((a) => a.severity === filterSeverity);

  const totalPages = Math.ceil(filtered.length / pageSize);
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize);

  const counts = {
    critical: items.filter((a) => a.severity === "critical").length,
    warning: items.filter((a) => a.severity === "warning").length,
    info: items.filter((a) => a.severity === "info").length,
  };

  return (
    <div>
      {/* Severity filter */}
      <div className="flex items-center gap-2 mb-3">
        {["all", "critical", "warning", "info"].map((s) => {
          const count = s === "all" ? items.length : counts[s as keyof typeof counts];
          return (
            <button
              key={s}
              onClick={() => { setFilterSeverity(s); setPage(1); }}
              className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-colors border ${
                filterSeverity === s
                  ? s === "all"
                    ? "bg-gray-500/20 text-gray-300 border-gray-500/30"
                    : severityStyles[s]
                  : "text-gray-500 border-transparent hover:bg-gray-800"
              }`}
            >
              {s} ({count})
            </button>
          );
        })}
      </div>

      <div className="space-y-2">
        {paged.map((ap, i) => (
          <div
            key={i}
            className="bg-gray-950 rounded-lg p-3.5 border border-gray-800 hover:border-gray-700 transition-colors"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded border ${severityStyles[ap.severity] || severityStyles.info}`}
              >
                {ap.severity.toUpperCase()}
              </span>
              <span className="text-xs text-gray-500 font-mono">{ap.type}</span>
              {ap.session_id && (
                <span className="text-xs text-gray-600 font-mono ml-auto">
                  {ap.session_id.slice(0, 8)}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-300">{ap.description}</p>
            <p className="text-xs text-gray-500 mt-1.5 italic">{ap.suggestion}</p>
          </div>
        ))}
      </div>

      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        totalItems={filtered.length}
        pageSize={pageSize}
      />
    </div>
  );
}
