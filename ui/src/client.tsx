import { StartClient } from "@tanstack/react-start/client"
import { hydrateRoot } from "react-dom/client"
import { registerSW } from "virtual:pwa-register"

// Keep production tabs on the deployed build. Skip in dev — the SW precaches
// production-only build artifacts that 404 against the dev server.
if (import.meta.env.PROD) {
  registerSW({ immediate: true })
}

hydrateRoot(document, <StartClient />)
