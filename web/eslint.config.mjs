import js from "@eslint/js";
import nextVitals from "eslint-config-next/core-web-vitals";
import storybook from "eslint-plugin-storybook";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "dist/**",
      "coverage/**",
      "storybook-static/**",
      "next-env.d.ts",
      "public/mockServiceWorker.js",
      "src/lib/api/schema.d.ts",
    ],
  },
  js.configs.recommended,
  ...nextVitals,
  tseslint.configs.strict,
  ...storybook.configs["flat/recommended"],
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
);
