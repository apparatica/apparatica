// Two origins for the regression test: the parent page (127.0.0.1) and the waveview site (localhost)
// with the headers the stand sets for it (deploy/Caddyfile, docs/waveview.md).
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".wasm": "application/wasm",
  ".txt": "text/plain; charset=utf-8",
};

/** The headers of the waveview origin; `ancestor` is the origin of the problem page. */
export function waveviewHeaders(ancestor) {
  return {
    "Content-Security-Policy":
      "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; " +
      `connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; frame-ancestors ${ancestor}`,
    // The frame has the opaque origin "null": its module and WASM are CORS requests.
    "Access-Control-Allow-Origin": "*",
    "X-Content-Type-Options": "nosniff",
  };
}

function files(directory, headers = () => ({})) {
  const root = resolve(directory);
  return (request, response) => {
    const extra = headers();
    if (request.method === "OPTIONS") {
      // Some antivirus software adds headers to fetch(), which turns a plain GET into a preflight.
      response.writeHead(204, {
        ...extra,
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      });
      response.end();
      return;
    }
    const path = decodeURIComponent(new URL(request.url, "http://x").pathname);
    const file = resolve(root, `.${path}`);
    let size;
    try {
      size = file.startsWith(root + sep) ? statSync(file).size : undefined;
    } catch {
      size = undefined;
    }
    if (size === undefined) {
      response.writeHead(404, extra);
      response.end();
      return;
    }
    response.writeHead(200, {
      ...extra,
      "Content-Type": TYPES[extname(file)] ?? "application/octet-stream",
      "Content-Length": size,
    });
    createReadStream(file).pipe(response);
  };
}

function listen(server, host) {
  return new Promise((resolve) => server.listen(0, host, () => resolve(server.address().port)));
}

/** Starts both origins; `dist` holds the build (<version>/...). */
export async function serve(dist) {
  const host = createServer(files(fileURLToPath(new URL(".", import.meta.url))));
  const hostOrigin = `http://127.0.0.1:${await listen(host, "127.0.0.1")}`;
  const waveview = createServer(files(dist, () => waveviewHeaders(hostOrigin)));
  const waveviewOrigin = `http://localhost:${await listen(waveview, "localhost")}`;
  return {
    host: hostOrigin,
    waveview: waveviewOrigin,
    close: () => Promise.all([host, waveview].map((s) => new Promise((r) => s.close(r)))),
  };
}
