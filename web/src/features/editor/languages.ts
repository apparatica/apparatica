// The editor language of a problem by its `language` (ADR-0011): the Monaco language, the
// extension of the file and how the tools of the language mark their messages in the console.
// Monaco ships the Monarch grammar of SystemVerilog.

export interface EditorLanguage {
  /** The Monaco language id. */
  monaco: string;
  extension: string;
  /** The solution file as the judge names it in diagnostics; null if unknown. */
  judgeFile: string | null;
  /** Output lines that are warnings or errors of the tools, by their start. */
  outputTones: readonly { start: RegExp; tone: "warning" | "error" }[];
}

const LANGUAGES: Record<string, EditorLanguage> = {
  systemverilog: {
    monaco: "systemverilog",
    extension: "sv",
    judgeFile: "solution.sv",
    // Verilator: `%Warning-WIDTHTRUNC: …`, `%Error: …`.
    outputTones: [
      { start: /^%Error\b/, tone: "error" },
      { start: /^%Warning\b/, tone: "warning" },
    ],
  },
};

const PLAIN: EditorLanguage = {
  monaco: "plaintext",
  extension: "txt",
  judgeFile: null,
  outputTones: [],
};

export function editorLanguage(language: string): EditorLanguage {
  return LANGUAGES[language] ?? PLAIN;
}

/** The name of the solution file: the top module and the extension, `sync_fifo.sv`. */
export function solutionFile(top: string, language: string): string {
  return `${top}.${editorLanguage(language).extension}`;
}

/** A file of a diagnostic is the solution, not the testbench: its lines lead to the editor. */
export function isSolutionFile(file: string | null, language: string): boolean {
  return file !== null && file === editorLanguage(language).judgeFile;
}
