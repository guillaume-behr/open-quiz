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
