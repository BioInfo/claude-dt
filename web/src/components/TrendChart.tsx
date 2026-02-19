import { useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Brush,
  ReferenceLine,
} from "recharts";

interface Props {
  data: { date: string; value: number }[];
  label: string;
  description?: string;
  color?: string;
  height?: number;
  showBrush?: boolean;
  showAverage?: boolean;
}

export default function TrendChart({
  data,
  label,
  description,
  color = "#818cf8",
  height = 220,
  showBrush = false,
  showAverage = false,
}: Props) {
  const [hoveredValue, setHoveredValue] = useState<{
    date: string;
    value: number;
  } | null>(null);

  const avg = data.length
    ? Math.round(data.reduce((s, d) => s + d.value, 0) / data.length)
    : 0;
  const max = data.length ? Math.max(...data.map((d) => d.value)) : 0;
  const min = data.length ? Math.min(...data.map((d) => d.value)) : 0;

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-medium text-gray-300">{label}</h3>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {hoveredValue ? (
            <span className="text-gray-300 font-medium">
              {hoveredValue.date.slice(5)}: {hoveredValue.value.toLocaleString()}
            </span>
          ) : (
            <>
              <span>avg {avg.toLocaleString()}</span>
              <span className="text-gray-600">|</span>
              <span>
                {min.toLocaleString()}-{max.toLocaleString()}
              </span>
            </>
          )}
        </div>
      </div>
      {description && (
        <p className="text-xs text-gray-500 mb-3">{description}</p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart
          data={data}
          onMouseMove={(e: { activePayload?: { payload: { date: string; value: number } }[] }) => {
            if (e?.activePayload?.[0]) {
              setHoveredValue(e.activePayload[0].payload);
            }
          }}
          onMouseLeave={() => setHoveredValue(null)}
        >
          <defs>
            <linearGradient id={`grad-${label}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            tickFormatter={(v: string) => v.slice(5)}
            axisLine={{ stroke: "#374151" }}
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 11 }}
            width={50}
            axisLine={{ stroke: "#374151" }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#111827",
              border: "1px solid #374151",
              borderRadius: 8,
              color: "#e5e7eb",
              fontSize: 12,
            }}
            labelFormatter={(l: string) => `Date: ${l}`}
            formatter={(v: number) => [v.toLocaleString(), label]}
          />
          {showAverage && (
            <ReferenceLine
              y={avg}
              stroke="#4b5563"
              strokeDasharray="4 4"
              label={{ value: `avg: ${avg}`, fill: "#6b7280", fontSize: 10, position: "right" }}
            />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#grad-${label})`}
            activeDot={{ r: 5, fill: color, stroke: "#111827", strokeWidth: 2 }}
          />
          {showBrush && (
            <Brush
              dataKey="date"
              height={24}
              stroke="#374151"
              fill="#111827"
              tickFormatter={(v: string) => v.slice(5)}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
