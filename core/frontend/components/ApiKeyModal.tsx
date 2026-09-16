import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "motion/react"
import { X, Cpu, Key, Layers } from "lucide-react"
import type { KeyConfig } from "@/hooks/useDashboard"
import { SelectMenu } from "./SelectMenu"

interface ApiKeyModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (keys: KeyConfig) => void
  initialKeys: KeyConfig
}

const PROVIDERS = [
  { id: "openai", name: "OpenAI", placeholder: "sk-...", defaultModel: "gpt-4o" },
  { id: "nvidia", name: "NVIDIA NIM", placeholder: "nvapi-...", defaultModel: "meta/llama-3.3-70b-instruct" },
  { id: "openrouter", name: "OpenRouter", placeholder: "sk-or-v1-...", defaultModel: "meta-llama/llama-3.3-70b-instruct" },
  { id: "anthropic", name: "Anthropic Claude", placeholder: "sk-ant-...", defaultModel: "claude-3-5-sonnet-20241022" },
  { id: "gemini", name: "Google Gemini", placeholder: "AIzaSy...", defaultModel: "gemini-1.5-pro" },
] as const

export function ApiKeyModal({ isOpen, onClose, onSave, initialKeys }: ApiKeyModalProps) {
  const [keys, setKeys] = useState<KeyConfig>({
    api_key_apify: "",
    api_key_mailsso: "",
    api_key_openai: "",
    llm_provider: "openai",
    api_key_llm: "",
    llm_model: "",
    ...initialKeys
  })

  const modalRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (initialKeys) {
      setKeys({
        api_key_apify: initialKeys.api_key_apify || "",
        api_key_mailsso: initialKeys.api_key_mailsso || "",
        api_key_openai: initialKeys.api_key_openai || "",
        llm_provider: initialKeys.llm_provider || "openai",
        api_key_llm: initialKeys.api_key_llm || initialKeys.api_key_openai || "",
        llm_model: initialKeys.llm_model || ""
      })
    }
  }, [initialKeys])

  // Focus trap and escape to close
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKeyDown)
    modalRef.current?.focus()
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const selectedProvider = PROVIDERS.find(p => p.id === (keys.llm_provider || "openai")) || PROVIDERS[0]

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <motion.div
          ref={modalRef}
          tabIndex={-1}
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 20, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="w-full max-w-lg bg-zinc-950 border border-zinc-800 p-6 shadow-2xl relative outline-none rounded-xl"
        >
          <button 
            onClick={onClose} 
            className="absolute right-4 top-4 text-zinc-400 hover:text-white focus:ring-2 focus:ring-white outline-none rounded p-1"
            aria-label="Close dialog"
          >
            <X size={18} aria-hidden="true" />
          </button>
          
          <div className="flex items-center gap-2 mb-6 border-b border-zinc-800 pb-4">
            <Cpu size={20} className="text-zinc-300" />
            <h2 id="modal-title" className="text-lg font-bold tracking-tight text-white">System API & LLM Configuration</h2>
          </div>
          
          <form onSubmit={(e) => {
            e.preventDefault()
            onSave(keys)
            onClose()
          }}>
            <div className="space-y-4">
              {/* APIFY TOKEN */}
              <div>
                <label htmlFor="apify_key" className="block text-[11px] font-mono text-zinc-400 mb-1.5 uppercase tracking-wider flex items-center gap-1.5">
                  <Key size={12} /> Apify Scraper Token
                </label>
                <input
                  id="apify_key"
                  type="password"
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-500 transition-colors font-mono"
                  value={keys.api_key_apify || ""}
                  onChange={e => setKeys(k => ({ ...k, api_key_apify: e.target.value }))}
                  placeholder="apify_api_..."
                />
              </div>

              {/* LLM PROVIDER SELECTOR */}
              <div className="pt-2 border-t border-zinc-900">
                <label htmlFor="llm_provider" className="block text-[11px] font-mono text-zinc-400 mb-1.5 uppercase tracking-wider flex items-center gap-1.5">
                  <Layers size={12} /> Enrichment & Matchmaking LLM Engine
                </label>
                <SelectMenu
                  value={keys.llm_provider || "openai"}
                  onChange={(val) => setKeys(k => ({ ...k, llm_provider: val as any }))}
                  options={PROVIDERS.map(p => ({ value: p.id, label: p.name }))}
                />
              </div>

              {/* DYNAMIC PROVIDER API KEY */}
              <div>
                <label htmlFor="llm_key" className="block text-[11px] font-mono text-zinc-400 mb-1.5 uppercase tracking-wider">
                  {selectedProvider.name} API Key
                </label>
                <input
                  id="llm_key"
                  type="password"
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-500 transition-colors font-mono"
                  value={keys.api_key_llm || keys.api_key_openai || ""}
                  onChange={e => setKeys(k => ({ ...k, api_key_llm: e.target.value, api_key_openai: e.target.value }))}
                  placeholder={selectedProvider.placeholder}
                />
              </div>

              {/* MODEL OVERRIDE */}
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label htmlFor="llm_model" className="block text-[11px] font-mono text-zinc-400 uppercase tracking-wider">
                    Target Model Name
                  </label>
                  <span className="text-[10px] text-zinc-500 font-mono">Default: {selectedProvider.defaultModel}</span>
                </div>
                <input
                  id="llm_model"
                  type="text"
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-500 transition-colors font-mono"
                  value={keys.llm_model || ""}
                  onChange={e => setKeys(k => ({ ...k, llm_model: e.target.value }))}
                  placeholder={selectedProvider.defaultModel}
                />
              </div>
              
              {/* MAILS.SO KEY */}
              <div className="pt-2 border-t border-zinc-900">
                <label htmlFor="mailsso_key" className="block text-[11px] font-mono text-zinc-400 mb-1.5 uppercase tracking-wider">
                  Mails.so Email Verification Key
                </label>
                <input
                  id="mailsso_key"
                  type="password"
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-zinc-500 transition-colors font-mono"
                  value={keys.api_key_mailsso || ""}
                  onChange={e => setKeys(k => ({ ...k, api_key_mailsso: e.target.value }))}
                  placeholder="mailsso_..."
                />
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-zinc-800">
              <motion.button
                whileTap={{ scale: 0.98 }}
                type="submit"
                className="w-full bg-white text-black font-semibold py-2.5 text-xs rounded-lg hover:bg-zinc-200 transition-colors focus:ring-2 focus:ring-offset-2 focus:ring-offset-background focus:ring-white outline-none shadow-sm font-mono tracking-wider uppercase"
              >
                Save LLM & System Credentials
              </motion.button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
