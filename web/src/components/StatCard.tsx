import type { LucideIcon } from "lucide-react";

interface Props {
  Icon: LucideIcon;
  label: string;
  value: string | number;
  description?: string;
  trend?: { value: number; label: string };
}

export default function StatCard({ Icon, label, value, description, trend }: Props) {
  const displayValue = typeof value === "number" ? value.toLocaleString() : value;

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 hover:border-gray-700 transition-colors group">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className="text-gray-500" />
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">
          {label}
        </span>
      </div>
      <div className="text-2xl font-bold text-gray-100">{displayValue}</div>
      {trend && (
        <div className={`text-xs mt-1 ${trend.value >= 0 ? "text-emerald-400" : "text-red-400"}`}>
          {trend.value >= 0 ? "+" : ""}{trend.value}% {trend.label}
        </div>
      )}
      {description && (
        <div className="text-xs text-gray-500 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
          {description}
        </div>
      )}
    </div>
  );
}
