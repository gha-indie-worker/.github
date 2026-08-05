import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://gha-indie-worker.github.io",
  output: "static",
  build: {
    format: "directory",
  },
});
