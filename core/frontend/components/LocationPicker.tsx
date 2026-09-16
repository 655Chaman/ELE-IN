import { useState, useRef, useEffect } from 'react'
import { X, ChevronDown, Search } from 'lucide-react'
import { COUNTRY_GROUPS, getCitiesForCountry } from '../data/locationData'

interface LocationPickerProps {
  selectedCountries: string[]
  selectedCities: string[]
  onCountriesChange: (countries: string[]) => void
  onCitiesChange: (cities: string[]) => void
  disabled?: boolean
}

interface SearchableDropdownProps {
  options?: string[]
  groups?: { name: string, options: string[] }[]
  selectedValues: string[]
  placeholder: string
  onSelect: (val: string) => void
  disabled?: boolean
  emptyMessage?: string
}

function SearchableDropdown({
  options = [],
  groups,
  selectedValues,
  placeholder,
  onSelect,
  disabled,
  emptyMessage = "No options available",
}: SearchableDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filteredOptions = query
    ? options.filter(o => o.toLowerCase().includes(query.toLowerCase()))
    : options

  const availableOptions = filteredOptions.filter(o => !selectedValues.includes(o))

  const processedGroups = groups
    ? groups.map(g => {
        const filteredGroupOptions = query
          ? g.options.filter(o => o.toLowerCase().includes(query.toLowerCase()))
          : g.options
        const availableGroupOptions = filteredGroupOptions.filter(o => !selectedValues.includes(o))
        return { name: g.name, options: availableGroupOptions }
      }).filter(g => g.options.length > 0)
    : []

  const hasOptions = availableOptions.length > 0 || processedGroups.length > 0
  const hasExactMatch = groups
    ? processedGroups.some(g => g.options.some(o => o.toLowerCase() === query.trim().toLowerCase()))
    : availableOptions.some(a => a.toLowerCase() === query.trim().toLowerCase())

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setQuery("")
      }
    }
    document.addEventListener("mousedown", handleOutside)
    return () => document.removeEventListener("mousedown", handleOutside)
  }, [])

  const handleOpen = () => {
    if (disabled) return
    setIsOpen(true)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  const handleSelect = (val: string) => {
    onSelect(val)
    setQuery("")
    // keep open for multi-select
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  return (
    <div className="relative" ref={containerRef}>
      {/* Trigger */}
      <button
        type="button"
        onClick={handleOpen}
        disabled={disabled}
        className="flex items-center gap-2 px-3 py-1.5 bg-black/40 border border-white/5 hover:border-white/10 rounded-lg text-sm text-gray-400 hover:text-white transition-colors disabled:opacity-50 min-w-[160px] justify-between shadow-sm"
      >
        <span>{placeholder}</span>
        <ChevronDown size={14} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-[#0f0f0f] border border-border rounded-xl shadow-2xl z-50 overflow-hidden">
          {/* Search */}
          <div className="p-2 border-b border-border flex items-center gap-2">
            <Search size={14} className="text-gray-500 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && query.trim()) {
                  e.preventDefault()
                  handleSelect(query.trim())
                }
              }}
              placeholder="Search or type custom..."
              className="w-full bg-transparent text-sm text-gray-300 placeholder-gray-600 outline-none"
            />
            {query && (
              <button onClick={() => setQuery("")} className="text-gray-600 hover:text-gray-400">
                <X size={12} />
              </button>
            )}
          </div>

          {/* Options list */}
          <div className="max-h-56 overflow-y-auto py-1">
            {!hasOptions && !query ? (
              <div className="px-4 py-3 text-sm text-gray-600 italic text-center">
                {options.length === 0 && (!groups || groups.length === 0) ? emptyMessage : "All options already selected"}
              </div>
            ) : (
              <>
                {groups ? (
                  processedGroups.map(group => (
                    <div key={group.name} className="mb-2 last:mb-0">
                      <div className="px-4 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wider bg-[#1a1a1a]">
                        {group.name}
                      </div>
                      {group.options.map(opt => (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => handleSelect(opt)}
                          className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-zinc-600 hover:text-white transition-colors"
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  ))
                ) : (
                  availableOptions.map(opt => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => handleSelect(opt)}
                      className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-zinc-600 hover:text-white transition-colors"
                    >
                      {opt}
                    </button>
                  ))
                )}
                {query.trim() && !hasExactMatch && (
                  <button
                    type="button"
                    onClick={() => handleSelect(query.trim())}
                    className="w-full text-left px-4 py-2 text-sm text-zinc-400 hover:bg-zinc-600 hover:text-white transition-colors font-medium border-t border-border mt-1 pt-2"
                  >
                    + Add custom "{query.trim()}"
                  </button>
                )}
              </>
            )}
          </div>

          <div className="p-2 border-t border-border text-xs text-gray-600 text-center">
            Click to select • Click outside to close
          </div>
        </div>
      )}
    </div>
  )
}

