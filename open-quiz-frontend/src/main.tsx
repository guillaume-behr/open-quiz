import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import { MainLayout } from "./layouts/main-layout.tsx"
import { HomePage } from "./pages/HomePage.tsx"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LanguageDirection } from "./components/langage/langage-direction.tsx"
import { Dashboard } from "./pages/Dashboard.tsx"

const queryClient = new QueryClient()

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <QueryClientProvider client={queryClient}>
            <ThemeProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/" element={<MainLayout />}>
                            <Route index element={<HomePage />} />
                            <Route path="dashboard" element={<Dashboard />} />
                        </Route>
                    </Routes>
                </BrowserRouter>
                <LanguageDirection />
            </ThemeProvider>
        </QueryClientProvider>
    </StrictMode>
)
