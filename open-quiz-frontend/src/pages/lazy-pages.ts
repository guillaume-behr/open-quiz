import { lazy } from "react"

export const HomePage = lazy(() =>
    import("./HomePage.tsx").then(({ HomePage }) => ({
        default: HomePage,
    }))
)

export const Dashboard = lazy(() =>
    import("./Dashboard.tsx").then(({ Dashboard }) => ({
        default: Dashboard,
    }))
)

export const AdminDashboard = lazy(() =>
    import("./AdminDashboard.tsx").then(({ AdminDashboard }) => ({
        default: AdminDashboard,
    }))
)

export const LegalNoticesPage = lazy(() =>
    import("./LegalPages.tsx").then(({ LegalNoticesPage }) => ({
        default: LegalNoticesPage,
    }))
)

export const PrivacyPage = lazy(() =>
    import("./LegalPages.tsx").then(({ PrivacyPage }) => ({
        default: PrivacyPage,
    }))
)

export const AccessibilityPage = lazy(() =>
    import("./LegalPages.tsx").then(({ AccessibilityPage }) => ({
        default: AccessibilityPage,
    }))
)

export const CookiesPage = lazy(() =>
    import("./LegalPages.tsx").then(({ CookiesPage }) => ({
        default: CookiesPage,
    }))
)

export const ReportProblemPage = lazy(() =>
    import("./ReportProblemPage.tsx").then(({ ReportProblemPage }) => ({
        default: ReportProblemPage,
    }))
)

export const NotFoundPage = lazy(() =>
    import("./NotFoundPage.tsx").then(({ NotFoundPage }) => ({
        default: NotFoundPage,
    }))
)
