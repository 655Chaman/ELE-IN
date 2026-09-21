import React, { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  private handleRefresh = () => {
    window.location.reload();
  };
  
  private handleGoHome = () => {
    // Kept as window.location.href because ErrorBoundary is a class component 
    // outside normal Router hooks context, acting as a hard reset.
    window.location.href = "/";
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#070809] flex flex-col items-center justify-center p-6 text-zinc-300 font-sans">
          <div className="max-w-md w-full bg-[#0d0f11] border border-white/5 rounded-2xl shadow-2xl p-8 text-center space-y-6 relative overflow-hidden">
            {/* Ambient Background Glow */}
            <div className="absolute -top-24 -left-24 w-48 h-48 bg-red-500/10 rounded-full blur-3xl pointer-events-none" />
            
            <div className="mx-auto w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mb-4 relative">
               <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            
            <div className="space-y-2 relative z-10">
              <h1 className="text-2xl font-semibold text-white tracking-tight">Oops, something went wrong</h1>
              <p className="text-sm text-zinc-500">
                A critical component crashed. Our team has been notified. 
                Please try refreshing the page to recover your session.
              </p>
            </div>

            {/* Error snippet (collapsible or just subtle) */}
            <div className="text-left bg-black/40 border border-white/5 rounded-lg p-3 overflow-auto max-h-32 mt-4 relative z-10">
               <details>
                 <summary className="text-xs text-zinc-400 cursor-pointer hover:text-zinc-300">Technical details (click to expand)</summary>
                 <code className="text-[11px] font-mono text-red-400/80 whitespace-pre-wrap mt-2 block">
                    {this.state.error?.message || "Unknown rendering error"}
                 </code>
               </details>
            </div>

            <div className="flex items-center gap-3 pt-2 relative z-10">
              <button 
                onClick={this.handleGoHome}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-white/5 text-white hover:bg-white/10 transition-colors border border-white/5"
              >
                <Home className="w-4 h-4" />
                Go Home
              </button>
              <button 
                onClick={this.handleRefresh}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-white text-black hover:bg-zinc-200 transition-colors shadow-sm"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
