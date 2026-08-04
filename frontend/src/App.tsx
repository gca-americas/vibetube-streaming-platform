import { useState, useEffect } from "react";
import { SearchBar } from "./components/SearchBar";
import { VideoCard, Video } from "./components/VideoCard";
import { VideoPlayerModal } from "./components/VideoPlayerModal";
import { UploadModal } from "./components/UploadModal";
import { AuthModal } from "./components/AuthModal";
import { getAuth } from "./services/firebase";
import { Film, Sun, Moon, Plus, LogOut, LogIn } from "lucide-react";

export default function App() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = localStorage.getItem("theme");
    return (saved as "dark" | "light") || "dark";
  });
  
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);

  // Listen for user auth state changes
  useEffect(() => {
    const auth = getAuth();
    const unsubscribe = auth.onAuthStateChanged((currentUser: any) => {
      setUser(currentUser);
    });
    return () => unsubscribe();
  }, []);

  // Sync theme changes with the DOM element class list
  useEffect(() => {
    if (theme === "light") {
      document.documentElement.classList.add("light");
    } else {
      document.documentElement.classList.remove("light");
    }
  }, [theme]);

  // Fetch videos function
  const fetchVideos = () => {
    setLoading(true);
    fetch("/api/videos")
      .then((res) => {
        if (!res.ok) {
          throw new Error("Failed to load videos from server");
        }
        return res.json();
      })
      .then((data) => {
        setVideos(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  // Fetch videos from backend server on mount
  useEffect(() => {
    fetchVideos();
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
  };

  // Filter videos based on title, description, or channel name
  const filteredVideos = videos.filter((video) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    return (
      video.title.toLowerCase().includes(query) ||
      video.description.toLowerCase().includes(query) ||
      video.channelName.toLowerCase().includes(query)
    );
  });

  return (
    <div className="min-h-screen stage-vignette relative bg-stage text-fg flex flex-col transition-colors duration-300">
      {/* Background vignette wrapper */}
      <div className="relative z-10 flex-1 flex flex-col px-4 py-8 md:px-8 max-w-7xl mx-auto w-full">
        {/* Controls Container */}
        <div className="absolute top-6 right-4 md:right-8 flex items-center gap-2">
          {/* Upload Button */}
          {user && (
            <button
              onClick={() => setUploadOpen(true)}
              className="p-2.5 rounded-full bg-card hover:bg-card-hover border border-hairline text-fg-muted hover:text-fg shadow-lg transition-all duration-200 cursor-pointer"
              aria-label="Publish new stream"
            >
              <Plus className="w-5 h-5" />
            </button>
          )}

          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="p-2.5 rounded-full bg-card hover:bg-card-hover border border-hairline text-fg-muted hover:text-fg shadow-lg transition-all duration-200 cursor-pointer"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? (
              <Sun className="w-5 h-5 text-amber-400" />
            ) : (
              <Moon className="w-5 h-5 text-indigo-500" />
            )}
          </button>

          {/* Authentication Actions */}
          {user ? (
            <div className="flex items-center gap-2">
              <img
                src={user.photoURL}
                alt={user.displayName}
                title={user.displayName}
                className="w-10 h-10 rounded-full object-cover border border-hairline"
              />
              <button
                onClick={() => getAuth().signOut()}
                className="p-2.5 rounded-full bg-card hover:bg-card-hover border border-hairline text-fg-muted hover:text-red-400 shadow-lg transition-all duration-200 cursor-pointer"
                aria-label="Sign out"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setAuthModalOpen(true)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white font-bold text-sm shadow-lg shadow-red-500/10 cursor-pointer transition-all duration-150"
            >
              <LogIn className="w-4 h-4" />
              <span>Sign In</span>
            </button>
          )}
        </div>

        {/* Header Section */}
        <header className="flex flex-col items-center text-center mt-6 mb-12 md:mb-16">
          <div className="flex items-center gap-2 mb-3">
            <Film className="w-8 h-8 text-vibe-red animate-pulse" />
            <h1 className="font-display text-4xl md:text-5xl tracking-tighter font-black bg-gradient-to-r from-vibe-red to-vibe-purple bg-clip-text text-transparent">
              VIBEFLIX
            </h1>
          </div>
          <p className="text-sm md:text-base text-fg-muted font-medium max-w-md mb-8">
            Curated channels and cinematic feeds to match your daily frequency.
          </p>

          {/* Centered Search Bar */}
          <SearchBar
            value={searchQuery}
            onChange={(val) => {
              setSearchQuery(val);
            }}
            onClear={() => setSearchQuery("")}
          />
        </header>

        {/* Main Content (Videos Grid or Loader/Error status) */}
        <main className="flex-1">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 text-center animate-pulse">
              <Film className="w-12 h-12 text-vibe-red mb-4" />
              <p className="text-sm text-fg-muted font-medium">Tuning into the vibe frequency...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-500 mb-4">
                <Film className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold text-fg mb-1">Failed to connect to Vibeflix</h3>
              <p className="text-sm text-red-400 max-w-xs">{error}</p>
            </div>
          ) : filteredVideos.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {filteredVideos.map((video) => (
                <VideoCard
                  key={video.id}
                  video={video}
                  onClick={setSelectedVideo}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-16 h-16 rounded-full bg-overlay border border-hairline flex items-center justify-center text-fg-muted mb-4">
                <Film className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold text-fg mb-1">
                No streams matching that vibe
              </h3>
              <p className="text-sm text-fg-muted max-w-xs">
                Try searching for something else, like "synthwave", "code", or "keyboard".
              </p>
            </div>
          )}
        </main>

        {/* Minimal Footer */}
        <footer className="mt-20 py-6 border-t border-hairline flex flex-col md:flex-row items-center justify-between text-xs text-fg-muted gap-4">
          <p>
            © {new Date().getFullYear()} Vibeflix Inc. Handcrafted with vibe-driven design.
          </p>
          <div className="flex gap-4">
            <span className="hover:text-fg cursor-pointer transition-colors duration-150">
              Support
            </span>
          </div>
        </footer>
      </div>

      {/* Video Player Modal */}
      {selectedVideo && (
        <VideoPlayerModal
          video={selectedVideo}
          onClose={() => setSelectedVideo(null)}
        />
      )}

      {/* Upload Modal */}
      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onUploadSuccess={fetchVideos}
        />
      )}

      {/* Auth Modal */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
      />
    </div>
  );
}
