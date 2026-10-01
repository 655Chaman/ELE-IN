export interface EINode {
  id: string;
  type: string;
  position?: { x: number; y: number };
  data?: any;
  [key: string]: any;
}

export interface EIEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  [key: string]: any;
}
