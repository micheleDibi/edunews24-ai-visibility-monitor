import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";
import { NonAutenticato } from "./lib/api";

const cache = new QueryClient({
  defaultOptions: {
    queries: {
      // I dati cambiano al massimo una volta all'ora: rileggerli a ogni fuoco
      // della finestra sarebbe traffico inutile su un cruscotto a utente unico.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      // Ritentare un 401 non serve: la sessione non torna da sola.
      retry: (tentativo, errore) => !(errore instanceof NonAutenticato) && tentativo < 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={cache}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
