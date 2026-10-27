// Storybook of the domain components (specs/08 §4): one story per state of components.md. The
// same stories render in the component tests through composeStories (src/test/setup.ts).
import type { StorybookConfig } from "@storybook/nextjs-vite";

const config: StorybookConfig = {
  framework: "@storybook/nextjs-vite",
  stories: ["../src/**/*.stories.tsx"],
  core: { disableTelemetry: true },
  viteFinal(vite) {
    // "use client" of the libraries means nothing to a Vite bundle; its warnings are noise.
    const rolldown = vite.build?.rolldownOptions ?? {};
    const previous = rolldown.onwarn;
    vite.build = {
      ...vite.build,
      rolldownOptions: {
        ...rolldown,
        onwarn(warning, warn) {
          if (warning.code === "MODULE_LEVEL_DIRECTIVE") return;
          if (previous) previous(warning, warn);
          else warn(warning);
        },
      },
    };
    return vite;
  },
};

export default config;
