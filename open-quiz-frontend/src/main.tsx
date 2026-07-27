import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import { MainLayout } from "./layouts/main-layout.tsx"
import { HomePage } from "./pages/HomePage.tsx"

import { LanguageDirection } from "./components/langage/langage-direction.tsx"
import { AdminDashboard } from "./pages/AdminDashboard.tsx"
import { Dashboard } from "./pages/Dashboard.tsx"

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider>
            <BrowserRouter>
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
            </BrowserRouter>
            <LanguageDirection />
        </ThemeProvider>
    </StrictMode>
)
