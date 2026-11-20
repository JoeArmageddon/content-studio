import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import OverviewPage from "./pages/OverviewPage";
import ChannelsPage from "./pages/ChannelsPage";
import ChannelDetailPage from "./pages/ChannelDetailPage";
import VideosPage from "./pages/VideosPage";
import RunsPage from "./pages/RunsPage";
import LibraryPage from "./pages/LibraryPage";
import LearningPage from "./pages/LearningPage";
import SystemPage from "./pages/SystemPage";

const NAV = [
  ["/", "Overview", true],
  ["/channels", "Channels"],
  ["/videos", "Videos"],
  ["/runs", "Runs"],
  ["/library", "Footage"],
  ["/learning", "Learning"],
  ["/system", "System"],
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="orbs" aria-hidden="true"><i className="orb orb-1" /><i className="orb orb-2" /><i className="orb orb-3" /></div>
      <header className="sticky top-0 z-30 px-3 pt-3 sm:px-6">
        <div className="glass glass-bar mx-auto flex max-w-7xl items-center gap-3 px-3 py-2 sm:px-4">
          <div className="flex shrink-0 items-center gap-2.5 pr-1">
            <span className="grid h-8 w-8 place-items-center rounded-xl text-sm font-bold text-white shadow-lg" style={{ background: "linear-gradient(135deg, var(--orb-1), var(--orb-2) 60%, var(--orb-3))" }}>S</span>
            <span className="hidden text-[15px] font-semibold tracking-tight sm:inline">Content Studio</span>
          </div>
          <nav className="no-scrollbar flex flex-1 gap-1 overflow-x-auto">
            {NAV.map(([to, label, end]) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `navlink ${isActive ? "active" : ""}`}>
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/channels" element={<ChannelsPage />} />
          <Route path="/channels/:key" element={<ChannelDetailPage />} />
          <Route path="/videos" element={<VideosPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/learning" element={<LearningPage />} />
          <Route path="/system" element={<SystemPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
