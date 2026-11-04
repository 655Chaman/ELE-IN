import React from "react"
import { AlertCircle, ArrowRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { Link } from "react-router-dom"

export interface EmptyStateAction {
  label: string
  onClick?: () => void
  href?: string
  icon?: any
}

interface EmptyStateProps {
  title: string
  description: string
  icon?: any
  badge?: string
  action?: EmptyStateAction
  secondaryAction?: EmptyStateAction
  className?: string
  children?: React.ReactNode
}

export function EmptyState({ 
  title, 
  description, 
  icon: Icon = AlertCircle, 
  badge,
  action,
  secondaryAction,
  className,
  children
}: EmptyStateProps) {
  return (
    <div 
      className={cn(
        "flex flex-col items-center justify-center p-8 sm:p-12 text-center rounded-2xl border border-dashed border-border/80 bg-card/40 backdrop-blur-xs transition-all",
        className
      )}
      role="status"
    >
      {badge && (
        <span className="mb-4 inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-muted text-muted-foreground border border-border/60">
          {badge}
        </span>
      )}

      <div className="size-12 rounded-2xl bg-muted/60 border border-border/60 flex items-center justify-center text-muted-foreground mb-4 shadow-xs">
        <Icon className="size-6 stroke-[1.75]" />
      </div>

      <h3 className="text-base font-semibold text-foreground tracking-tight mb-1.5 max-w-md">
        {title}
      </h3>
      
      <p className="text-xs text-muted-foreground leading-relaxed max-w-sm mb-6">
        {description}
      </p>

      {(action || secondaryAction) && (
        <div className="flex flex-wrap items-center justify-center gap-3">
          {action && (
            action.href ? (
              <Link
                to={action.href}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all shadow-xs cursor-pointer"
              >
                {action.icon && <action.icon className="size-3.5" />}
                <span>{action.label}</span>
                <ArrowRight className="size-3" />
              </Link>
            ) : (
              <button
                type="button"
                onClick={action.onClick}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all shadow-xs cursor-pointer"
              >
                {action.icon && <action.icon className="size-3.5" />}
                <span>{action.label}</span>
                <ArrowRight className="size-3" />
              </button>
            )
          )}

          {secondaryAction && (
            secondaryAction.href ? (
              <Link
                to={secondaryAction.href}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-xs font-semibold hover:bg-muted transition-all border border-border/60 cursor-pointer"
              >
                {secondaryAction.icon && <secondaryAction.icon className="size-3.5" />}
                <span>{secondaryAction.label}</span>
              </Link>
            ) : (
              <button
                type="button"
                onClick={secondaryAction.onClick}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-xs font-semibold hover:bg-muted transition-all border border-border/60 cursor-pointer"
              >
                {secondaryAction.icon && <secondaryAction.icon className="size-3.5" />}
                <span>{secondaryAction.label}</span>
              </button>
            )
          )}
        </div>
      )}

      {children}
    </div>
  )
}

