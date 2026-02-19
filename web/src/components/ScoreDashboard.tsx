import ScoreCard from "./ScoreCard";
import type { Scores } from "../api";

interface Props {
  scores: Scores;
}

export default function ScoreDashboard({ scores }: Props) {
  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-center gap-10 flex-wrap">
        <ScoreCard label="Overall" score={scores.composite} large />
        <div className="flex gap-8 flex-wrap justify-center">
          <ScoreCard label="Context" score={scores.context} />
          <ScoreCard label="Tools" score={scores.tools} />
          <ScoreCard label="Prompts" score={scores.prompts} />
          <ScoreCard label="Health" score={scores.health} />
        </div>
      </div>
    </div>
  );
}
