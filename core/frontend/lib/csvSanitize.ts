/**
 * Paranoia Layer 0 & 2: Neutralizes CSV Formula Injection (CWE-1236).
 * Any cell value beginning with '=', '+', '-', '@', '\t', or '\r' is prefixed
 * with a single quote "'" to prevent arbitrary command execution in spreadsheet readers.
 */
export function sanitizeCsvCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '""'
  }
  let str = String(value).replace(/"/g, '""')
  const trimmed = str.trimStart()
  if (['=', '+', '-', '@', '\t', '\r'].includes(trimmed[0])) {
    str = `'${str}`
  }
  return `"${str}"`
}

export function buildSafeCsv(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const safeHeaders = headers.map(h => sanitizeCsvCell(h)).join(",")
  const safeRows = rows.map(r => r.map(c => sanitizeCsvCell(c)).join(",")).join("\n")
  return `${safeHeaders}\n${safeRows}`
}
