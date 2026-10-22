import { useState } from "react"
import type { KeyboardEvent } from "react"
import { X, Plus, Tag } from "lucide-react"
import useSWR from "swr"
import { fetcher, fetchWithAuth } from "@/lib/apiClient"
import { cn } from "@/lib/utils"

interface AccountTagsProps {
  accountId: string
  initialTags?: string[]
  onTagsChange?: (tags: string[]) => void
}

export default function AccountTags({ accountId, initialTags, onTagsChange }: AccountTagsProps) {
  const { data: tags, mutate } = useSWR<string[]>(
    `/api/elein/accounts/${accountId}/tags`,
    fetcher,
    { fallbackData: initialTags || [], revalidateOnMount: !initialTags }
  )

  const [input, setInput] = useState("")
  const [adding, setAdding] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  const handleAdd = async () => {
    const trimmed = input.trim()
    if (!trimmed) {
      setValidationError('Tag cannot be empty')
      return
    }
    if (trimmed.length > 50) {
      setValidationError('Tag must be 50 characters or less')
      return
    }
    if (tags?.includes(trimmed)) {
      setValidationError('Tag already exists')
      return
    }
    setAdding(true)
    try {
      await fetchWithAuth(`/api/elein/accounts/bulk/add-tag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_ids: [accountId], tag: trimmed })
      })
      setInput("")
      const nextTags = [...(tags || []), trimmed]
      mutate(nextTags, false)
      onTagsChange?.(nextTags)
    } catch (e: any) {
      console.error("Failed to add tag", e)
      setValidationError(e?.message || 'Failed to add tag')
    } finally {
      setAdding(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault()
      handleAdd()
    }
  }

  const handleRemove = async (tag: string) => {
    try {
      await fetchWithAuth(`/api/elein/accounts/bulk/remove-tag`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_ids: [accountId], tag })
      })
      const nextTags = (tags || []).filter(t => t !== tag)
      mutate(nextTags, false)
      onTagsChange?.(nextTags)
    } catch (e: any) {
      console.error("Failed to remove tag", e)
    }
  }

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Tag size={10} className="text-muted-foreground mr-1" />
        {tags?.map(t => (
          <span key={t} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-muted text-[10px] text-muted-foreground font-medium group">
            {t}
            <button onClick={() => handleRemove(t)} className="hover:text-foreground opacity-50 group-hover:opacity-100 transition-opacity">
              <X size={10} />
            </button>
          </span>
        ))}
        <div className="flex items-center ml-1">
          <input
            value={input}
            onChange={e => { setInput(e.target.value); setValidationError(null); }}
            onKeyDown={handleKeyDown}
            placeholder="Add tag..."
            disabled={adding}
            className="w-20 bg-transparent text-[10px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:w-32 transition-all disabled:opacity-50"
          />
        </div>
      </div>
      {validationError && (
        <div className="text-[10px] text-destructive mt-1">{validationError}</div>
      )}
    </div>
  )
}
