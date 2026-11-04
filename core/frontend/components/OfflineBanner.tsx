import React, { useState, useEffect } from "react"
import { WifiOff, Wifi, RefreshCw } from "lucide-react"

export const OfflineBanner: React.FC = () => {
  const [isOnline, setIsOnline] = useState<boolean>(() => {
    return typeof navigator !== "undefined" ? navigator.onLine : true
  })
  const [wasOffline, setWasOffline] = useState<boolean>(false)
  const [isChecking, setIsChecking] = useState<boolean>(false)

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      if (wasOffline) {
        // Auto-dismiss the "back online" state after 3 seconds
        const timer = setTimeout(() => setWasOffline(false), 3000)
        return () => clearTimeout(timer)
      }
    }

    const handleOffline = () => {
      setIsOnline(false)
      setWasOffline(true)
    }

    const handleCustomNetworkStatus = (e: Event) => {
      const customEvent = e as CustomEvent<{ isOnline: boolean }>
      if (typeof customEvent.detail?.isOnline === "boolean") {
        if (!customEvent.detail.isOnline) {
          setIsOnline(false)
          setWasOffline(true)
        } else {
          setIsOnline(true)
        }
      }
    }

    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)
    window.addEventListener("elein:network-status", handleCustomNetworkStatus)

    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
      window.removeEventListener("elein:network-status", handleCustomNetworkStatus)
    }
  }, [wasOffline])

  const handleManualCheck = async () => {
    setIsChecking(true)
    try {
      // Direct health ping with 4s timeout
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 4000)
      const res = await fetch("/api/health", { method: "GET", signal: controller.signal })
      clearTimeout(timer)
      if (res.ok || res.status < 500) {
        setIsOnline(true)
        setTimeout(() => setWasOffline(false), 3000)
      } else {
        setIsOnline(false)
      }
    } catch {
      setIsOnline(false)
    } finally {
      setIsChecking(false)
    }
  }

  if (isOnline && !wasOffline) return null

  return (
    <div
      role="alert"
      aria-live="polite"
      className={`w-full py-2.5 px-4 sticky top-0 z-[100] transition-all duration-300 flex items-center justify-between text-xs font-semibold backdrop-blur-md ${
        !isOnline
          ? "bg-amber-500/90 text-amber-950 border-b border-amber-600/30 dark:bg-amber-600/90 dark:text-amber-50"
          : "bg-emerald-600/95 text-white border-b border-emerald-700/30"
      }`}
    >
      <div className="flex items-center gap-2.5 mx-auto max-w-5xl w-full justify-between">
        <div className="flex items-center gap-2">
          {!isOnline ? (
            <WifiOff size={16} className="animate-pulse shrink-0" />
          ) : (
            <Wifi size={16} className="shrink-0" />
          )}
          <span>
            {!isOnline
              ? "You are currently offline. Background actions are paused until your internet connection returns."
              : "Connection restored. Your session and data are now synchronized."}
          </span>
        </div>

        {!isOnline && (
          <button
            type="button"
            onClick={handleManualCheck}
            disabled={isChecking}
            className="px-2.5 py-1 rounded bg-amber-950/15 hover:bg-amber-950/25 dark:bg-black/20 dark:hover:bg-black/30 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shrink-0"
          >
            <RefreshCw size={12} className={isChecking ? "animate-spin" : ""} />
            <span>{isChecking ? "Checking..." : "Retry Connection"}</span>
          </button>
        )}
      </div>
    </div>
  )
}
