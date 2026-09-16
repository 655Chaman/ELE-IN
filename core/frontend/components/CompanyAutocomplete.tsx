import React, { useState, useEffect, useRef } from "react";
import { Building2, Search, Loader2 } from "lucide-react";

interface CompanyAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
}

export function CompanyAutocomplete({ value, onChange }: CompanyAutocompleteProps) {
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
    
    // Only search if the query doesn't match the selected value
    if (query === value) return;

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        // TODO: Route through backend proxy if clearbit/open-meteo add CORS restrictions
        const res = await fetch(`https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error('Autocomplete unavailable')
        const data = await res.json();
        setResults(data);
        setIsOpen(true);
      } catch (e) {
        // Silently fail — user can still type manually
        setResults([]);
        console.error("Clearbit API error", e);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query, value]);

  return (
    <div className="relative" ref={dropdownRef}>
      <div className="relative">
        <Building2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            onChange(e.target.value); // keep parent state in sync
            setIsOpen(true);
          }}
          onFocus={() => { if (results.length > 0) setIsOpen(true); }}
          placeholder="e.g. Stripe, Microsoft..."
          className="flex h-10 w-full rounded-xl border border-input bg-background/50 px-3 py-2 pl-9 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all hover:bg-accent/10"
        />
        {isLoading && (
          <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground animate-spin" />
        )}
      </div>

      {isOpen && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-background border rounded-xl shadow-xl overflow-hidden max-h-60 overflow-y-auto">
          <div className="p-1">
            {results.map((company, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  onChange(company.name);
                  setQuery(company.name);
                  setIsOpen(false);
                }}
                className="w-full flex items-center gap-3 px-3 py-2 text-sm text-left hover:bg-accent rounded-lg transition-colors"
              >
                {company.logo ? (
                  <img src={company.logo} alt={company.name} className="w-6 h-6 rounded object-contain bg-white" />
                ) : (
                  <div className="w-6 h-6 rounded bg-muted flex items-center justify-center">
                    <Building2 size={12} className="text-muted-foreground" />
                  </div>
                )}
                <div>
                  <div className="font-medium">{company.name}</div>
                  <div className="text-xs text-muted-foreground">{company.domain}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
