// Apparatica · Bench — темы Monaco для SystemVerilog.
// Подключение: import * as monaco from 'monaco-editor'; registerBenchThemes(monaco); затем theme: 'bench-light' | 'bench-dark'.
// Токены SV берём из Monarch-языка (keyword, type, number, comment, predefined для $-задач). Диагностику линта рисуйте маркерами:
// monaco.editor.setModelMarkers(model, 'lint', [{ severity: monaco.MarkerSeverity.Warning, startLineNumber, startColumn, endLineNumber, endColumn, message }]).
// Переход из консоли «файл:строка»: editor.revealLineInCenter(line); editor.setPosition({ lineNumber: line, column: col }).
export const benchLight = {
  base: 'vs' as const, inherit: false,
  rules: [
    { token: 'keyword',    foreground: '0e7490' },
    { token: 'type',       foreground: '6d28d9' },
    { token: 'number',     foreground: 'a24b0a' },
    { token: 'comment',    foreground: '5a665c', fontStyle: 'italic' },
    { token: 'predefined', foreground: '1d4ed8' },
    { token: 'identifier', foreground: '141a15' },
    { token: 'delimiter',  foreground: '505a52' },
  ],
  colors: {
    'editor.background': '#fbfcf9',
    'editor.foreground': '#141a15',
    'editor.lineHighlightBackground': '#e9ece4',
    'editor.selectionBackground': '#e0f1f5',
    'editorLineNumber.foreground': '#505a52',
    'editorLineNumber.activeForeground': '#141a15',
    'editorCursor.foreground': '#0e7490',
    'editorIndentGuide.background1': '#c3c9bf',
    'editorError.foreground': '#b42318',
    'editorWarning.foreground': '#7a4f00',
  },
};

export const benchDark = {
  base: 'vs-dark' as const, inherit: false,
  rules: [
    { token: 'keyword',    foreground: '22d3ee' },
    { token: 'type',       foreground: 'c4b5fd' },
    { token: 'number',     foreground: 'fbbf24' },
    { token: 'comment',    foreground: '7d887e', fontStyle: 'italic' },
    { token: 'predefined', foreground: '86efac' },
    { token: 'identifier', foreground: 'dfe6df' },
    { token: 'delimiter',  foreground: '8f9b92' },
  ],
  colors: {
    'editor.background': '#090c0a',
    'editor.foreground': '#dfe6df',
    'editor.lineHighlightBackground': '#151a17',
    'editor.selectionBackground': '#0b2a31',
    'editorLineNumber.foreground': '#8f9b92',
    'editorLineNumber.activeForeground': '#dfe6df',
    'editorCursor.foreground': '#22d3ee',
    'editorIndentGuide.background1': '#222a25',
    'editorError.foreground': '#ff7b72',
    'editorWarning.foreground': '#e3b341',
  },
};

export function registerBenchThemes(monaco: { editor: { defineTheme: (name: string, data: any) => void } }) {
  monaco.editor.defineTheme('bench-light', benchLight);
  monaco.editor.defineTheme('bench-dark', benchDark);
}
