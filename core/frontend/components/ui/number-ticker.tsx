import { useEffect, useRef } from "react"
import { useInView, useMotionValue, useSpring } from "motion/react"
import { cn } from "@/lib/utils"

export interface NumberTickerProps {
  value: number | string
  direction?: "up" | "down"
  className?: string
  delay?: number // seconds
  decimalPlaces?: number
  format?: boolean
}

export function NumberTicker({
  value,
  direction = "up",
  delay = 0,
  className,
  decimalPlaces = 0,
  format = true,
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const numValue = typeof value === "number" ? value : parseFloat(String(value))
  const safeValue = Number.isFinite(numValue) ? numValue : 0
  const prevValueRef = useRef(safeValue)

  // Calibrate spring physics to crisp 220ms trajectory (stiffness: 280, damping: 28, zeta ~ 0.83)
  const motionValue = useMotionValue(direction === "down" ? safeValue : 0)
  const springValue = useSpring(motionValue, {
    damping: 28,
    stiffness: 280,
  })
  const isInView = useInView(ref, { once: true, margin: "0px" })

  useEffect(() => {
    // Respect system reduced-motion preference
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      if (ref.current) {
        ref.current.textContent = format
          ? Intl.NumberFormat("en-US", {
              minimumFractionDigits: decimalPlaces,
              maximumFractionDigits: decimalPlaces,
            }).format(safeValue)
          : safeValue.toFixed(decimalPlaces)
      }
      return
    }

    if (isInView) {
      const targetVal = direction === "down" ? 0 : safeValue
      // Avoid SWR 30s background re-validation ticking spam if value has not changed
      if (prevValueRef.current === safeValue && motionValue.get() === targetVal) {
        return
      }
      const timer = setTimeout(() => {
        motionValue.set(targetVal)
        prevValueRef.current = safeValue
      }, delay * 1000)
      return () => clearTimeout(timer)
    }
  }, [isInView, delay, safeValue, direction, motionValue, decimalPlaces, format])

  useEffect(() => {
    return springValue.on("change", (latest) => {
      if (ref.current) {
        const rounded = Number(latest.toFixed(decimalPlaces))
        ref.current.textContent = format
          ? Intl.NumberFormat("en-US", {
              minimumFractionDigits: decimalPlaces,
              maximumFractionDigits: decimalPlaces,
            }).format(rounded)
          : rounded.toFixed(decimalPlaces)
      }
    })
  }, [springValue, decimalPlaces, format])

  return (
    <span
      ref={ref}
      className={cn("inline-block tabular-nums font-mono tracking-tight", className)}
      aria-label={String(safeValue)}
    >
      {format
        ? Intl.NumberFormat("en-US", {
            minimumFractionDigits: decimalPlaces,
            maximumFractionDigits: decimalPlaces,
          }).format(direction === "down" ? safeValue : 0)
        : (direction === "down" ? safeValue : 0).toFixed(decimalPlaces)}
    </span>
  )
}
