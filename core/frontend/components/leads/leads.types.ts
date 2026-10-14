export interface LeadList {
  id: string
  name: string
  type: "csv" | "sales_nav" | "linkedin_url" | "search" | "hubspot" | "dynamic"
  row_count: number
  campaign: string | null
  created_at: string
  status?: string
  error_message?: string
}
