import { StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import { MainLayout } from "./layouts/main-layout.tsx"

import { LanguageDirection } from "@/components/language/language-direction"
import { RouteErrorBoundary } from "@/components/error-boundary"
import {
    AccessibilityPage,
    AdminDashboard,
    CookiesPage,
    Dashboard,
    HomePage,
    LegalNoticesPage,
    NotFoundPage,
    PrivacyPage,
    ReportProblemPage,
} from "./pages/lazy-pages.ts"

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider>
            <BrowserRouter>
                <RouteErrorBoundary>
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
                                <Route
                                    path="dashboard"
                                    element={<Dashboard />}
                                />
                                <Route
                                    path="admin/dashboard"
                                    element={<AdminDashboard />}
                                />
                                <Route
                                    path="legal-notice"
                                    element={<LegalNoticesPage />}
                                />
                                <Route
                                    path="privacy"
                                    element={<PrivacyPage />}
                                />
                                <Route
                                    path="accessibility"
                                    element={<AccessibilityPage />}
                                />
                                <Route
                                    path="cookie-settings"
                                    element={<CookiesPage />}
                                />
                                <Route
                                    path="report-a-problem"
                                    element={<ReportProblemPage />}
                                />
                                <Route path="*" element={<NotFoundPage />} />
                            </Route>
                        </Routes>
                    </Suspense>
                </RouteErrorBoundary>
            </BrowserRouter>
            <LanguageDirection />
        </ThemeProvider>
    </StrictMode>
)
