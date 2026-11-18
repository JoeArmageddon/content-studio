import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import OverviewPage from "./pages/OverviewPage";
import ChannelsPage from "./pages/ChannelsPage";
import ChannelDetailPage from "./pages/ChannelDetailPage";
import VideosPage from "./pages/VideosPage";
import RunsPage from "./pages/RunsPage";
import LibraryPage from "./pages/LibraryPage";
import SystemPage from "./pages/SystemPage";

const NAV = [
  ["/", "Overview", true],
  ["/channels", "Channels"],
  ["/videos", "Videos"],
  ["/runs", "Runs"],
  ["/library", "Footage"],
  ["/system", "System"],
];

export default function App() {
  return (
    <BrowserRouter>
      <header className="sticky top-0 z-20 border-b backdrop-blur hairline" style={{ background: "color-mix(in srgb, var(--surface) 88%, transparent)" }}>
        <div className="mx-auto flex max-w-7xl items-center gap-5 px-4 sm:px-6">
          <div className="flex shrink-0 items-center gap-2 py-3">
            <span className="grid h-7 w-7 place-items-center rounded-lg text-sm font-bold text-white" style={{ background: "var(--accent)" }}>S</span>
            <span className="hidden text-[15px] font-semibold sm:inline">Content Studio</span>
          </div>
          <nav className="-mb-px flex flex-1 gap-1 overflow-x-auto">
            {NAV.map(([to, label, end]) => (
              <NavLink key={to} to={to} end={end}
                className={({ isActive }) => `whitespace-nowrap border-b-2 px-3 py-3.5 text-sm font-medium transition ${isActive ? "border-[var(--accent)] text-[var(--text)]" : "muted border-transparent hover:text-[var(--text)]"}`}>
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
          <Route path="/system" element={<SystemPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
