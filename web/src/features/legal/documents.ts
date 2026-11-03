// The legal documents of the site (FR-AUTH-06, specs/09 §5): Markdown in content/legal/ with the
// operator filled in from GET /config (config/legal.yaml). A first login accepts the editions of
// terms and privacy that /config names; cookies is a list for reference. Server only: the texts
// are read from the disk (next.config.ts traces them into the standalone build).
import { readFile } from "node:fs/promises";
import path from "node:path";

import type { Schemas } from "@/lib/api/client";

export const LEGAL_DOCUMENTS = ["terms", "privacy", "cookies"] as const;
export type LegalDocument = (typeof LEGAL_DOCUMENTS)[number];
export type Operator = Schemas["Operator"];

export function isLegalDocument(value: string): value is LegalDocument {
  return (LEGAL_DOCUMENTS as readonly string[]).includes(value);
}

const DIRECTORY = path.join(process.cwd(), "content", "legal");

/** The text of a document, ready to render. */
export async function legalText(document: LegalDocument, operator: Operator): Promise<string> {
  return fillIn(await readFile(path.join(DIRECTORY, `${document}.md`), "utf-8"), operator);
}

/** `{{operator.<field>}}` → that field of the operator; an unknown placeholder is a bug. */
export function fillIn(text: string, operator: Operator): string {
  return text.replace(/\{\{operator\.(\w+)\}\}/g, (placeholder, field: string) => {
    if (!Object.hasOwn(operator, field)) throw new Error(`unknown placeholder ${placeholder}`);
    return operator[field as keyof Operator];
  });
}
