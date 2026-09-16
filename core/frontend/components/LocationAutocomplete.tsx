import React, { useState, useEffect, useRef } from "react";
import { MapPin, Loader2 } from "lucide-react";

interface LocationAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
}

export function LocationAutocomplete({ value, onChange }: LocationAutocompleteProps) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<any[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!query || query.length < 2) {
      setResults([]);
      return;
    }
    
    if (query === value) return;

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        // TODO: Route through backend proxy if clearbit/open-meteo add CORS restrictions
        const res = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=5`);
        if (!res.ok) throw new Error('Autocomplete unavailable')
        const data = await res.json();
        setResults(data.results || []);
        setIsOpen(true);
      } catch (e) {
        // Silently fail — user can still type manually
        setResults([]);
        console.error("Geocoding API error", e);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query, value]);

  return (
    <div className="relative" ref={dropdownRef}>
      <div className="relative">
        <MapPin size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            onChange(e.target.value); 
            setIsOpen(true);
          }}
          onFocus={() => { if (results.length > 0) setIsOpen(true); }}
          placeholder="e.g. San Francisco, London..."
          className="flex h-10 w-full rounded-xl border border-input bg-background/50 px-3 py-2 pl-9 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all hover:bg-accent/10"
        />
        {isLoading && (
          <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground animate-spin" />
        )}
      </div>

      {isOpen && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-background border rounded-xl shadow-xl overflow-hidden max-h-60 overflow-y-auto">
          <div className="p-1">
            {results.map((loc, idx) => {
              const displayName = [loc.name, loc.admin1, loc.country].filter(Boolean).join(", ");
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    onChange(displayName);
                    setQuery(displayName);
                    setIsOpen(false);
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2 text-sm text-left hover:bg-accent rounded-lg transition-colors"
                >
                  <div className="w-6 h-6 rounded bg-muted flex items-center justify-center shrink-0">
                    <MapPin size={12} className="text-muted-foreground" />
                  </div>
                  <div className="truncate">
                    <div className="font-medium truncate">{loc.name}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {[loc.admin1, loc.country].filter(Boolean).join(", ")}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
