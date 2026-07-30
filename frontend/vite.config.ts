import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // In sviluppo si costruisce direttamente dove FastAPI serve i file statici;
    // nel Dockerfile si passa VITE_OUT_DIR=dist e il risultato viene copiato.
    outDir: process.env.VITE_OUT_DIR ?? "../app/static",
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      output: {
        // Recharts e' due terzi del bundle e cambia solo quando si aggiorna la
        // dipendenza: in un chunk a parte resta in cache del browser fra i
        // deploy, invece di essere riscaricato a ogni modifica dell'app.
        manualChunks: {
          grafici: ["recharts"],
          react: ["react", "react-dom", "@tanstack/react-query"],
        },
      },
    },
  },
  server: {
    port: 5173,
    // Il backend in sviluppo gira su 8000: il proxy evita ogni questione di
    // CORS e fa sì che il cookie di sessione sia same-origin come in produzione.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
