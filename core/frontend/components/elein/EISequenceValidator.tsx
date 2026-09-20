import React, { useMemo } from "react"
import { motion, AnimatePresence } from "motion/react"
import { AlertTriangle, ShieldAlert } from "lucide-react"
import { useHRTreeStore } from "@campaigns/eiTreeStore"
import type { SeqTreeNode } from "@campaigns/eiTreeStore"

export function EISequenceValidator() {
  const rootNodes = useHRTreeStore(s => s.rootNodes)
  const selectNode = useHRTreeStore(s => s.selectNode)

  const warnings = useMemo(() => {
    const warns: { id: string, nodeId: string, title: string, message: string, type: "error" | "warning" }[] = []

    function traverse(nodes: SeqTreeNode[], parent: SeqTreeNode | null = null, ancestors: string[] = []) {
      for (const node of nodes) {
        
        

        if ((node.type === "send_message" || node.type === "send_ai_message") && parent && (parent.type === "connection_request")) {
          warns.push({
            id: `msg_after_connect_${node.id}`,
            nodeId: node.id,
            type: "error",
            title: "Logical Error: Sending a message before they accept",
            message: "You are trying to send a DM immediately after sending a Connection Request. You must wait for them to accept! Insert an 'If Connected?' node between them."
          })
        }

        if (node.type === "if_connected" && (!node.data.delay || node.data.delay === 0)) {
          warns.push({
            id: `no_delay_connect_${node.id}`,
            nodeId: node.id,
            type: "warning",
            title: "Warning: Missing Delay on Connection Check",
            message: "You are checking if they connected with 0 days of delay. The system will check instantly and fail. Add a delay (e.g. 3-5 days) so they have time to accept."
          })
        }

        

        
        if ((node.type === "connection_request") && ancestors.includes("withdraw_request")) {
          warns.push({
            id: `connect_after_withdraw_${node.id}`,
            nodeId: node.id,
            type: "error",
            title: "LinkedIn Ban Risk: Re-connecting",
            message: "You placed a Connection Request after withdrawing one. LinkedIn explicitly bans you from reconnecting for 3 weeks! Delete this and use 'Find Email' or 'InMail' instead to pivot to cold email."
          })
        }
        
        
        // Rule: Sending message without connection request in history
        if ((node.type === "send_message" || node.type === "send_ai_message") && !ancestors.includes("connection_request") && !ancestors.includes("if_connected")) {
          warns.push({
            id: `msg_without_connect_${node.id}`,
            nodeId: node.id,
            type: "warning",
            title: "LinkedIn Restriction: Messaging non-connections",
            message: "You are sending a DM but haven't sent a Connection Request in this flow. LinkedIn only allows DMs to 1st-degree connections! Only run this sequence on existing connections."
          })
        }

        

        if (node.children) {


          for (const branch of Object.values(node.children || {})) {
            traverse(branch, node, [...ancestors, node.type])
          }
        }
      }
    }

    traverse(rootNodes)
    return warns
  }, [rootNodes])

  if (warnings.length === 0) return null

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-[500px] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence>
        {warnings.map((w) => (
          <motion.div
            key={w.id}
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className={`pointer-events-auto flex items-start gap-3 p-3 rounded-lg border shadow-lg backdrop-blur-md ${
              w.type === "error" 
                ? "bg-red-500/10 border-red-500/20 text-red-500" 
                : "bg-primary/10 border-primary/20 text-primary"
            }`}
          >
            <div className="mt-0.5">
              {w.type === "error" ? <ShieldAlert className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
            </div>
            <div className="flex-1">
              <h4 className="text-xs font-bold tracking-wide uppercase mb-1">{w.title}</h4>
              <p className="text-xs opacity-90 leading-relaxed">{w.message}</p>
              <button 
                onClick={() => selectNode(w.nodeId)}
                className="mt-2 text-[10px] font-semibold underline underline-offset-2 opacity-80 hover:opacity-100 transition-opacity"
              >
                Highlight node
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
