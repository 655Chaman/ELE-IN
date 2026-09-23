import { HR_NODE_DEFS } from './eiNodeDefs';
import type { SeqTreeNode } from "@campaigns/eiTreeStore";

const TERMINAL_NODES = ['sequence_end', 'mark_converted', 'mark_not_interested', 'mark_opted_out'];

export function validateTree(rootNodes: SeqTreeNode[]): { errors: Record<string, string[]>, warnings: Record<string, string[]> } {
  const errors: Record<string, string[]> = {};
  const warnings: Record<string, string[]> = {};

  interface PathState {
    connectionStatus: 'unknown' | 'pending' | 'accepted' | 'withdrawn';
    autoWithdrawEnabled?: boolean;
    lastAction: string | null;
    lastMessageDelayAccumulator: number;
    hasSentMessage: boolean;
  }

  function traverse(node: SeqTreeNode, state: PathState, prevNode: SeqTreeNode | null, visited: Set<string> = new Set()) {
    if (visited.has(node.id)) {
      // Cycle detected, stop traversing this path to prevent call stack exceeded crash
      return;
    }
    visited.add(node.id);
    const nodeErrors: string[] = [];
    const nodeWarnings: string[] = [];

    if (node.type === state.lastAction && node.type !== 'sequence_end') {
      nodeErrors.push(`This '${node.type.replace(/_/g, ' ')}' step is identical to the immediate previous step. This is usually a mistake. How to correct: Delete this node or change its action type.`);
    }


    const isMessageNode = node.type.startsWith('send_message') || node.type.startsWith('send_ai_message') || node.type === 'send_meeting_invite' || node.type === 'send_intro_call_invite' || node.type === 'send_inmail' || node.type === 'send_paid_inmail' || node.type === 'send_voice_note';
    
    let nodeDelay = 1;
    const rawDelay = node.data.delay;
    if (rawDelay !== undefined && rawDelay !== null) {
      const parsed = parseFloat(String(rawDelay));
      nodeDelay = isNaN(parsed) ? 1 : Math.ceil(parsed);
    }
    if (nodeDelay < 1) {
      nodeErrors.push("Delay must be at least 1 day to protect your account.");
    }
    
    if (['send_message', 'send_message_with_doc', 'send_message_with_image', 'send_intro_message', 'send_followup', 'send_breakup_message', 'send_reengage_message'].includes(node.type)) {
       if (!node.data.body || typeof node.data.body !== 'string' || node.data.body.trim() === '') {
         nodeErrors.push("Your message body is empty! Leads will receive a blank message. How to correct: Click this node and write a message.");
       }
    } else if (node.type === 'connection_request') {
       if (node.data.note_strategy === "Fixed note") {
         if (!node.data.note || typeof node.data.note !== 'string' || node.data.note.trim() === '') {
           nodeErrors.push("Your connection request is set to 'Fixed note' but has no note! How to correct: Click this node and write a note.");
         } else if (node.data.note.length > 300) {
           nodeErrors.push("Connection requests cannot exceed 300 characters. How to correct: Click this node and shorten your note.");
         }
       }
    /* removed send_message_ab */
    } else if (node.type === 'send_inmail' || node.type === 'send_paid_inmail') {
       if (!node.data.subject || typeof node.data.subject !== 'string' || node.data.subject.trim() === '') {
         nodeErrors.push("InMail subject is empty! How to correct: Click this node and write a subject line.");
       } else if (node.data.subject.length > 200) {
         const len = node.data.subject.length;
         const diff = len - 200;
         nodeErrors.push(`InMail subject is ${new Intl.NumberFormat('en-US').format(len)} characters. LinkedIn's hard limit is 200. Trim ${new Intl.NumberFormat('en-US').format(diff)} characters.`);
       }
       if (!node.data.body || typeof node.data.body !== 'string' || node.data.body.trim() === '') {
         nodeErrors.push("InMail body is empty! How to correct: Click this node and write a message body.");
       } else if (node.data.body.length > 1900) {
         const len = node.data.body.length;
         const diff = len - 1900;
         nodeErrors.push(`InMail body is ${new Intl.NumberFormat('en-US').format(len)} characters. LinkedIn's hard limit is 1,900. Trim ${new Intl.NumberFormat('en-US').format(diff)} characters.`);
       }
    } else if (node.type === 'send_voice_note') {
       if (!node.data.audio_url || typeof node.data.audio_url !== 'string' || node.data.audio_url.trim() === '') {
         nodeErrors.push("Voice note node has no audio URL configured.");
       } else {
         const url = node.data.audio_url.trim();
         if (!url.startsWith("https://")) {
           nodeErrors.push("Audio URL must start with https://. Insecure URLs are not supported.");
         } else {
           const validExts = [".mp3", ".mp4", ".wav", ".ogg", ".m4a", ".webm"];
           const validCDNs = ["drive.google.com", "dropbox.com", "loom.com"];
           const lowerUrl = url.toLowerCase();
           
           let hasValidExt = false;
           try {
             const parsedUrl = new URL(url);
             const pathname = parsedUrl.pathname.toLowerCase();
             hasValidExt = validExts.some(ext => pathname.endsWith(ext));
           } catch {
             hasValidExt = validExts.some(ext => lowerUrl.endsWith(ext) || lowerUrl.includes(ext + "?"));
           }
           
           const hasValidCDN = validCDNs.some(cdn => lowerUrl.includes(cdn));
           if (!hasValidExt && !hasValidCDN) {
             nodeWarnings.push("Audio URL does not appear to point to an audio file. Verify it is a direct audio link.");
           }
         }
       }
    }

    if (['remove_connection', 'endorse_skill', 'recommendation'].includes(node.type) || (isMessageNode && !['send_inmail', 'send_paid_inmail'].includes(node.type))) {
      if (state.connectionStatus === 'unknown') {
         nodeErrors.push(`This action requires a 1st-degree connection. How to correct: If your campaign audience isn't exclusively 1st-degree connections, you need to add a 'Connection Request' or 'If Connected?' check before this step.`);
      } else if (state.connectionStatus === 'pending') {
         nodeErrors.push(`You cannot use '${node.type.replace(/_/g, ' ')}' here because the connection request is still pending. How to correct: Delete this node here, and add it inside the 'ACCEPTED' branch of the Connection Request.`);
      } else if (state.connectionStatus === 'withdrawn') {
         nodeErrors.push(`You cannot use '${node.type.replace(/_/g, ' ')}' here because the connection request was withdrawn. How to correct: Remove this node, or send a new connection request first.`);
      }
    }

    if (node.type === 'withdraw_request') {
      if (state.connectionStatus === 'accepted') {
        nodeErrors.push("You cannot withdraw a connection request that has already been accepted. How to correct: Remove this node, or use 'Remove Connection' instead.");
      } else if (state.connectionStatus === 'unknown' || state.connectionStatus === 'withdrawn') {
        nodeErrors.push("You can only withdraw a connection request if one is currently pending. How to correct: Delete this node here, and add it inside the 'NOT ACCEPTED YET' branch of a Connection Request.");
      } else if (state.autoWithdrawEnabled) {
        nodeErrors.push("You already enabled 'Withdraw connection request' inside the Connection Request node settings. Adding a physical 'Withdraw Request' node is redundant and will cause errors. How to correct: Delete this node, OR turn off the setting in the Connection Request node.");
      }
    }

    if (node.type === 'if_connected') {
      if (state.connectionStatus === 'accepted') {
         nodeErrors.push("The lead is already connected in this path, so checking their status again is redundant. How to correct: Delete this node.");
      }
    }

    if (node.type === 'connection_request') {
      if (state.connectionStatus === 'pending') {
        nodeErrors.push("You already have a pending connection request in this path. Sending another one immediately is invalid. How to correct: Delete this duplicate node, or use 'Withdraw Pending Request' before sending a new one.");
      } else if (state.connectionStatus === 'accepted') {
        nodeErrors.push("You are already connected to leads in this path. Sending a connection request is invalid. How to correct: Delete this duplicate node.");
      }
    }

    if (isMessageNode) {
      if (state.hasSentMessage) {
        const totalDelaySinceLastMsg = state.lastMessageDelayAccumulator + nodeDelay;
        if (totalDelaySinceLastMsg === 0) {
          nodeErrors.push("Sending multiple messages back-to-back with 0 delay risks flagging your account for spam. How to correct: Click this node's settings and set the Delay to 1 day or more.");
        }
      }
    }

    const branches = Object.entries(node.children || {});
    
    const defOutputs = HR_NODE_DEFS[node.type as keyof typeof HR_NODE_DEFS]?.outputs as unknown as string[] || [];
    const expectedBranches: string[] = defOutputs.length > 0 ? defOutputs : (node.type === 'sequence_end' ? [] as string[] : ['then'] as string[]);
    
    // Layer 0: Check for invalid edge labels
    for (const [branchName, childNodes] of branches) {
        if (!expectedBranches.includes(branchName) && childNodes.length > 0) {
            const labelStr = HR_NODE_DEFS[node.type as keyof typeof HR_NODE_DEFS]?.label || node.type;
            const expectedList = expectedBranches.map(b => `'${b}'`).join(', ');
            nodeErrors.push(`The '${labelStr}' node's output must be connected using a ${expectedList} branch — not a generic connection. Delete and re-draw your connection.`);
        }
    }
    
    // Layer 2: Check for missing connections (WARNING)
    if (expectedBranches.length > 1) {
        for (const expBranch of expectedBranches) {
            const childList = node.children?.[expBranch];
            if (!childList || childList.length === 0) {
                const labelStr = HR_NODE_DEFS[node.type as keyof typeof HR_NODE_DEFS]?.label || node.type;
                nodeWarnings.push(`The '${labelStr}' node has a '${expBranch}' branch with no connection. Leads that match this branch will stop here.`);
            }
        }
    }
    
    // Check pure leaf nodes
    if (branches.length === 0) {
      let isPendingAtEnd = state.connectionStatus === 'pending' && !state.autoWithdrawEnabled;
      if (node.type === 'connection_request') {
        isPendingAtEnd = !node.data?.withdraw_enabled;
      } else if (node.type === 'withdraw_request') {
        isPendingAtEnd = false;
      }
      if (isPendingAtEnd) {
        nodeWarnings.push("Infinite Pending Trap: This sequence path ends with a pending connection request that is never withdrawn. LinkedIn limits you to ~1,000 pending requests before shadow-banning your account. How to correct: Enable 'Withdraw connection request' in the connection node settings, OR add a 'Withdraw Request' node at the end of this path.");
      }
    }

    // NEW: Variable Validation
    const ALLOWED_VARIABLES = [
      'first_name', 'last_name', 'company', 'job_title', 'location', 'industry', 'mutual_connections',
      // AI & Enrichment Variables
      'ai_icebreaker', 'ai_sentiment', 'ai_brain_reply', 'best_send_time', 'work_email', 'competitor_detected'
    ];
    
    function extractAllStringValues(obj: Record<string, unknown>): string[] {
      const results: string[] = [];
      for (const val of Object.values(obj)) {
        if (typeof val === 'string') results.push(val);
        else if (val && typeof val === 'object') results.push(...extractAllStringValues(val as Record<string, unknown>));
      }
      return results;
    }

    function checkVariablesInString(text: string | undefined, fieldName: string, customError?: (varName: string) => string) {
      if (!text || typeof text !== 'string') return;
      const matches = [...text.matchAll(/{{\s*([\w.]+)\s*}}/g)];
      for (const match of matches) {
        let varName = match[1].trim();
        // Drop any filter syntax like | fallback
        if (varName.includes('|')) {
          varName = varName.split('|')[0].trim();
        }
        if (!ALLOWED_VARIABLES.includes(varName)) {
           if (customError) {
             nodeErrors.push(customError(varName));
           } else {
             nodeErrors.push(`Invalid variable '{{${varName}}}' found in ${fieldName}. Allowed variables are: ${ALLOWED_VARIABLES.join(', ')}. How to correct: Click this node, remove the invalid text, and use the 'Add variables' dropdown to insert correct ones.`);
           }
        }
      }
    }

    const allStringValues = extractAllStringValues((node.data || {}) as Record<string, unknown>);
    for (const str of allStringValues) {
      checkVariablesInString(str, 'node data');
    }

    // ISSUE #5: Check unprotected variables in messaging fields
    function findUnprotectedVariables(text: string): string[] {
      if (!text) return [];
      const matches = [...text.matchAll(/{{\s*([\w.]+)\s*}}/g)];
      const unprotected: string[] = [];
      for (const match of matches) {
        unprotected.push(match[1]);
      }
      return unprotected;
    }

    const messageFields = ['body', 'body_a', 'body_b', 'body_c', 'note', 'subject', 'fallback'];
    for (const field of messageFields) {
      if (typeof node.data[field] === 'string') {
        const unprotected = findUnprotectedVariables(node.data[field] as string);
        for (const varName of unprotected) {
          // Note: match case-insensitively, wait, findUnprotectedVariables extracted it exactly as typed, trimmed.
          nodeWarnings.push(`Message contains {{${varName}}} with no fallback. If a lead's data is missing this field, broken text will be sent. Add a fallback: {{${varName}|Your fallback}}`);
        }
      }
    }

    if (node.data.fallback_message) {
      checkVariablesInString(node.data.fallback_message as string, 'fallback_message', (badVar) => `Node '${node.type}': fallback_message contains invalid variable {{${badVar}}}. The fallback will crash if the AI fails.`);
    }
    if (node.data.custom_persona) {
      checkVariablesInString(node.data.custom_persona as string, 'custom_persona', (badVar) => `Node '${node.type}': custom_persona contains invalid variable {{${badVar}}}. The fallback will crash if the AI fails.`);
    }

    if (nodeErrors.length > 0) {
      errors[node.id] = nodeErrors;
    }
    if (nodeWarnings.length > 0) {
      warnings[node.id] = nodeWarnings;
    }

    let nextNodeState = { ...state };
    nextNodeState.lastAction = node.type;
    
    if (isMessageNode) {
      nextNodeState.hasSentMessage = true;
      nextNodeState.lastMessageDelayAccumulator = 0;
    } else {
      nextNodeState.lastMessageDelayAccumulator += nodeDelay;
    }

    if (node.type === 'withdraw_request') {
      nextNodeState.connectionStatus = 'withdrawn';
      nextNodeState.autoWithdrawEnabled = false;
    } else if (node.type === 'remove_connection') {
      nextNodeState.connectionStatus = 'unknown';
      nextNodeState.autoWithdrawEnabled = false;
    } else if (node.type === 'connection_request') {
      nextNodeState.autoWithdrawEnabled = !!node.data?.withdraw_enabled;
    }

    for (const [branchName, childNodes] of branches) {
      let nextState = { ...nextNodeState };
      
      if (node.type === 'connection_request') {
        if (branchName.toUpperCase() === 'ACCEPTED') {
          nextState.connectionStatus = 'accepted';
          nextState.autoWithdrawEnabled = false;
        } else if (branchName.toUpperCase() === 'NOT ACCEPTED YET' || branchName.toUpperCase() === 'NOT ACCEPTED') {
          nextState.connectionStatus = 'pending';
        }
      } else if (node.type === 'if_connected') {
        if (branchName.toUpperCase() === 'YES' || branchName.toUpperCase() === 'CONNECTED') {
           nextState.connectionStatus = 'accepted';
           nextState.autoWithdrawEnabled = false;
        }
      }

      if (childNodes.length === 0) {
         if (nextState.connectionStatus === 'pending' && !nextState.autoWithdrawEnabled) {
             nodeWarnings.push(`Infinite Pending Trap: The '${branchName}' branch ends with a pending connection request that is never withdrawn. LinkedIn limits you to ~1,000 pending requests before shadow-banning your account. How to correct: Enable 'Withdraw connection request' in the connection node settings, OR add a 'Withdraw Request' node to this empty branch.`);
         }
      } else {
         for (const child of childNodes) {
           traverse(child, nextState, node, visited);
         }
      }
    }
  }

  for (const root of rootNodes) {
    traverse(root, { connectionStatus: 'unknown', lastAction: null, lastMessageDelayAccumulator: 0, hasSentMessage: false }, null, new Set());
  }

  return { errors, warnings };
}
