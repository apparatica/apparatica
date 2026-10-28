// The editor language of a problem by its `language` (ADR-0011): the Monaco language and the
// extension of the file. Monaco ships the Monarch grammar of SystemVerilog.

export interface EditorLanguage {
  /** The Monaco language id. */
  monaco: string;
  extension: string;
}

const LANGUAGES: Record<string, EditorLanguage> = {
  systemverilog: { monaco: "systemverilog", extension: "sv" },
};

const PLAIN: EditorLanguage = { monaco: "plaintext", extension: "txt" };

export function editorLanguage(language: string): EditorLanguage {
  return LANGUAGES[language] ?? PLAIN;
}

/** The name of the solution file: the top module and the extension, `sync_fifo.sv`. */
export function solutionFile(top: string, language: string): string {
  return `${top}.${editorLanguage(language).extension}`;
}
