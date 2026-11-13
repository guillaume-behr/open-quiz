import { StrictMode, Suspense } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Navigate, Route, Routes } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme/theme-provider.tsx"

import "./lib/i18n.ts"

import { MainLayout } from "./layouts/main-layout.tsx"

import { LanguageDirection } from "@/components/language/language-direction"
import { RouteErrorBoundary } from "@/components/error-boundary"
import { RouteFocusManager } from "@/components/navigation/route-focus-manager"
import {
    AccessibilityPage,
    AdminDashboard,
    CookiesPage,
    TeacherPage,
    ExamPage,
    StudentPage,
    LegalNoticesPage,
    NotFoundPage,
    PrivacyPage,
    ReportProblemPage,
    SessionDisplayPage,
    TrainingPage,
} from "./pages/lazy-pages.ts"

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <ThemeProvider>
            <BrowserRouter>
                <RouteFocusManager />
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
                                <Route
                                    index
                                    element={
                                        <Navigate to="/student/login" replace />
                                    }
                                />
                                <Route
                                    path="student/login"
                                    element={<StudentPage page="login" />}
                                />
                                <Route
                                    path="student/dashboard"
                                    element={<StudentPage page="dashboard" />}
                                />
                                <Route
                                    path="student/results"
                                    element={
                                        <StudentPage
                                            page="dashboard"
                                            initialSection="results"
                                        />
                                    }
                                />
                                <Route
                                    path="student/exam"
                                    element={<ExamPage />}
                                />
                                <Route
                                    path="student/training"
                                    element={<TrainingPage />}
                                />
                                <Route
                                    path="teacher/login"
                                    element={<TeacherPage page="login" />}
                                />
                                <Route
                                    path="teacher/dashboard"
                                    element={<TeacherPage page="dashboard" />}
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
                            {/* Outside the shared layout: this view is meant
                                to be projected to the class. */}
                            <Route
                                path="/teacher/session-display/:sessionKey"
                                element={<SessionDisplayPage />}
                            />
                        </Routes>
                    </Suspense>
                </RouteErrorBoundary>
            </BrowserRouter>
            <LanguageDirection />
        </ThemeProvider>
    </StrictMode>
)
