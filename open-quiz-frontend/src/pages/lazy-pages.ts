import { lazy } from "react"

export const StudentDashboard = lazy(() =>
    import("./student-dashboard.tsx").then(({ StudentDashboard }) => ({
        default: StudentDashboard,
    }))
)

export const ExamPage = lazy(() =>
    import("./exam-page.tsx").then(({ ExamPage }) => ({
        default: ExamPage,
    }))
)

export const TrainingPage = lazy(() =>
    import("./training-page.tsx").then(({ TrainingPage }) => ({
        default: TrainingPage,
    }))
)

export const TeacherDashboard = lazy(() =>
    import("./teacher-dashboard.tsx").then(({ TeacherDashboard }) => ({
        default: TeacherDashboard,
    }))
)

export const SessionDisplayPage = lazy(() =>
    import("./session-display-page.tsx").then(({ SessionDisplayPage }) => ({
        default: SessionDisplayPage,
    }))
)

export const AdminDashboard = lazy(() =>
    import("./admin-dashboard.tsx").then(({ AdminDashboard }) => ({
        default: AdminDashboard,
    }))
)

export const LegalNoticesPage = lazy(() =>
    import("./legal/legal-notices-page.tsx").then(({ LegalNoticesPage }) => ({
        default: LegalNoticesPage,
    }))
)

export const PrivacyPage = lazy(() =>
    import("./legal/privacy-page.tsx").then(({ PrivacyPage }) => ({
        default: PrivacyPage,
    }))
)

export const AccessibilityPage = lazy(() =>
    import("./legal/accessibility-page.tsx").then(({ AccessibilityPage }) => ({
        default: AccessibilityPage,
    }))
)

export const CookiesPage = lazy(() =>
    import("./legal/cookies-page.tsx").then(({ CookiesPage }) => ({
        default: CookiesPage,
    }))
)

export const ReportProblemPage = lazy(() =>
    import("./report-problem-page.tsx").then(({ ReportProblemPage }) => ({
        default: ReportProblemPage,
    }))
)

export const NotFoundPage = lazy(() =>
    import("./not-found-page.tsx").then(({ NotFoundPage }) => ({
        default: NotFoundPage,
    }))
)
