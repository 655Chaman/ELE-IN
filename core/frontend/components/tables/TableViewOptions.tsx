import * as React from "react"
import { motion } from "motion/react"
import { 
  SlidersHorizontal, 
  Check, 
  RotateCcw, 
  Lock, 
  AlignJustify, 
  Menu, 
  MoveVertical,
  Eye,
  Columns3
} from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

export type TableDensity = "compact" | "standard" | "comfortable"

export interface TableColumnDef {
  id: string
  label: string
  icon?: React.ComponentType<{ className?: string; size?: number }>
  locked?: boolean
  defaultVisible?: boolean
  responsiveBreakpoint?: "sm" | "md" | "lg" | "xl" | "2xl"
}

interface TableViewOptionsProps {
  density: TableDensity
  onDensityChange: (density: TableDensity) => void
  columns: TableColumnDef[]
  visibleColumns: string[]
  onToggleColumn: (columnId: string) => void
  onResetToDefaults: () => void
  storageKey?: string
  className?: string
}

export function TableViewOptions({
  density,
  onDensityChange,
  columns,
  visibleColumns,
  onToggleColumn,
  onResetToDefaults,
  className,
}: TableViewOptionsProps) {
  const [open, setOpen] = React.useState(false)

  const toggleableColumns = columns.filter((c) => !c.locked)
  const activeCount = toggleableColumns.filter((c) => visibleColumns.includes(c.id)).length
  const totalCount = toggleableColumns.length

  const densityOptions: { id: TableDensity; label: string; icon: typeof AlignJustify; desc: string }[] = [
    { id: "compact", label: "Compact", icon: AlignJustify, desc: "High density (py-2)" },
    { id: "standard", label: "Standard", icon: Menu, desc: "Balanced (py-3.5)" },
    { id: "comfortable", label: "Comfortable", icon: MoveVertical, desc: "Spacious (py-5)" },
  ]

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Table display and column density settings"
          className={cn(
            "group flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-border bg-background hover:bg-muted/60 text-xs font-medium text-foreground transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-2xs",
            open && "border-primary/50 bg-muted/40 ring-1 ring-primary/30",
            className
          )}
        >
          <SlidersHorizontal size={13} className="text-muted-foreground group-hover:text-foreground transition-colors" />
          <span className="hidden sm:inline">View</span>
          <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">
            {activeCount}/{totalCount}
          </span>
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        sideOffset={6}
        className="w-76 p-0 bg-card/95 border-border shadow-2xl backdrop-blur-md rounded-xl overflow-hidden divide-y divide-border/60"
      >
        {/* Header */}
        <div className="px-3.5 py-2.5 flex items-center justify-between bg-muted/20">
          <div className="flex items-center gap-2">
            <Columns3 size={14} className="text-primary" />
            <span className="text-xs font-semibold text-foreground">Display &amp; View Options</span>
          </div>
          <button
            type="button"
            onClick={onResetToDefaults}
            title="Reset columns and density to defaults"
            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <RotateCcw size={11} />
            <span>Reset</span>
          </button>
        </div>

        {/* Section 1: Row Density Selector */}
        <div className="p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Row Density
            </span>
            <span className="text-[10px] text-muted-foreground font-mono capitalize">
              {density}
            </span>
          </div>

          <div className="relative grid grid-cols-3 p-1 rounded-lg bg-muted/40 border border-border/50 gap-1">
            {densityOptions.map((opt) => {
              const isSelected = density === opt.id
              const Icon = opt.icon
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onDensityChange(opt.id)}
                  className={cn(
                    "relative z-10 flex flex-col items-center justify-center py-1.5 px-2 rounded-md text-xs font-medium transition-colors cursor-pointer select-none",
                    isSelected ? "text-foreground font-semibold" : "text-muted-foreground hover:text-foreground"
                  )}
                  title={opt.desc}
                >
                  {isSelected && (
                    <motion.div
                      layoutId="table-density-pill"
                      className="absolute inset-0 bg-background border border-border/80 shadow-xs rounded-md -z-10"
                      transition={{ type: "spring", stiffness: 400, damping: 32 }}
                    />
                  )}
                  <Icon size={13} className="mb-0.5" />
                  <span className="text-[11px]">{opt.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Section 2: Visible Columns Checklist */}
        <div className="p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Eye size={12} />
              <span>Visible Columns</span>
            </span>
            <span className="text-[10px] text-muted-foreground font-mono">
              {activeCount} of {totalCount} active
            </span>
          </div>

          <div className="space-y-1 max-h-56 overflow-y-auto pr-1">
            {columns.map((col) => {
              const isVisible = col.locked || visibleColumns.includes(col.id)
              const Icon = col.icon

              return (
                <div
                  key={col.id}
                  onClick={() => {
                    if (!col.locked) onToggleColumn(col.id)
                  }}
                  className={cn(
                    "flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs transition-colors select-none",
                    col.locked
                      ? "opacity-60 cursor-not-allowed bg-muted/10 text-muted-foreground"
                      : isVisible
                      ? "hover:bg-muted/40 text-foreground cursor-pointer"
                      : "hover:bg-muted/20 text-muted-foreground cursor-pointer"
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div
                      className={cn(
                        "w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors",
                        isVisible
                          ? "bg-primary border-primary text-primary-foreground"
                          : "border-border bg-background"
                      )}
                    >
                      {isVisible && <Check size={11} strokeWidth={3} />}
                    </div>

                    {Icon && <Icon size={13} className="shrink-0 text-muted-foreground" />}
                    <span className="truncate text-xs font-medium">{col.label}</span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0 ml-2">
                    {col.responsiveBreakpoint && (
                      <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted/60 text-muted-foreground border border-border/40">
                        {col.responsiveBreakpoint}+
                      </span>
                    )}
                    {col.locked && (
                      <span title="Primary identity column cannot be hidden">
                        <Lock size={11} className="text-muted-foreground/70" />
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Footer info */}
        <div className="px-3.5 py-2 bg-muted/10 text-[10px] text-muted-foreground flex items-center justify-between">
          <span>Viewport auto-adapts on mobile</span>
          <kbd className="font-mono text-[9px] px-1 py-0.2 bg-muted rounded border border-border/60">Esc to close</kbd>
        </div>
      </PopoverContent>
    </Popover>
  )
}
