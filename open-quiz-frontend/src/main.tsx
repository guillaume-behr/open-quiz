import { StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import { MainLayout } from "./layouts/main-layout.tsx"

import { LanguageDirection } from "@/components/language/language-direction"
import { AdminDashboard, Dashboard, HomePage } from "./pages/lazy-pages.ts"

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider>
            <BrowserRouter>
                <Suspense
                    fallback={
                        <div
                            className="min-h-screen bg-background"
                            aria-busy="true"
                        />
                    }
                >
                    <Routes>
                        <Route path="/" element={<MainLayout />}>
                            <Route index element={<HomePage />} />
                            <Route path="dashboard" element={<Dashboard />} />
                            <Route
                                path="admin/dashboard"
                                element={<AdminDashboard />}
                            />
                        </Route>
                    </Routes>
                </Suspense>
            </BrowserRouter>
            <LanguageDirection />
        </ThemeProvider>
    </StrictMode>
)
