import { AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import React from 'react'

export function friendlyToast(fallback: string, error: unknown) {
  if (import.meta.env.DEV) {
    console.error('FriendlyError caught raw error:', error)
  } else {
    console.error(error)
  }
  toast.error(fallback)
}

export function InlineError({ message }: { message: string }) {
  if (!message) return null
  return (
    <div className="flex items-center gap-2 text-destructive text-sm mt-1">
      <AlertCircle className="h-4 w-4" />
      <span>{message}</span>
    </div>
  )
}
