import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import ChannelsPage from "./pages/ChannelsPage";
import ChannelDetailPage from "./pages/ChannelDetailPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto max-w-5xl px-6 py-4">
            <Link to="/" className="text-lg font-semibold text-slate-900">
              Content Studio
            </Link>
            <span className="ml-2 text-sm text-slate-400">Storique — 10 channels</span>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">
          <Routes>
            <Route path="/" element={<ChannelsPage />} />
            <Route path="/channels/:key" element={<ChannelDetailPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
