import { Moon, Sun } from "lucide-react"
import { useTheme } from "./ThemeProvider"

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark")
  }

  return (
    <button
      onClick={toggleTheme}
      className={`p-2 rounded-full border border-border shadow-sm bg-background/50 backdrop-blur-md text-foreground hover:bg-muted/50 transition-colors ${className}`}
      title="Toggle Theme"
    >
      {theme === "dark" ? <Sun size={14} strokeWidth={1.5} /> : <Moon size={14} strokeWidth={1.5} />}
    </button>
  )
}
