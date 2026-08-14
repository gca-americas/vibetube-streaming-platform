import { Search, X } from "lucide-react";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  /** Compact sizing for the top bar, where vertical space is tight. */
  compact?: boolean;
}

export const SearchBar = ({
  value,
  onChange,
  onClear,
  compact = false,
}: SearchBarProps) => {
  return (
    <div className={compact ? "w-full" : "w-full max-w-2xl mx-auto"}>
      <div className="relative group">
        {/* Glow effect under the search bar */}
        <div className={`absolute -inset-0.5 bg-gradient-to-r from-vibe-red to-vibe-purple rounded-full blur-md transition duration-500 group-focus-within:duration-200 ${
          compact
            ? "opacity-0 group-hover:opacity-25 group-focus-within:opacity-50"
            : "opacity-30 group-hover:opacity-50 group-focus-within:opacity-70"
        }`}></div>

        {/* Search Bar Container */}
        <div className={`relative flex items-center bg-input/90 backdrop-blur-xl border border-hairline rounded-full transition-all duration-300 ${
          compact ? "px-4 py-2 shadow-lg" : "px-5 py-3.5 shadow-2xl"
        }`}>
          <Search className={`text-fg-muted group-focus-within:text-vibe-red transition-colors duration-200 ${
            compact ? "w-4 h-4 mr-2.5" : "w-5 h-5 mr-3.5"
          }`} />

          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={compact ? "Search this showroom" : "Search videos, channels, or vibes..."}
            className={`flex-1 min-w-0 bg-transparent text-fg placeholder-fg-muted/60 focus:outline-none font-medium tracking-wide ${
              compact ? "text-sm" : "text-base"
            }`}
          />

          {value && (
            <button
              onClick={onClear}
              type="button"
              className="p-1 rounded-full hover:bg-overlay text-fg-muted hover:text-fg transition-all duration-150 cursor-pointer"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
