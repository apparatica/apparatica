import path from "node:path";

import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const OG_FONTS =
  "./node_modules/@fontsource/ibm-plex-{sans,mono}/files/*-{latin,cyrillic}-*-normal.woff";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // A self-contained server for the web image (web/Dockerfile); the workspace root is traced so
  // that dependencies of the pnpm workspace are included.
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, ".."),
  // Files read from the disk at request time: the legal documents (src/features/legal/documents.ts)
  // and the fonts of the OG pictures (src/features/share/og-image.tsx).
  outputFileTracingIncludes: {
    "/legal/[document]": ["./content/legal/*.md"],
    "/**/opengraph-image": [OG_FONTS],
  },
  // `next dev` must not write AGENTS.md: the instructions for agents live in the repository root.
  agentRules: false,
};

export default withNextIntl(config);
