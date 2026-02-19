import { useState } from "react";
import type { Recommendation } from "../api";

interface Props {
  rec: Recommendation;
}

const priorityStyles = {
  high: "bg-red-500/15 text-red-400 border-red-500/30",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  low: "bg-blue-500/15 text-blue-400 border-blue-500/30",
};

export default function RecommendationCard({ rec }: Props) {
  const [copied, setCopied] = useState(false);

  const copyPrompt = () => {
    navigator.clipboard.writeText(rec.prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="flex items-start gap-3 mb-2">
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${priorityStyles[rec.priority]}`}
        >
          {rec.priority.toUpperCase()}
        </span>
        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">
          {rec.category}
        </span>
      </div>
      <h3 className="text-sm font-semibold text-gray-200 mb-1">{rec.title}</h3>
      <p className="text-xs text-gray-400 mb-3">{rec.description}</p>
      {rec.impact && (
        <p className="text-xs text-emerald-400 mb-3">{rec.impact}</p>
      )}
      <div className="relative">
        <pre className="text-xs bg-gray-950 text-gray-300 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap border border-gray-800">
          {rec.prompt}
        </pre>
        <button
          onClick={copyPrompt}
          className="absolute top-2 right-2 text-xs px-2 py-1 rounded bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    </div>
  );
}
