import { useState, useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "motion/react"
import { Search, Terminal, Activity, FileText, Database } from "lucide-react"

const COMMANDS = [
  { id: "status", title: "System Status", subtitle: "View active tasks and pipelines", icon: Activity, path: "/status", color: "text-zinc-400", bg: "bg-zinc-500/10" },
  { id: "review", title: "Review Board", subtitle: "HITL Match & Copy Review", icon: FileText, path: "/review", color: "text-zinc-400", bg: "bg-zinc-500/10" },
  { id: "leads", title: "Leads Vault", subtitle: "View all extracted and enriched leads", icon: Database, path: "/inventory", color: "text-zinc-400", bg: "bg-zinc-500/10" },
  { id: "dashboard", title: "Main Dashboard", subtitle: "Go to market selection", icon: Terminal, path: "/", color: "text-zinc-400", bg: "bg-zinc-500/10" },
]

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [selectedIndex, setSelectedIndex] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setIsOpen((open) => !open)
      }
      if (e.key === "Escape") {
        setIsOpen(false)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  useEffect(() => {
    if (isOpen) {
      setSearch("")
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen])

  const filteredCommands = COMMANDS.filter((cmd) =>
    cmd.title.toLowerCase().includes(search.toLowerCase()) ||
    cmd.subtitle.toLowerCase().includes(search.toLowerCase())
  )

  useEffect(() => {
    setSelectedIndex(0)
  }, [search])

  const handleExecute = (path: string) => {
    setIsOpen(false)
    navigate(path)
  }

  useEffect(() => {
    if (!isOpen) return
    const handleNavigation = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex((i) => (i + 1) % filteredCommands.length)
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex((i) => (i - 1 + filteredCommands.length) % filteredCommands.length)
      } else if (e.key === "Enter" && filteredCommands.length > 0) {
        e.preventDefault()
        handleExecute(filteredCommands[selectedIndex].path)
      }
    }
    window.addEventListener("keydown", handleNavigation)
    return () => window.removeEventListener("keydown", handleNavigation)
  }, [isOpen, filteredCommands, selectedIndex, handleExecute])

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsOpen(false)}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100]"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="fixed top-[20vh] left-1/2 -translate-x-1/2 w-full max-w-xl bg-[#0a0a0a] border border-white/10 shadow-2xl rounded-2xl overflow-hidden z-[101]"
          >
            <div className="flex items-center px-4 py-4 border-b border-white/5 bg-white/[0.02]">
              <Search className="w-5 h-5 text-gray-500 mr-3" />
              <input
                ref={inputRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Type a command or search..."
                className="flex-1 bg-transparent border-none text-lg text-white placeholder-gray-500 focus:outline-none focus:ring-0"
              />
              <div className="flex gap-1">
                <kbd className="px-2 py-1 bg-white/10 rounded text-xs font-mono text-gray-400">esc</kbd>
              </div>
            </div>

            <div className="max-h-[60vh] overflow-y-auto p-2">
              {filteredCommands.length === 0 ? (
                <div className="py-8 text-center text-sm text-gray-500">No commands found.</div>
              ) : (
                filteredCommands.map((cmd, index) => {
                  const Icon = cmd.icon
                  const isSelected = index === selectedIndex
                  return (
                    <button
                      key={cmd.id}
                      onClick={() => handleExecute(cmd.path)}
                      className={`w-full flex items-center text-left px-4 py-3 rounded-xl mb-1 transition-colors ${
                        isSelected ? "bg-white/10" : "hover:bg-white/5"
                      }`}
                    >
                      <div className={`p-2 rounded-lg mr-4 ${cmd.bg}`}>
                        <Icon className={`w-5 h-5 ${cmd.color}`} />
                      </div>
                      <div className="flex-1">
                        <div className={`font-medium ${isSelected ? "text-white" : "text-gray-200"}`}>{cmd.title}</div>
                        <div className="text-xs text-gray-500">{cmd.subtitle}</div>
                      </div>
                      {isSelected && (
                        <div className="text-xs text-gray-400 font-mono">enter</div>
                      )}
                    </button>
                  )
                })
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
