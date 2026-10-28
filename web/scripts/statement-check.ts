// Checks the statements of a problem package the way the site renders them (FR-PKG-03): KaTeX
// formulas, WaveDrom diagrams, pictures from assets/ that exist. `judge validate` runs it:
//
//   pnpm -C web --silent statement:check <package-dir> <statement.md> [<statement.en.md> ...]
//
// Prints one problem per line, `<file>:<line>:<column>: <reason>`; exits with 1 when there are
// problems and with 2 when it cannot read a file.
import { readFileSync, statSync } from "node:fs";
import path from "node:path";

import { renderStatement } from "../src/lib/statement/render";

const PICTURES = new Set([".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]);

function isFile(file: string): boolean {
  try {
    return statSync(file).isFile();
  } catch {
    return false;
  }
}

function check(packageDir: string, name: string): string[] {
  const markdown = readFileSync(path.join(packageDir, name), "utf8");
  const { messages, assets } = renderStatement(markdown, {
    waveformLabel: "",
    assetUrl: (asset) => asset,
  });
  const problems = messages.map(
    (message) => `${name}:${message.line ?? 1}:${message.column ?? 1}: ${message.reason}`,
  );
  for (const asset of new Set(assets)) {
    if (!PICTURES.has(path.extname(asset).toLowerCase())) {
      problems.push(`${name}: ${asset}: не картинка (${[...PICTURES].join(", ")})`);
    } else if (!isFile(path.join(packageDir, asset))) {
      problems.push(`${name}: нет файла ${asset}`);
    }
  }
  return problems;
}

function main(args: string[]): number {
  const [packageDir, ...names] = args;
  if (packageDir === undefined || names.length === 0) {
    console.error("usage: statement-check <package-dir> <statement.md> [...]");
    return 2;
  }
  let problems: string[];
  try {
    problems = names.flatMap((name) => check(packageDir, name));
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 2;
  }
  for (const problem of problems) console.log(problem);
  return problems.length === 0 ? 0 : 1;
}

process.exitCode = main(process.argv.slice(2));
