import { useEffect, useState } from "react";
import { api } from "../api";
import type { Scores, Recommendation, StatusData, TrendsData } from "../api";
import ScoreDashboard from "../components/ScoreDashboard";
import TrendChart from "../components/TrendChart";
import RecommendationCard from "../components/RecommendationCard";
import StatCard from "../components/StatCard";
import InfoBox from "../components/InfoBox";
import {
  ClipboardList,
  MessageSquare,
  Wrench,
  Bot,
  FolderOpen,
  PenLine,
  BarChart3,
  HardDrive,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const tableLabels: Record<string, { Icon: LucideIcon; label: string; desc: string }> = {
  sessions: { Icon: ClipboardList, label: "Sessions", desc: "Claude Code conversations tracked" },
  messages: { Icon: MessageSquare, label: "Messages", desc: "Total messages exchanged" },
  tool_calls: { Icon: Wrench, label: "Tool Calls", desc: "Tools invoked across sessions" },
  subagents: { Icon: Bot, label: "Subagents", desc: "Delegated agent tasks" },
  file_access: { Icon: FolderOpen, label: "File Access", desc: "File read/write operations logged" },
  prompts: { Icon: PenLine, label: "Prompts", desc: "User prompts analyzed" },
  daily_stats: { Icon: BarChart3, label: "Daily Stats", desc: "Days of aggregated metrics" },
};

export default function Dashboard() {
  const [scores, setScores] = useState<Scores | null>(null);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [status, setStatus] = useState<StatusData | null>(null);
  const [trends, setTrends] = useState<TrendsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.scores(7),
      api.recommend(7),
      api.status(),
      api.trends(14),
    ])
      .then(([s, r, st, t]) => {
        setScores(s);
        setRecs(r);
        setStatus(st);
        setTrends(t);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 animate-pulse text-lg">Loading dashboard...</div>
      </div>
    );
  }

  const dailySessions = (trends?.daily || []).map((d) => ({
    date: String(d[0]),
    value: d[1],
  }));
  const dailyMessages = (trends?.daily || []).map((d) => ({
    date: String(d[0]),
    value: d[2] || 0,
  }));

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Dashboard</h2>
        <p className="text-sm text-gray-500">
          Your Claude Code usage at a glance.
          {status?.last_ingest && (
            <span className="ml-2 text-gray-600">
              Last ingested: {status.last_ingest.replace("T", " ")}
            </span>
          )}
        </p>
      </div>

      {scores && <ScoreDashboard scores={scores} />}

      <InfoBox>
        Scores measure your Claude Code efficiency across four dimensions.
        <strong className="text-gray-300"> Context</strong> tracks cache utilization and file re-reads,
        <strong className="text-gray-300"> Tools</strong> measures error rates,
        <strong className="text-gray-300"> Prompts</strong> checks prompt specificity, and
        <strong className="text-gray-300"> Health</strong> looks for anti-patterns like repeat reads within sessions.
      </InfoBox>

      {/* Stats overview with human-readable labels */}
      {status && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(status.tables).map(([name, count]) => {
            const meta = tableLabels[name] || { Icon: BarChart3, label: name, desc: "" };
            return (
              <StatCard
                key={name}
                Icon={meta.Icon}
                label={meta.label}
                value={count}
                description={meta.desc}
              />
            );
          })}
          <StatCard
            Icon={HardDrive}
            label="Database"
            value={`${status.db_size_mb} MB`}
            description="DuckDB storage on disk"
          />
        </div>
      )}

      {/* Activity charts */}
      {dailySessions.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          <TrendChart
            data={dailySessions}
            label="Daily Sessions"
            description="Number of Claude Code sessions per day"
            color="#818cf8"
            showAverage
          />
          <TrendChart
            data={dailyMessages}
            label="Daily Messages"
            description="Total messages exchanged per day"
            color="#34d399"
            showAverage
          />
        </div>
      )}

      {/* Top recommendations */}
      {recs.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold text-gray-200">
              Top Recommendations
            </h3>
            <a
              href="/recommendations"
              className="text-xs text-indigo-400 hover:text-indigo-300"
            >
              View all {recs.length} &rarr;
            </a>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {recs.slice(0, 4).map((r, i) => (
              <RecommendationCard key={i} rec={r} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
