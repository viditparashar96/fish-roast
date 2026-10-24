import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"
import { loadPreview, PREVIEW } from "./room/preview"

// `?preview`: the stage with sample messages and no bot (`room/preview.ts`).
if (PREVIEW !== null) loadPreview(PREVIEW)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
