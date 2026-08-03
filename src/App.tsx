import { useState } from "react";
import { SearchBar } from "./components/SearchBar";
import { VideoCard, Video } from "./components/VideoCard";
import mockVideos from "./data/mockVideos.json";
import { Film } from "lucide-react";

export default function App() {
  const [searchQuery, setSearchQuery] = useState("");

  // Filter videos based on title, description, or channel name
  const filteredVideos = (mockVideos as Video[]).filter((video) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    return (
      video.title.toLowerCase().includes(query) ||
      video.description.toLowerCase().includes(query) ||
      video.channelName.toLowerCase().includes(query)
    );
  });

  return (
    <div className="min-h-screen stage-vignette relative bg-stage text-white flex flex-col">
      {/* Background vignette wrapper */}
      <div className="relative z-10 flex-1 flex flex-col px-4 py-8 md:px-8 max-w-7xl mx-auto w-full">
        {/* Header Section */}
        <header className="flex flex-col items-center text-center mt-6 mb-12 md:mb-16">
          <div className="flex items-center gap-2 mb-3">
            <Film className="w-8 h-8 text-vibe-red animate-pulse" />
            <h1 className="font-display text-4xl md:text-5xl tracking-tighter font-black bg-gradient-to-r from-vibe-red to-vibe-purple bg-clip-text text-transparent">
              VIBEFLIX
            </h1>
          </div>
          <p className="text-sm md:text-base text-gray-400 font-medium max-w-md mb-8">
            Curated channels and cinematic feeds to match your daily frequency.
          </p>
          
          {/* Centered Search Bar */}
          <SearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            onClear={() => setSearchQuery("")}
          />
        </header>

        {/* Main Content (Videos Grid) */}
        <main className="flex-1">
          {filteredVideos.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {filteredVideos.map((video) => (
                <VideoCard key={video.id} video={video} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-gray-500 mb-4">
                <Film className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold text-white mb-1">No streams matching that vibe</h3>
              <p className="text-sm text-gray-400 max-w-xs">
                Try searching for something else, like "synthwave", "code", or "keyboard".
              </p>
            </div>
          )}
        </main>

        {/* Minimal Footer */}
        <footer className="mt-20 py-6 border-t border-white/5 flex flex-col md:flex-row items-center justify-between text-xs text-gray-500 gap-4">
          <p>© {new Date().getFullYear()} Vibeflix Inc. Handcrafted with vibe-driven design.</p>
          <div className="flex gap-4">
            <span className="hover:text-white cursor-pointer transition-colors duration-150">Terms</span>
            <span className="hover:text-white cursor-pointer transition-colors duration-150">Privacy</span>
            <span className="hover:text-white cursor-pointer transition-colors duration-150">Support</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
