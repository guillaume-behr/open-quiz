import { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import HomePage from "./pages/HomePage.tsx"
import { useTranslation } from "react-i18next"

function DocumentLanguage() {
  const { i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language

  useEffect(() => {
    document.documentElement.lang = language
    document.documentElement.dir = i18n.dir(language)
  }, [language, i18n])

  return null
}

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider>
            <DocumentLanguage />
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<HomePage />} />
                </Routes>
            </BrowserRouter>
        </ThemeProvider>
    </StrictMode>
)
