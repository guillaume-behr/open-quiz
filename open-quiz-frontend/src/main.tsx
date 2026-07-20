import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme-provider.tsx"

import "./lib/i18n.ts"

import HomePage from "./pages/HomePage.tsx"

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<HomePage />} />
                </Routes>
            </BrowserRouter>
        </ThemeProvider>
    </StrictMode>
)
