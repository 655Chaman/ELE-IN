import { createContext, useContext, useState, useEffect, useRef } from "react";
import type { ReactNode, RefObject } from "react"
import useSWR from "swr"
import { fetcher } from "@/lib/apiClient"
import type { LeadList } from "./leads.types"

type MethodType = LeadList["type"] | "search" | "hubspot" | null;

interface SearchParams {
  keywords: string;
  jobTitles: string[];
  customTitle: string;
  location: string;
  company: string;
  pastCompany: string;
  school: string;
  industries: string[];
  companySize: string[];
  seniority: string[];
  department: string[];
  network: string[];
}

export interface LeadImportState {
  method: MethodType;
  setMethod: (m: MethodType) => void;
  
  name: string;
  setName: (n: string) => void;
  
  urlList: string;
  setUrlList: (u: string) => void;
  
  salesNavUrl: string;
  setSalesNavUrl: (u: string) => void;
  
  file: File | null;
  setFile: (f: File | null) => void;
  
  cleanData: boolean;
  setCleanData: (c: boolean) => void;
  
  targetTimezone: string;
  setTargetTimezone: (t: string) => void;
  
  isSubmitting: boolean;
  setIsSubmitting: (s: boolean) => void;
  
  step: 1 | 2;
  setStep: (s: 1 | 2) => void;
  
  headers: string[];
  setHeaders: (h: string[]) => void;
  
  mappings: {
    first_name: string;
    last_name: string;
    linkedin_url: string;
    company_name: string;
  };
  setMappings: (m: any) => void;
  
  searchParams: SearchParams;
  setSearchParams: (s: SearchParams) => void;
  
  hubspotToken: string;
  setHubspotToken: (t: string) => void;
  
  hubspotConnecting: boolean;
  setHubspotConnecting: (c: boolean) => void;
  
  selectedHubspotList: string;
  setSelectedHubspotList: (l: string) => void;
  
  // SWR data
  billing: any;
  accounts: any[];
  activeAccount: any;
  budget: any;
  isHubspotConnected: boolean;
  hubspotLists: any[];
  mutateHubspotStatus: () => void;
  
  fileInputRef: RefObject<HTMLInputElement | null>;
  
  liveUrl: string;
}

const LeadImportContext = createContext<LeadImportState | undefined>(undefined);

