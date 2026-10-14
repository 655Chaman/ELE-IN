export interface Objection {
  id: string;
  name: string;
  keywords?: string;
  rebuttal: string;
}

export interface Persona {
  id: string;
  name: string;
  pain_points: string;
  value_prop: string;
  tone_tweaks: string;
}

export interface KnowledgeAsset {
  id: string;
  name: string;
  type: "pdf" | "text" | "url";
  status: string;
  error_msg?: string;
  chunk_count?: number;
  created_at?: string;
}
