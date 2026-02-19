import { Info, Sparkles, AlertTriangle } from "lucide-react";

interface Props {
  children: React.ReactNode;
  variant?: "info" | "tip" | "warning";
}

const variants = {
  info: {
    border: "border-indigo-500/20",
    bg: "bg-indigo-500/5",
    Icon: Info,
    iconColor: "text-indigo-400",
  },
  tip: {
    border: "border-emerald-500/20",
    bg: "bg-emerald-500/5",
    Icon: Sparkles,
    iconColor: "text-emerald-400",
  },
  warning: {
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    Icon: AlertTriangle,
    iconColor: "text-amber-400",
  },
};

export default function InfoBox({ children, variant = "info" }: Props) {
  const v = variants[variant];
  return (
    <div
      className={`${v.bg} ${v.border} border rounded-lg px-4 py-3 flex gap-3 items-start`}
    >
      <v.Icon size={15} className={`${v.iconColor} mt-0.5 shrink-0`} />
      <div className="text-sm text-gray-400 leading-relaxed">{children}</div>
    </div>
  );
}
