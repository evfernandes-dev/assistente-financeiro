import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";

const markdownAsText = {
  name: "markdown-as-text",
  enforce: "pre" as const,
  load(id: string) {
    const filePath = id.split("?")[0];

    if (filePath.endsWith(".md")) {
      return `export default ${JSON.stringify(readFileSync(filePath, "utf8"))};`;
    }

    return null;
  },
};

export default defineConfig({
  plugins: [markdownAsText],
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    testTimeout: 30_000,
    hookTimeout: 30_000,
    clearMocks: true,
    restoreMocks: true,
    unstubGlobals: true,
  },
});
