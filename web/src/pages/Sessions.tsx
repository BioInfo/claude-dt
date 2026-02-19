import { useEffect, useState, useMemo } from "react";
import { api } from "../api";
import type { SessionSummary, SessionDetail } from "../api";
import SortableTable from "../components/SortableTable";
import InfoBox from "../components/InfoBox";
import {
  Search,
  Timer,
  MessageSquare,
  Wrench,
  Target,
  HardDrive,
  Bot,
  Brain,
} from "lucide-react";

export default function Sessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");

  useEffect(() => {
    api
      .sessions(500)
      .then(setSessions)
      .finally(() => setLoading(false));
  }, []);

  const projects = useMemo(() => {
    const set = new Set(sessions.map((s) => s.project_name || "unknown"));
    return ["all", ...Array.from(set).sort()];
  }, [sessions]);

  const filtered = useMemo(() => {
    let result = sessions;
    if (projectFilter !== "all") {
      result = result.filter((s) => s.project_name === projectFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (s) =>
          (s.summary || "").toLowerCase().includes(q) ||
          (s.project_name || "").toLowerCase().includes(q) ||
          s.session_id.toLowerCase().includes(q)
      );
    }
    return result;
  }, [sessions, projectFilter, search]);

  const handleSelect = (row: Record<string, unknown>) => {
    api.session(row.session_id as string).then(setSelected);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 animate-pulse text-lg">Loading sessions...</div>
      </div>
    );
  }

  const columns = [
    {
      key: "session_id",
      label: "ID",
      render: (v: unknown) => (
        <span className="font-mono text-xs text-indigo-400">
          {String(v).slice(0, 8)}
        </span>
      ),
    },
    {
      key: "project_name",
      label: "Project",
      render: (v: unknown) => (
        <span className="text-gray-300 truncate block max-w-[140px]">
          {String(v || "?")}
        </span>
      ),
    },
    {
      key: "summary",
      label: "Summary",
      sortable: false,
      render: (v: unknown) => (
        <span className="text-gray-400 truncate block max-w-[280px]" title={String(v || "")}>
          {String(v || "")}
        </span>
      ),
    },
    { key: "user_message_count", label: "Turns", align: "right" as const },
    {
      key: "tool_call_count",
      label: "Tools",
      align: "right" as const,
      render: (v: unknown, row: Record<string, unknown>) => {
        const errors = Number(row.tool_error_count || 0);
        return (
          <span>
            {String(v)}
            {errors > 0 && (
              <span className="text-red-400 text-xs ml-1">
                ({errors}e)
              </span>
            )}
          </span>
        );
      },
    },
    {
      key: "total_tokens",
      label: "Tokens",
      align: "right" as const,
      render: (v: unknown) => {
        const n = v as number;
        return n ? `${(n / 1000).toFixed(0)}k` : "";
      },
    },
    {
      key: "first_message_at",
      label: "When",
      render: (v: unknown) => (
        <span className="text-xs text-gray-500">
          {v ? String(v).slice(0, 16).replace("T", " ") : "?"}
        </span>
      ),
    },
    {
      key: "minutes",
      label: "Duration",
      align: "right" as const,
      render: (v: unknown) => (
        <span className="text-gray-400">{v != null ? `${v}m` : ""}</span>
      ),
    },
  ];

  const detailItems: { Icon: typeof Timer; label: string; value: string }[] = selected
    ? [
        {
          Icon: Timer,
          label: "Duration",
          value: `${((selected.duration_seconds || 0) / 60).toFixed(1)} min`,
        },
        {
          Icon: MessageSquare,
          label: "Messages",
          value: `${selected.message_count} (${selected.user_message_count}u / ${selected.assistant_msg_count}a)`,
        },
        {
          Icon: Wrench,
          label: "Tools",
          value: `${selected.tool_call_count} (${selected.tool_error_count} errors)`,
        },
        {
          Icon: Target,
          label: "Tokens",
          value: (
            (selected.total_input_tokens || 0) +
            (selected.total_output_tokens || 0)
          ).toLocaleString(),
        },
        {
          Icon: HardDrive,
          label: "Cache Reads",
          value: (selected.total_cache_read || 0).toLocaleString(),
        },
        {
          Icon: Bot,
          label: "Subagents",
          value: String(selected.subagent_count),
        },
        {
          Icon: Brain,
          label: "Models",
          value: (selected.models_used || [])
            .join(", ")
            .replace(/claude-/g, "")
            .slice(0, 50),
        },
      ]
    : [];

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Sessions</h2>
        <p className="text-sm text-gray-500 mt-1">
          Browse all Claude Code sessions. Click a row to see detailed breakdown.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <input
            type="text"
            placeholder="Search sessions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-gray-800 text-gray-300 text-sm rounded-lg pl-9 pr-3 py-2 border border-gray-700 focus:border-indigo-500 focus:outline-none placeholder-gray-600"
          />
          <Search size={14} className="absolute left-3 top-2.5 text-gray-600" />
        </div>
        <select
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-2 border border-gray-700 focus:border-indigo-500 focus:outline-none"
        >
          {projects.map((p) => (
            <option key={p} value={p}>
              {p === "all" ? "All projects" : p}
            </option>
          ))}
        </select>
        <span className="text-xs text-gray-500">
          {filtered.length} of {sessions.length} sessions
        </span>
      </div>

      {/* Detail panel */}
      {selected && (
        <div className="bg-gray-900 rounded-xl border border-indigo-500/30 overflow-hidden">
          <div className="bg-indigo-500/5 px-5 py-3 border-b border-indigo-500/20 flex items-start justify-between">
            <div>
              <h3 className="text-lg font-semibold text-white">
                {selected.summary || "No summary"}
              </h3>
              <p className="text-sm text-gray-400">
                {selected.project_name} &middot; {selected.session_id.slice(0, 8)}
              </p>
            </div>
            <button
              onClick={() => setSelected(null)}
              className="text-gray-400 hover:text-white text-sm px-2 py-1 rounded hover:bg-gray-800 transition-colors"
            >
              Close
            </button>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
              {detailItems.map((item) => (
                <div
                  key={item.label}
                  className="bg-gray-950 rounded-lg p-3 border border-gray-800"
                >
                  <div className="text-xs text-gray-500 flex items-center gap-1.5">
                    <item.Icon size={12} />
                    {item.label}
                  </div>
                  <div className="text-sm text-gray-200 mt-1 font-medium">
                    {item.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Tool breakdown */}
            {selected.tool_breakdown?.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-400 mb-2 uppercase tracking-wide">
                  Tool Breakdown
                </h4>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  {selected.tool_breakdown.map((t) => {
                    const hasErrors = t.errors > 0;
                    return (
                      <div
                        key={t.tool}
                        className={`rounded-lg p-2.5 border text-center ${
                          hasErrors
                            ? "bg-red-500/5 border-red-500/20"
                            : "bg-gray-950 border-gray-800"
                        }`}
                      >
                        <div className="text-xs text-gray-400 truncate" title={t.tool}>
                          {t.tool}
                        </div>
                        <div className="text-sm font-bold text-gray-200 mt-0.5">
                          {t.count}
                        </div>
                        {hasErrors && (
                          <div className="text-xs text-red-400 mt-0.5">
                            {t.errors} errors
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Session table */}
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <SortableTable
          columns={columns}
          data={filtered as unknown as Record<string, unknown>[]}
          pageSize={25}
          onRowClick={handleSelect}
          defaultSort={{ key: "first_message_at", dir: "desc" }}
        />
      </div>

      {!selected && (
        <InfoBox>
          Click any session row to see its detailed breakdown including tool usage, token counts, and model information.
        </InfoBox>
      )}
    </div>
  );
}
