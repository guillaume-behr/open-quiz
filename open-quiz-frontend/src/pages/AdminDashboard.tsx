import {
    createUser,
    getUsers,
    resetUserCredentials,
    updateUserStatus,
} from "@/api/admin"
import { login, logout, restoreSession, verifyTwoFactor } from "@/api/auth"
import { getProblemReports } from "@/api/problem-reports"
import type {
    NewUser,
    ProblemReport,
    TwoFactorChallenge,
    User,
} from "@/api/types"
import { ProblemReportsPanel } from "@/components/admin/problem-reports-panel"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { TwoFactorForm } from "@/components/forms/two-factor-form"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import { errorMessage } from "@/lib/errors"
import {
    LoaderCircle,
    KeyRound,
    LogOut,
    MessageSquareWarning,
    ShieldCheck,
    UserPlus,
    UserCheck,
    UserX,
    Users,
} from "lucide-react"
import { useEffect, useState, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"

async function requireAdmin(user: User, message: string): Promise<void> {
    if (!user.is_admin) {
        await logout()
        throw new Error(message)
    }
}

export function AdminDashboard() {
    const { t } = useTranslation()
    const [currentUser, setCurrentUser] = useState<User | null>(null)
    const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null)
    const [users, setUsers] = useState<User[]>([])
    const [reports, setReports] = useState<ProblemReport[]>([])
    const [usersPage, setUsersPage] = useState(1)
    const [usersTotalPages, setUsersTotalPages] = useState(1)
    const [usersTotal, setUsersTotal] = useState(0)
    const [reportsPage, setReportsPage] = useState(1)
    const [reportsTotalPages, setReportsTotalPages] = useState(1)
    const [reportsTotal, setReportsTotal] = useState(0)
    const [activeSection, setActiveSection] = useState<"users" | "reports">(
        "users"
    )
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState("")
    const [success, setSuccess] = useState("")
    const [isCreating, setIsCreating] = useState(false)
    const [recoveryUser, setRecoveryUser] = useState<User | null>(null)
    const [isUpdatingUser, setIsUpdatingUser] = useState(false)

    async function loadUsers(page: number) {
        const result = await getUsers(page)
        if (result.page > result.totalPages) {
            await loadUsers(result.totalPages)
            return
        }
        setUsers(result.items)
        setUsersPage(result.page)
        setUsersTotalPages(result.totalPages)
        setUsersTotal(result.total)
    }

    async function loadReports(page: number) {
        const result = await getProblemReports(page)
        if (result.page > result.totalPages) {
            await loadReports(result.totalPages)
            return
        }
        setReports(result.items)
        setReportsPage(result.page)
        setReportsTotalPages(result.totalPages)
        setReportsTotal(result.total)
    }

    useEffect(() => {
        restoreSession()
            .then(async (user) => {
                await requireAdmin(user, t("admin-only"))
                const [loadedUsers, loadedReports] = await Promise.all([
                    getUsers(),
                    getProblemReports(),
                ])
                setCurrentUser(user)
                setUsers(loadedUsers.items)
                setUsersTotalPages(loadedUsers.totalPages)
                setUsersTotal(loadedUsers.total)
                setReports(loadedReports.items)
                setReportsTotalPages(loadedReports.totalPages)
                setReportsTotal(loadedReports.total)
            })
            .catch(() => {
                setCurrentUser(null)
            })
            .finally(() => setIsLoading(false))
    }, [t])

    async function handleLogin(username: string, password: string) {
        setChallenge(await login(username, password, "admin"))
    }

    async function handleTwoFactor(code: string) {
        if (!challenge) return
        const user = await verifyTwoFactor(challenge.challenge_token, code)
        await requireAdmin(user, t("admin-only"))
        setCurrentUser(user)
        const [loadedUsers, loadedReports] = await Promise.all([
            getUsers(),
            getProblemReports(),
        ])
        setUsers(loadedUsers.items)
        setUsersTotalPages(loadedUsers.totalPages)
        setUsersTotal(loadedUsers.total)
        setReports(loadedReports.items)
        setReportsTotalPages(loadedReports.totalPages)
        setReportsTotal(loadedReports.total)
        setChallenge(null)
    }

    async function handleCreateUser(event: SyntheticEvent<HTMLFormElement>) {
        event.preventDefault()
        setError("")
        setSuccess("")
        setIsCreating(true)
        const formElement = event.currentTarget
        const form = new FormData(formElement)
        const newUser: NewUser = {
            username: String(form.get("username")),
            display_name: String(form.get("displayName")),
            password: String(form.get("password")),
        }
        try {
            const created = await createUser(newUser)
            await loadUsers(1)
            setSuccess(t("user-created", { username: created.username }))
            formElement.reset()
        } catch (caught) {
            setError(errorMessage(caught, t("create-user-error")))
        } finally {
            setIsCreating(false)
        }
    }

    function replaceUser(updated: User) {
        setUsers((existing) =>
            existing.map((user) => (user.id === updated.id ? updated : user))
        )
    }

    async function handleStatusChange(user: User) {
        setError("")
        setSuccess("")
        setIsUpdatingUser(true)
        try {
            const updated = await updateUserStatus(user.id, !user.is_active)
            replaceUser(updated)
            setSuccess(
                t(updated.is_active ? "user-enabled" : "user-disabled", {
                    username: updated.username,
                })
            )
        } catch (caught) {
            setError(errorMessage(caught, t("user-update-error")))
        } finally {
            setIsUpdatingUser(false)
        }
    }

    async function handleCredentialReset(
        event: SyntheticEvent<HTMLFormElement>
    ) {
        event.preventDefault()
        if (!recoveryUser) return
        const form = new FormData(event.currentTarget)
        setError("")
        setSuccess("")
        setIsUpdatingUser(true)
        try {
            const updated = await resetUserCredentials(
                recoveryUser.id,
                String(form.get("password")),
                true
            )
            replaceUser(updated)
            setRecoveryUser(null)
            setSuccess(
                t("user-credentials-reset", { username: updated.username })
            )
        } catch (caught) {
            setError(errorMessage(caught, t("user-update-error")))
        } finally {
            setIsUpdatingUser(false)
        }
    }

    function handleLogout() {
        void logout().finally(() => {
            setCurrentUser(null)
            setUsers([])
            setReports([])
        })
    }

    if (isLoading) {
        return (
            <div
                className="flex flex-1 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle className="size-9 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )
    }

    if (!currentUser) {
        return (
            <div className="flex flex-1 items-center justify-center px-4">
                {challenge ? (
                    <TwoFactorForm
                        challenge={challenge}
                        onVerify={handleTwoFactor}
                        onCancel={() => setChallenge(null)}
                    />
                ) : (
                    <DashboardLogin
                        onLogin={handleLogin}
                        title={t("admin-login")}
                        instructions={t("admin-login-instructions")}
                    />
                )}
            </div>
        )
    }

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 overflow-y-auto px-4 py-2 sm:px-6 lg:px-10">
            <NavbarAction>
                <Button variant="outline" onClick={handleLogout}>
                    <LogOut />
                    {t("sign-out")}
                </Button>
            </NavbarAction>
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-sm font-medium text-primary">
                        {t("administration")}
                    </p>
                    <h1 className="text-3xl font-extrabold">
                        {t(
                            activeSection === "users"
                                ? "user-management"
                                : "problem-reports"
                        )}
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("signed-in-as", { name: currentUser.display_name })}
                    </p>
                </div>
            </div>

            <nav
                className="flex flex-wrap gap-2 border-b pb-3"
                aria-label={t("admin-sections")}
            >
                <Button
                    variant={activeSection === "users" ? "default" : "outline"}
                    aria-current={
                        activeSection === "users" ? "page" : undefined
                    }
                    onClick={() => setActiveSection("users")}
                >
                    <Users aria-hidden="true" />
                    {t("users")}
                </Button>
                <Button
                    variant={
                        activeSection === "reports" ? "default" : "outline"
                    }
                    aria-current={
                        activeSection === "reports" ? "page" : undefined
                    }
                    onClick={() => setActiveSection("reports")}
                >
                    <MessageSquareWarning aria-hidden="true" />
                    {t("problem-reports")}
                    {reportsTotal > 0 && (
                        <span className="rounded-full bg-background/20 px-1.5 py-0.5 text-xs">
                            {reportsTotal}
                        </span>
                    )}
                </Button>
            </nav>

            {activeSection === "users" ? (
                <>
                    <div className="grid gap-4 lg:grid-cols-[minmax(300px,0.8fr)_minmax(420px,1.2fr)]">
                        <form
                            onSubmit={handleCreateUser}
                            className="h-fit rounded-2xl border bg-card p-4 shadow-sm sm:p-5"
                        >
                            <div className="mb-5 flex items-center gap-3">
                                <div className="rounded-xl bg-primary/10 p-2 text-primary">
                                    <UserPlus />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold">
                                        {t("create-user")}
                                    </h2>
                                    <p className="text-sm text-muted-foreground">
                                        {t("create-user-help")}
                                    </p>
                                </div>
                            </div>

                            <FieldGroup className="gap-4">
                                <Field>
                                    <FieldLabel htmlFor="displayName">
                                        {t("display-name")}
                                    </FieldLabel>
                                    <Input
                                        id="displayName"
                                        name="displayName"
                                        required
                                        maxLength={120}
                                    />
                                </Field>
                                <Field>
                                    <FieldLabel htmlFor="username">
                                        {t("login-id")}
                                    </FieldLabel>
                                    <Input
                                        id="username"
                                        name="username"
                                        required
                                        minLength={3}
                                        maxLength={80}
                                        pattern="[a-zA-Z0-9._-]+"
                                        autoComplete="off"
                                    />
                                </Field>
                                <Field>
                                    <FieldLabel htmlFor="new-password">
                                        {t("login-password")}
                                    </FieldLabel>
                                    <Input
                                        id="new-password"
                                        name="password"
                                        type="password"
                                        required
                                        minLength={16}
                                        maxLength={256}
                                        autoComplete="new-password"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        {t("password-help")}
                                    </p>
                                </Field>
                                {error && (
                                    <p
                                        className="text-sm text-destructive"
                                        role="alert"
                                    >
                                        {error}
                                    </p>
                                )}
                                {success && (
                                    <p
                                        className="text-sm text-emerald-700 dark:text-emerald-300"
                                        role="status"
                                    >
                                        {success}
                                    </p>
                                )}

                                <Button type="submit" disabled={isCreating}>
                                    {isCreating ? (
                                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                    ) : (
                                        <UserPlus />
                                    )}
                                    {isCreating
                                        ? t("creating-user")
                                        : t("create-user")}
                                </Button>
                            </FieldGroup>
                        </form>

                        <section className="rounded-2xl border bg-card p-4 shadow-sm sm:p-5">
                            <div className="mb-5 flex items-center gap-3">
                                <div className="rounded-xl bg-primary/10 p-2 text-primary">
                                    <Users />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold">
                                        {t("users")}
                                    </h2>
                                    <p className="text-sm text-muted-foreground">
                                        {t("user-count", {
                                            count: usersTotal,
                                        })}
                                    </p>
                                </div>
                            </div>

                            <div
                                key={usersPage}
                                className="animate-in divide-y duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
                            >
                                {users.map((user) => (
                                    <div
                                        key={user.id}
                                        className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0"
                                    >
                                        <div className="min-w-0">
                                            <div className="flex min-w-0 flex-wrap items-center gap-2">
                                                <p className="min-w-0 truncate font-semibold">
                                                    {user.display_name}
                                                </p>
                                                {user.is_admin && (
                                                    <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                                                        <ShieldCheck className="size-3" />
                                                        {t("admin")}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="truncate text-sm text-muted-foreground">
                                                @{user.username}
                                            </p>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span
                                                className={
                                                    user.is_active
                                                        ? "rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                                                        : "rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground"
                                                }
                                            >
                                                {t(
                                                    user.is_active
                                                        ? "active"
                                                        : "inactive"
                                                )}
                                            </span>
                                            {!user.is_admin && (
                                                <>
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() =>
                                                            setRecoveryUser(
                                                                user
                                                            )
                                                        }
                                                        disabled={
                                                            isUpdatingUser
                                                        }
                                                    >
                                                        <KeyRound />
                                                        {t("account-recovery")}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() =>
                                                            void handleStatusChange(
                                                                user
                                                            )
                                                        }
                                                        disabled={
                                                            isUpdatingUser
                                                        }
                                                    >
                                                        {user.is_active ? (
                                                            <UserX />
                                                        ) : (
                                                            <UserCheck />
                                                        )}
                                                        {t(
                                                            user.is_active
                                                                ? "disable"
                                                                : "enable"
                                                        )}
                                                    </Button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <Pagination
                                currentPage={usersPage}
                                totalPages={usersTotalPages}
                                onPageChange={(page) => void loadUsers(page)}
                            />
                        </section>
                    </div>
                    <Dialog
                        open={recoveryUser !== null}
                        onOpenChange={(open) => {
                            if (!open && !isUpdatingUser) setRecoveryUser(null)
                        }}
                        title={t("account-recovery")}
                        description={t("account-recovery-help", {
                            username: recoveryUser?.username,
                        })}
                    >
                        <form
                            className="space-y-4"
                            onSubmit={handleCredentialReset}
                        >
                            <Field>
                                <FieldLabel htmlFor="recovery-password">
                                    {t("new-password")}
                                </FieldLabel>
                                <Input
                                    id="recovery-password"
                                    name="password"
                                    type="password"
                                    required
                                    minLength={16}
                                    maxLength={256}
                                    autoComplete="new-password"
                                />
                                <p className="text-xs text-muted-foreground">
                                    {t("account-recovery-security-help")}
                                </p>
                            </Field>
                            <div className="flex justify-end gap-2">
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => setRecoveryUser(null)}
                                    disabled={isUpdatingUser}
                                >
                                    {t("cancel")}
                                </Button>
                                <Button type="submit" disabled={isUpdatingUser}>
                                    {isUpdatingUser ? (
                                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                    ) : (
                                        <KeyRound />
                                    )}
                                    {t("reset-access")}
                                </Button>
                            </div>
                        </form>
                    </Dialog>
                </>
            ) : (
                <ProblemReportsPanel
                    reports={reports}
                    page={reportsPage}
                    totalPages={reportsTotalPages}
                    total={reportsTotal}
                    onPageChange={(page) => void loadReports(page)}
                    onDeleted={() => void loadReports(reportsPage)}
                />
            )}
        </div>
    )
}
