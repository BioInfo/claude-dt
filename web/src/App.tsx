import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  Lightbulb,
  TrendingUp,
  List,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/report", label: "Report", Icon: FileText },
  { to: "/recommendations", label: "Recommendations", Icon: Lightbulb },
  { to: "/trends", label: "Trends", Icon: TrendingUp },
  { to: "/sessions", label: "Sessions", Icon: List },
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-gray-950">
      {/* Sidebar */}
      <nav className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col py-6 px-3 shrink-0">
        <div className="px-3 mb-8">
          <h1 className="text-xl font-bold text-white">
            <span className="text-indigo-400">dt</span> Dashboard
          </h1>
          <p className="text-xs text-gray-600 mt-1">Claude Code DevTools</p>
        </div>
        <div className="space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? "bg-indigo-500/15 text-indigo-300 shadow-sm shadow-indigo-500/5"
                    : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                }`
              }
            >
              <item.Icon size={16} />
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="mt-auto px-3 pt-4 border-t border-gray-800">
          <div className="text-xs text-gray-600">
            Open-source CLI analytics
          </div>
          <div className="text-xs text-gray-700 mt-0.5">
            github.com/claude-dt
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6 pb-12">
        <Outlet />
      </main>
    </div>
  );
}
