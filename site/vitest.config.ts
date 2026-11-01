import { defineConfig } from "vitest/config";

// Full page suites validate the actual published static output.
export default defineConfig({
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
