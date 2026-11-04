import { describe, it, expect } from "bun:test";
import { detectAndDecodeCsv } from "./CSVImport";

describe("Universal Charset & Encoding Normalizer (Phase A Leads)", () => {
  it("Layer 0: correctly decodes standard UTF-8 text", async () => {
    const csvContent = "first_name,last_name,email\nAlice,Smith,alice@example.com\n";
    const file = new File([csvContent], "test.csv", { type: "text/csv" });

    const result = await detectAndDecodeCsv(file);
    expect(result.encoding).toBe("UTF-8");
    expect(result.normalized).toBe(false);
    expect(result.text).toContain("Alice,Smith,alice@example.com");
  });

  it("Layer 1: strips UTF-8 BOM without leaving corrupted leading characters", async () => {
    const bom = new Uint8Array([0xef, 0xbb, 0xbf]);
    const textEncoder = new TextEncoder();
    const contentBytes = textEncoder.encode("first_name,last_name,email\nBob,Jones,bob@example.com\n");
    
    const combined = new Uint8Array(bom.length + contentBytes.length);
    combined.set(bom, 0);
    combined.set(contentBytes, bom.length);

    const file = new File([combined], "bom_test.csv", { type: "text/csv" });
    const result = await detectAndDecodeCsv(file);

    expect(result.encoding).toBe("UTF-8 (BOM)");
    expect(result.normalized).toBe(true);
    expect(result.text.startsWith("first_name")).toBe(true);
    expect(result.text.charCodeAt(0)).not.toBe(0xfeff);
  });

  it("Layer 1 & 2: normalizes Windows-1252 umlauts and special characters into clean UTF-8", async () => {
    // Windows-1252 bytes for: first_name,last_name,email\nJürgen,Müller,juergen@example.com\n
    // In Windows-1252, ü is 0xFC. 0xFC in strict UTF-8 throws an error.
    const win1252Bytes = new Uint8Array([
      102, 105, 114, 115, 116, 95, 110, 97, 109, 101, 44, 108, 97, 115, 116, 95, 110, 97, 109, 101, 44, 101, 109, 97, 105, 108, 10,
      74, 0xfc, 114, 103, 101, 110, 44, 77, 0xfc, 108, 108, 101, 114, 44, 106, 117, 101, 114, 103, 101, 110, 64, 101, 120, 97, 109, 112, 108, 101, 46, 99, 111, 109, 10
    ]);

    const file = new File([win1252Bytes], "windows1252.csv", { type: "text/csv" });
    const result = await detectAndDecodeCsv(file);

    expect(result.encoding).toBe("Windows-1252");
    expect(result.normalized).toBe(true);
    expect(result.text).toContain("Jürgen,Müller");
  });

  it("Layer 1: correctly detects and normalizes UTF-16LE encoded files", async () => {
    const utf16leBom = new Uint8Array([0xff, 0xfe]);
    const csvStr = "first_name,last_name\nSarah,Connor\n";
    const utf16Bytes = new Uint8Array(csvStr.length * 2);
    for (let i = 0; i < csvStr.length; i++) {
      const code = csvStr.charCodeAt(i);
      utf16Bytes[i * 2] = code & 0xff;
      utf16Bytes[i * 2 + 1] = (code >> 8) & 0xff;
    }

    const combined = new Uint8Array(utf16leBom.length + utf16Bytes.length);
    combined.set(utf16leBom, 0);
    combined.set(utf16Bytes, utf16leBom.length);

    const file = new File([combined], "utf16le.csv", { type: "text/csv" });
    const result = await detectAndDecodeCsv(file);

    expect(result.encoding).toBe("UTF-16LE");
    expect(result.normalized).toBe(true);
    expect(result.text).toContain("Sarah,Connor");
  });
});
