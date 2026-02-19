interface Props {
  label: string;
  score: number;
  large?: boolean;
}

function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-yellow-400";
  return "text-red-400";
}

function ringColor(score: number): string {
  if (score >= 80) return "stroke-emerald-400";
  if (score >= 60) return "stroke-yellow-400";
  return "stroke-red-400";
}

export default function ScoreCard({ label, score, large }: Props) {
  const size = large ? 120 : 80;
  const stroke = large ? 8 : 6;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - score / 100);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-gray-800"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={`${ringColor(score)} transition-all duration-700`}
        />
      </svg>
      <div className="flex flex-col items-center -mt-2" style={{ marginTop: large ? -size / 2 - 14 : -size / 2 - 10 }}>
        <span className={`${large ? "text-3xl" : "text-xl"} font-bold ${scoreColor(score)}`}>
          {score}
        </span>
      </div>
      <span className={`${large ? "text-sm mt-4" : "text-xs mt-2"} text-gray-400 font-medium`}>
        {label}
      </span>
    </div>
  );
}
