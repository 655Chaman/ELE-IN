import { AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

export function EmptyState({ title, description, icon: Icon = AlertCircle, className }: { 
  title: string, 
  description: string, 
  icon?: any,
  className?: string 
}) {
  return (
    <div 
      className={cn("flex flex-col items-center justify-center p-8 text-center border border-dashed border-border rounded-xl text-gray-500", className)}
      role="status"
    >
      <Icon className="w-8 h-8 mb-4 opacity-50" />
      <h3 className="text-sm font-medium text-gray-300">{title}</h3>
      <p className="mt-1 text-xs">{description}</p>
    </div>
  )
}
