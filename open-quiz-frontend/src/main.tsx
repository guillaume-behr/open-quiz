import { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import { useTranslation } from "react-i18next"

import { MainLayout } from "./layouts/main-layout.tsx"
import { HomePage } from "./pages/HomePage.tsx"

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
                    <Route path="/" element={<MainLayout />}>
                        <Route index element={<HomePage />} />
                    </Route>
                </Routes>
            </BrowserRouter>
        </ThemeProvider>
    </StrictMode>
)