export function LeadImportProvider({ children }: { children: ReactNode }) {
  const { data: billing } = useSWR('/api/elein/workspaces/billing', fetcher)
  const { data: accountsData } = useSWR('/api/elein/accounts', fetcher)
  const accounts = accountsData?.accounts || accountsData || []
  const activeAccount = Array.isArray(accounts) ? accounts.find((a: any) => a.is_active) : null

  const { data: budgetData } = useSWR(
    activeAccount ? `/api/elein/leads/daily-budget?account_id=${activeAccount.id}` : null,
    fetcher,
    { refreshInterval: 30000 }
  )
  const budget = budgetData || { used: 0, limit: 150, remaining: 150 }

  const [cleanData, setCleanData] = useState(false)
  
  const { data: hubspotStatus, mutate: mutateHubspotStatus } = useSWR('/api/elein/hubspot/status', fetcher)
  const isHubspotConnected = hubspotStatus?.connected || false
  const [hubspotConnecting, setHubspotConnecting] = useState(false)
  const [hubspotToken, setHubspotToken] = useState('')
  
  const { data: hubspotListsData } = useSWR(isHubspotConnected ? '/api/elein/hubspot/lists' : null, fetcher)
  const hubspotLists = hubspotListsData?.lists || []
  const [selectedHubspotList, setSelectedHubspotList] = useState('')
  
  const [method, setMethod] = useState<MethodType>(null)
  
  const [name, setName] = useState("")
  const [urlList, setUrlList] = useState("")
  const [salesNavUrl, setSalesNavUrl] = useState("")
  const [targetTimezone, setTargetTimezone] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const [searchParams, setSearchParams] = useState<SearchParams>(() => {
    if (typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem("elein_search_params");
      if (saved) {
        try { return JSON.parse(saved); } catch (e) {}
      }
    }
    return {
      keywords: "",
      jobTitles: [] as string[],
      customTitle: "",
      location: "",
      company: "",
      pastCompany: "",
      school: "",
      industries: [] as string[],
      companySize: [] as string[],
      seniority: [] as string[],
      department: [] as string[],
      network: [] as string[]
    };
  })

  useEffect(() => {
    localStorage.setItem("elein_search_params", JSON.stringify(searchParams));
  }, [searchParams]);
  
  const [step, setStep] = useState<1 | 2>(1)
  const [headers, setHeaders] = useState<string[]>([])
  const [mappings, setMappings] = useState({
    first_name: "",
    last_name: "",
    linkedin_url: "",
    company_name: ""
  })

  const generateSearchUrl = () => {
    const params = new URLSearchParams();
    
    const formatOr = (val: string) => {
      const parts = val.split(',').map(p => p.trim()).filter(Boolean);
      if (parts.length === 0) return null;
      if (parts.length === 1) return `"${parts[0]}"`;
      return `(${parts.map(p => `"${p}"`).join(" OR ")})`;
    };

    if (searchParams.company) {
      const f = formatOr(searchParams.company);
      if (f) params.append("company", f);
    }
    if (searchParams.school) {
      const f = formatOr(searchParams.school);
      if (f) params.append("school", f);
    }
    
    const titleParts = [...searchParams.jobTitles];
    if (searchParams.customTitle) {
       titleParts.push(...searchParams.customTitle.split(',').map((p: any) => p.trim()).filter(Boolean));
    }
    if (titleParts.length > 0) {
      params.append("title", titleParts.length > 1 ? `(${titleParts.map(t => `"${t}"`).join(" OR ")})` : `"${titleParts[0]}"`);
    }

    if (searchParams.network.length > 0) {
      const netMap: Record<string, string> = { "1st degree": "F", "2nd degree": "S", "3rd+ degree": "O" };
      const nets = searchParams.network.map((n: any) => netMap[n]).filter(Boolean);
      if (nets.length > 0) params.append("network", JSON.stringify(nets));
    }
    
    // keywords: only the actual free-text field — NOT a dumping ground for structured filters
    if (searchParams.keywords) {
      params.append("keywords", searchParams.keywords);
    }

    // Structured LinkedIn filters — each as its own URL param
    if (searchParams.location) {
      params.append("geoUrn", searchParams.location);
    }
    if (searchParams.pastCompany) {
      params.append("pastCompany", searchParams.pastCompany);
    }
    if (searchParams.industries.length > 0) {
      params.append("industry", JSON.stringify(searchParams.industries));
    }
    if (searchParams.department.length > 0) {
      params.append("function", JSON.stringify(searchParams.department));
    }
    if (searchParams.seniority.length > 0) {
      params.append("seniority", JSON.stringify(searchParams.seniority));
    }
    
    if (Array.from(params.keys()).length === 0) return "";
    return `https://www.linkedin.com/search/results/people/?${params.toString()}`;
  }

  const liveUrl = generateSearchUrl();

  const value = {
    method, setMethod,
    name, setName,
    urlList, setUrlList,
    salesNavUrl, setSalesNavUrl,
    targetTimezone, setTargetTimezone,
    file, setFile,
    cleanData, setCleanData,
    isSubmitting, setIsSubmitting,
    step, setStep,
    headers, setHeaders,
    mappings, setMappings,
    searchParams, setSearchParams,
    hubspotToken, setHubspotToken,
    hubspotConnecting, setHubspotConnecting,
    selectedHubspotList, setSelectedHubspotList,
    billing, accounts, activeAccount, budget,
    isHubspotConnected, hubspotLists, mutateHubspotStatus,
    fileInputRef, liveUrl
  };

  return (
    <LeadImportContext.Provider value={value}>
      {children}
    </LeadImportContext.Provider>
  )
}

export function useLeadImport() {
  const context = useContext(LeadImportContext);
  if (context === undefined) {
    throw new Error("useLeadImport must be used within a LeadImportProvider");
  }
  return context;
}