export function LocationPicker({
  selectedCountries,
  selectedCities,
  onCountriesChange,
  onCitiesChange,
  disabled,
}: LocationPickerProps) {


  const removeCountry = (country: string) => {
    onCountriesChange(selectedCountries.filter(c => c !== country))
    // Also remove cities that belonged to this country
    const removedCities = getCitiesForCountry(country)
    onCitiesChange(selectedCities.filter(city => !removedCities.includes(city)))
  }

  const removeCity = (city: string) => {
    onCitiesChange(selectedCities.filter(c => c !== city))
  }

  const addCountry = (country: string) => {
    if (!selectedCountries.includes(country)) {
      onCountriesChange([...selectedCountries, country])
    }
  }

  const addCity = (city: string) => {
    if (!selectedCities.includes(city)) {
      onCitiesChange([...selectedCities, city])
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">
          Target Locations
        </label>
        <SearchableDropdown
          groups={COUNTRY_GROUPS.map(g => ({ name: g.name, options: g.countries }))}
          selectedValues={selectedCountries}
          placeholder="+ Add country"
          onSelect={addCountry}
          disabled={disabled}
          emptyMessage="No countries found"
        />
      </div>

      <div className="space-y-3">
        {selectedCountries.length === 0 && (
          <div className="p-4 border border-dashed border-white/10 rounded-xl text-center text-sm text-gray-500">
            No countries selected. Add a country to start selecting cities.
          </div>
        )}

        {selectedCountries.map(country => {
          const availableForCountry = getCitiesForCountry(country)
          const selectedForCountry = selectedCities.filter(city => availableForCountry.includes(city))

          return (
            <div key={country} className="bg-black/20 border border-white/5 rounded-xl p-4 flex flex-col gap-3 relative group transition-colors hover:border-white/10">
              {/* Country Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-zinc-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div>
                  <h4 className="font-medium text-zinc-100">{country}</h4>
                </div>
                <button
                  type="button"
                  onClick={() => removeCountry(country)}
                  disabled={disabled}
                  className="text-gray-500 hover:text-zinc-400 transition-colors disabled:opacity-50"
                  title={`Remove ${country}`}
                >
                  <X size={16} />
                </button>
              </div>

              {/* Cities for this country */}
              <div className="pl-4 border-l border-white/5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[9px] text-gray-500 font-bold uppercase tracking-widest">Cities</span>
                  {selectedForCountry.length > 0 && (
                    <span className="text-xs text-gray-600">{selectedForCountry.length} selected</span>
                  )}
                </div>
                
                <div className="flex flex-wrap gap-2">
                  {selectedForCountry.map(city => (
                    <div
                      key={city}
                      className="flex items-center gap-1.5 px-3 py-1 bg-white/[0.02] border border-white/5 rounded-md text-xs text-gray-400 hover:border-white/10 hover:text-gray-300 transition-colors"
                    >
                      <span>{city}</span>
                      <button
                        type="button"
                        onClick={() => removeCity(city)}
                        disabled={disabled}
                        className="text-gray-500 hover:text-white transition-colors disabled:opacity-50"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}

                  <SearchableDropdown
                    options={availableForCountry}
                    selectedValues={selectedCities}
                    placeholder="+ Add city"
                    onSelect={addCity}
                    disabled={disabled}
                    emptyMessage="No more cities available"
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
