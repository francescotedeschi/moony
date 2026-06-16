import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import topLevelAwait from "vite-plugin-top-level-await";
import wasm from "vite-plugin-wasm";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_PROXY_TARGET || "http://localhost:8090";

  const wasmPlugins = () => [wasm(), topLevelAwait()];

  return {
    plugins: [...wasmPlugins(), react()],
    worker: {
      format: "es",
      plugins: wasmPlugins,
    },
    server: {
      port: 5173,
      proxy: {
        "/health": apiTarget,
        "/match": apiTarget,
        "/prefetch": apiTarget,
        "/prefetch/l2": apiTarget,
        "/tracks": apiTarget,
        "/catalog": apiTarget,
        "/jamendo": apiTarget,
      },
    },
  };
});
