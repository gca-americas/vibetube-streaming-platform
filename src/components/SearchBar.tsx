import { Search, X } from "lucide-react";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
}

export const SearchBar = ({
  value,
  onChange,
  onClear,
}: SearchBarProps) => {
  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="relative group">
        {/* Glow effect under the search bar */}
        <div className="absolute -inset-0.5 bg-gradient-to-r from-vibe-red to-vibe-purple rounded-full opacity-30 blur-md group-hover:opacity-50 transition duration-500 group-focus-within:opacity-70 group-focus-within:duration-200"></div>
        
        {/* Search Bar Container */}
        <div className="relative flex items-center bg-input/90 backdrop-blur-xl border border-hairline rounded-full px-5 py-3.5 shadow-2xl transition-all duration-300">
          <Search className="w-5 h-5 text-fg-muted mr-3.5 group-focus-within:text-vibe-red transition-colors duration-200" />
          
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Search videos, channels, or vibes..."
            className="flex-1 bg-transparent text-fg placeholder-fg-muted/60 focus:outline-none text-base font-medium tracking-wide"
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
