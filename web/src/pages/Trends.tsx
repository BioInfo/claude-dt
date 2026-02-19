import { useEffect, useState } from "react";
import { api } from "../api";
import type { TrendsData } from "../api";
import TrendChart from "../components/TrendChart";
import InfoBox from "../components/InfoBox";
import SortableTable from "../components/SortableTable";
import {
  ClipboardList,
  MessageSquare,
  Wrench,
  AlertTriangle,
  Target,
  RefreshCw,
  FolderOpen,
  Bot,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

function shortModel(m: string): string {
  return m.replace("claude-", "").replace(/-\d{8}$/, "");
}

function delta(cur: number, prev: number): string {
  if (!prev) return "new";
  const pct = ((cur - prev) / prev) * 100;
  if (pct > 0) return `+${pct.toFixed(0)}%`;
  if (pct < 0) return `${pct.toFixed(0)}%`;
  return "0%";
}

function deltaColor(cur: number, prev: number): string {
  if (!prev) return "text-gray-400";
  const pct = ((cur - prev) / prev) * 100;
  if (pct > 0) return "text-emerald-400";
  if (pct < 0) return "text-red-400";
  return "text-gray-400";
}

const chartMetrics = ["sessions", "messages", "tools", "tokens"] as const;
const chartColors: Record<string, string> = {
  sessions: "#818cf8",
  messages: "#34d399",
  tools: "#fbbf24",
  tokens: "#f472b6",
};

export default function Trends() {
  const [data, setData] = useState<TrendsData | null>(null);
  const [days, setDays] = useState(14);
  const [activeChart, setActiveChart] = useState<string>("sessions");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.trends(days).then(setData).finally(() => setLoading(false));
  }, [days]);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 animate-pulse text-lg">Loading trends...</div>
      </div>
    );
  }

  const half = data.period_days;
  const cur = data.current;
  const prev = data.previous;

  const metrics: { label: string; ci: number; Icon: LucideIcon }[] = [
    { label: "Sessions", ci: 0, Icon: ClipboardList },
    { label: "Messages", ci: 1, Icon: MessageSquare },
    { label: "Tool Calls", ci: 2, Icon: Wrench },
    { label: "Tool Errors", ci: 3, Icon: AlertTriangle },
    { label: "Tokens", ci: 4, Icon: Target },
    { label: "Avg Turns", ci: 5, Icon: RefreshCw },
    { label: "Projects", ci: 6, Icon: FolderOpen },
    { label: "Subagents", ci: 7, Icon: Bot },
  ];

  const chartDataMap: Record<string, { date: string; value: number }[]> = {
    sessions: data.daily.map((d) => ({ date: String(d[0]), value: d[1] })),
    messages: data.daily.map((d) => ({ date: String(d[0]), value: d[2] || 0 })),
    tools: data.daily.map((d) => ({ date: String(d[0]), value: d[3] || 0 })),
    tokens: data.daily.map((d) => ({ date: String(d[0]), value: d[4] || 0 })),
  };

  // Model shift
  const curModels: Record<string, number> = {};
  const prevModels: Record<string, number> = {};
  for (const [m, c] of data.current_models) curModels[shortModel(m)] = c;
  for (const [m, c] of data.previous_models) prevModels[shortModel(m)] = c;
  const allModels = [
    ...new Set([...Object.keys(curModels), ...Object.keys(prevModels)]),
  ].sort((a, b) => (curModels[b] || 0) - (curModels[a] || 0));

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <h2 className="text-2xl font-bold text-white">Trends</h2>
          <p className="text-sm text-gray-500 mt-1">
            Compare your current period against the previous one to spot changes.
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="bg-gray-800 text-gray-300 text-sm rounded-lg px-3 py-2 border border-gray-700 focus:border-indigo-500 focus:outline-none"
        >
          {[14, 30, 60].map((d) => (
            <option key={d} value={d}>
              {d / 2}d vs {d / 2}d
            </option>
          ))}
        </select>
      </div>

      <InfoBox>
        The period is split in half: <strong className="text-gray-300">current</strong> (most recent {half} days) vs <strong className="text-gray-300">previous</strong> ({half} days before that). Green means growth, red means decline.
      </InfoBox>

      {/* Period comparison */}
      <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
        <h3 className="text-base font-semibold text-gray-200 mb-4">
          Period Comparison
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                <th className="pb-2 pr-4 w-8"></th>
                <th className="pb-2 pr-4">Metric</th>
                <th className="pb-2 pr-4 text-right">Current ({half}d)</th>
                <th className="pb-2 pr-4 text-right">Previous ({half}d)</th>
                <th className="pb-2 text-right">Change</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map(({ label, ci, Icon }) => {
                const c = cur[ci] || 0;
                const p = prev[ci] || 0;
                const isFloat = label === "Avg Turns";
                return (
                  <tr key={label} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-2 pr-2 text-center">
                      <Icon size={14} className="text-gray-500 inline" />
                    </td>
                    <td className="py-2 pr-4 text-gray-300 font-medium">{label}</td>
                    <td className="py-2 pr-4 text-right text-gray-200 font-medium">
                      {isFloat ? c.toFixed(1) : c.toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-400">
                      {isFloat ? p.toFixed(1) : p.toLocaleString()}
                    </td>
                    <td
                      className={`py-2 text-right font-semibold ${deltaColor(c, p)}`}
                    >
                      {delta(c, p)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Interactive chart with metric switcher */}
      <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
        <div className="flex items-center gap-2 mb-4">
          <h3 className="text-base font-semibold text-gray-200 mr-2">Daily Activity</h3>
          {chartMetrics.map((m) => (
            <button
              key={m}
              onClick={() => setActiveChart(m)}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                activeChart === m
                  ? "text-white border"
                  : "text-gray-400 hover:bg-gray-800 border border-transparent"
              }`}
              style={
                activeChart === m
                  ? { backgroundColor: chartColors[m] + "22", borderColor: chartColors[m] + "44" }
                  : undefined
              }
            >
              {m.charAt(0).toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
        <TrendChart
          data={chartDataMap[activeChart]}
          label={activeChart.charAt(0).toUpperCase() + activeChart.slice(1)}
          color={chartColors[activeChart]}
          height={280}
          showBrush={data.daily.length > 14}
          showAverage
        />
      </div>

      {/* All charts grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {chartMetrics
          .filter((m) => m !== activeChart)
          .map((m) => (
            <div
              key={m}
              className="cursor-pointer"
              onClick={() => setActiveChart(m)}
            >
              <TrendChart
                data={chartDataMap[m]}
                label={m.charAt(0).toUpperCase() + m.slice(1)}
                color={chartColors[m]}
                height={160}
              />
            </div>
          ))}
      </div>

      {/* Model shift */}
      {allModels.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-base font-semibold text-gray-200 mb-1">Model Shift</h3>
          <p className="text-xs text-gray-500 mb-4">
            Changes in model usage between periods. Watch for unintentional shifts to more expensive models.
          </p>
          <SortableTable
            columns={[
              { key: "model", label: "Model" },
              { key: "current", label: "Current", align: "right" },
              { key: "previous", label: "Previous", align: "right" },
              {
                key: "change",
                label: "Change",
                align: "right",
                render: (_v, row) => {
                  const c = row.current as number;
                  const p = row.previous as number;
                  return (
                    <span className={`font-semibold ${deltaColor(c, p)}`}>
                      {delta(c, p)}
                    </span>
                  );
                },
              },
            ]}
            data={allModels.map((m) => ({
              model: m,
              current: curModels[m] || 0,
              previous: prevModels[m] || 0,
              change: 0,
            }))}
            defaultSort={{ key: "current", dir: "desc" }}
          />
        </div>
      )}
    </div>
  );
}
