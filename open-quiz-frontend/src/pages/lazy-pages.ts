import { lazy } from "react"

export const StudentDashboard = lazy(() =>
    import("./StudentDashboard.tsx").then(({ StudentDashboard }) => ({
        default: StudentDashboard,
    }))
)

export const ExamPage = lazy(() =>
    import("./ExamPage.tsx").then(({ ExamPage }) => ({
        default: ExamPage,
    }))
)

export const TrainingPage = lazy(() =>
    import("./TrainingPage.tsx").then(({ TrainingPage }) => ({
        default: TrainingPage,
    }))
)

export const TeacherDashboard = lazy(() =>
    import("./TeacherDashboard.tsx").then(({ TeacherDashboard }) => ({
        default: TeacherDashboard,
    }))
)

export const SessionDisplayPage = lazy(() =>
    import("./SessionDisplayPage.tsx").then(({ SessionDisplayPage }) => ({
        default: SessionDisplayPage,
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
