import { useEffect, useState } from "react";
import { api } from "../api";
import type { ReportData } from "../api";
import AntipatternList from "../components/AntipatternList";
import SortableTable from "../components/SortableTable";
import StatCard from "../components/StatCard";
import {
  ClipboardList,
  MessageSquare,
  Wrench,
  Target,
} from "lucide-react";

function shortModel(m: string): string {
  return m.replace("claude-", "").replace(/-\d{8}$/, "");
}

export default function Report() {
  const [data, setData] = useState<ReportData | null>(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.report(days).then(setData).finally(() => setLoading(false));
  }, [days]);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 animate-pulse text-lg">Loading report...</div>
      </div>
    );
  }

  const ov = data.overview;

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <h2 className="text-2xl font-bold text-white">Report</h2>
          <p className="text-sm text-gray-500 mt-1">
            Comprehensive analysis of your Claude Code activity
          </p>
        </div>
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
      </div>

      {/* Overview */}
      {ov && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard Icon={ClipboardList} label="Sessions" value={ov[0] || 0} />
          <StatCard Icon={MessageSquare} label="Messages" value={ov[1] || 0} />
          <StatCard
            Icon={Wrench}
            label="Tool Calls"
            value={ov[2] || 0}
            description={ov[3] ? `${ov[3].toLocaleString()} errors (${((ov[3] / (ov[2] || 1)) * 100).toFixed(1)}%)` : "No errors"}
          />
          <StatCard
            Icon={Target}
            label="Tokens"
            value={(ov[4] || 0).toLocaleString()}
            description={
              ov[5] && ov[4]
                ? `Cache efficiency: ${((ov[5] / (ov[5] + ov[4])) * 100).toFixed(0)}%`
                : undefined
            }
          />
        </div>
      )}

      {/* Model usage */}
      {data.model_usage?.length > 0 && (
        <Section
          title="Model Usage"
          description="Token consumption and cache efficiency by model. Higher cache reads mean better prompt caching."
        >
          <SortableTable
            columns={[
              { key: "model", label: "Model" },
              { key: "messages", label: "Messages", align: "right" },
              { key: "tokens", label: "Tokens", align: "right" },
              { key: "cache", label: "Cache Reads", align: "right" },
            ]}
            data={data.model_usage.map((r) => ({
              model: shortModel(r[0]),
              messages: r[1] || 0,
              tokens: r[2] || 0,
              cache: r[3] || 0,
            }))}
            defaultSort={{ key: "messages", dir: "desc" }}
          />
        </Section>
      )}

      {/* Top projects */}
      {data.top_projects?.length > 0 && (
        <Section
          title="Top Projects"
          description="Most active projects by session count. High tool counts may indicate complex tasks or inefficient workflows."
        >
          <SortableTable
            columns={[
              { key: "project", label: "Project" },
              { key: "sessions", label: "Sessions", align: "right" },
              { key: "messages", label: "Messages", align: "right" },
              { key: "tools", label: "Tools", align: "right" },
            ]}
            data={data.top_projects.map((r) => ({
              project: r[0],
              sessions: r[1] || 0,
              messages: r[2] || 0,
              tools: r[3] || 0,
            }))}
            defaultSort={{ key: "sessions", dir: "desc" }}
          />
        </Section>
      )}

      {/* Tool usage */}
      {data.tools?.tool_frequency?.length > 0 && (
        <Section
          title="Tool Usage"
          description="Frequency and error rates for each tool. High error rates on Edit usually mean the file wasn't Read first."
        >
          <SortableTable
            columns={[
              { key: "tool", label: "Tool" },
              { key: "calls", label: "Calls", align: "right" },
              { key: "errors", label: "Errors", align: "right" },
              {
                key: "errorPct",
                label: "Error %",
                align: "right",
                render: (v) => {
                  const n = v as number;
                  const color = n > 10 ? "text-red-400" : n > 5 ? "text-yellow-400" : "text-gray-400";
                  return <span className={color}>{n}%</span>;
                },
              },
            ]}
            data={data.tools.tool_frequency.map((r) => ({
              tool: r[0],
              calls: r[1] || 0,
              errors: r[2] || 0,
              errorPct: r[3] || 0,
            }))}
            defaultSort={{ key: "calls", dir: "desc" }}
          />
        </Section>
      )}

      {/* Context hotspots */}
      {data.context?.hotspot_files?.length > 0 && (
        <Section
          title="Context Hotspots"
          description="Files read most often. If a file appears here frequently, consider adding its key content to CLAUDE.md to avoid re-reads."
        >
          <SortableTable
            columns={[
              {
                key: "file",
                label: "File",
                render: (v) => (
                  <span className="font-mono text-xs text-gray-400">
                    {String(v).slice(-65)}
                  </span>
                ),
              },
              { key: "reads", label: "Reads", align: "right" },
              { key: "sessions", label: "Sessions", align: "right" },
            ]}
            data={data.context.hotspot_files.map((r) => ({
              file: String(r[0]),
              reads: r[1] || 0,
              sessions: r[2] || 0,
            }))}
            defaultSort={{ key: "reads", dir: "desc" }}
          />
        </Section>
      )}

      {/* Prompt patterns */}
      {data.prompts?.patterns?.length > 0 && (
        <Section
          title="Prompt Patterns"
          description="How your prompts are classified. More specific patterns (fix, create, refactor) lead to faster results than 'other'."
        >
          <SortableTable
            columns={[
              { key: "pattern", label: "Pattern" },
              { key: "count", label: "Count", align: "right" },
              { key: "avgWords", label: "Avg Words", align: "right" },
            ]}
            data={data.prompts.patterns.map((r) => ({
              pattern: r[0],
              count: r[1] || 0,
              avgWords: Math.round(r[2] || 0),
            }))}
            defaultSort={{ key: "count", dir: "desc" }}
          />
        </Section>
      )}

      {/* Anti-patterns */}
      {data.antipatterns?.length > 0 && (
        <Section
          title="Anti-Patterns"
          description="Detected inefficiencies. Critical items waste the most tokens and should be addressed first."
        >
          <AntipatternList items={data.antipatterns} />
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
      <h3 className="text-base font-semibold text-gray-200 mb-1">{title}</h3>
      {description && (
        <p className="text-xs text-gray-500 mb-4">{description}</p>
      )}
      {children}
    </div>
  );
}
