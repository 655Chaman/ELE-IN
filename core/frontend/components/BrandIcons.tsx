import React from 'react';

// Pro-Grade Minimalist Brand Logo (Linear / Vercel Aesthetic)
export const BrandLogo = React.memo(function BrandLogo({ className = "w-7 h-7" }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center bg-zinc-900 border border-zinc-800 rounded-lg p-1.5 shadow-sm ${className}`}>
      <svg viewBox="0 0 24 24" fill="none" className="w-full h-full text-white" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 17L10 11L14 15L20 7M20 7H15M20 7V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
});

// Healthcare (HIPAA): Minimalist Shield & Lock Stroke
export const HipaaLogo = React.memo(function HipaaLogo({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`text-zinc-300 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <rect x="9" y="10" width="6" height="5" rx="1" />
      <path d="M10 10V8a2 2 0 0 1 4 0v2" />
    </svg>
  );
});

// Dental Staffing: Minimalist User Pulse Stroke
export const DentalLogo = React.memo(function DentalLogo({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`text-zinc-300 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 11l-3 3-2-2" />
    </svg>
  );
});

// IT MSP & Cyber: Minimalist Server Nodes Stroke
export const MspLogo = React.memo(function MspLogo({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`text-zinc-300 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
      <line x1="6" y1="6" x2="6.01" y2="6" strokeWidth="2.5" />
      <line x1="6" y1="18" x2="6.01" y2="18" strokeWidth="2.5" />
    </svg>
  );
});

// R&D Tax Credit: Minimalist Metric Chart Stroke
export const RdTaxLogo = React.memo(function RdTaxLogo({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`text-zinc-300 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="20" x2="12" y2="10" />
      <line x1="18" y1="20" x2="18" y2="4" />
      <line x1="6" y1="20" x2="6" y2="16" />
    </svg>
  );
});

// Apify / Apollo: Minimalist Zap Stroke
export const ApifyLogo = React.memo(function ApifyLogo({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={`text-zinc-400 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
});

// Directory: Minimalist Database Folder Stroke
export const DirectoryLogo = React.memo(function DirectoryLogo({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={`text-zinc-400 ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
});
