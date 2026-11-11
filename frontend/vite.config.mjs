// Inventory web app build (replaces Create React App + craco, 2026-11-11). Same commands
// (`yarn start`, `yarn build`) and the same `build/` output that Render publishes.
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // The app reads its switches as process.env.REACT_APP_* (set in Render or a local .env), as under
  // Create React App; they are fixed into the bundle at build time.
  const env = { NODE_ENV: mode === "production" ? "production" : "development", PUBLIC_URL: "",
    ...loadEnv(mode, import.meta.dirname, "REACT_APP_") };
  return {
    plugins: [react()],
    resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
    define: { "process.env": JSON.stringify(env) },
    // Components keep JSX in .js files, as Create React App allowed.
    esbuild: { loader: "jsx", include: /src[\\/].*\.jsx?$/, exclude: [] },
    optimizeDeps: { esbuildOptions: { loader: { ".js": "jsx" } } },
    build: {
      outDir: "build",
      // The production browserslist minimums (package.json): iOS/Safari 15.6, Chrome 103.
      target: ["es2020", "safari15", "ios15", "chrome103"],
      // One bundle, as before (about 1.5 MB, 0.44 MB gzipped); splitting it is separate work.
      chunkSizeWarningLimit: 1800,
    },
    server: { port: 3000 },
  };
});
