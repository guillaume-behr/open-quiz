import {
    createUser,
    deleteUser,
    getUsers,
    resetUserCredentials,
    updateUserStatus,
} from "@/api/admin"
import { getProblemReports } from "@/api/problem-reports"
import type { NewUser, User } from "@/api/types"
import { ProblemReportsPanel } from "@/components/admin/problem-reports-panel"
import { usePagedList } from "@/hooks/use-paged-list"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { Pagination } from "@/components/ui/pagination"
import { apiErrorMessage } from "@/lib/errors"
import {
    LoaderCircle,
    KeyRound,
    Trash2,
    LogOut,
    MessageSquareWarning,
    ShieldCheck,
    UserPlus,
    UserCheck,
    UserX,
    Users,
} from "lucide-react"
import { useState, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"

function loadUsers(page: number) {
    return getUsers(page)
}

function loadReports(page: number) {
    return getProblemReports(page)
}

/** The administration space of a signed-in administrator. */
export function AdminWorkspace({
    currentUser,
    onLogout,
}: {
    currentUser: User
    onLogout: () => void
}) {
    const { t } = useTranslation()
    const userList = usePagedList(loadUsers, {})
    const reportList = usePagedList(loadReports, {})
    const reportTotal = reportList.data?.total ?? 0
    const [activeSection, setActiveSection] = useState<"users" | "reports">(
        "users"
    )
    const [error, setError] = useState("")
    const [success, setSuccess] = useState("")
    const [isCreating, setIsCreating] = useState(false)
    const [recoveryUser, setRecoveryUser] = useState<User | null>(null)
    const [deletingUser, setDeletingUser] = useState<User | null>(null)
    const [isUpdatingUser, setIsUpdatingUser] = useState(false)

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
            userList.showPage(1)
            userList.reload()
            setSuccess(t("user-created", { username: created.username }))
            formElement.reset()
        } catch (caught) {
            setError(apiErrorMessage(caught, t, t("create-user-error")))
        } finally {
            setIsCreating(false)
        }
    }

    function replaceUser(updated: User) {
        userList.setData(
            (current) =>
                current && {
                    ...current,
                    items: current.items.map((user) =>
                        user.id === updated.id ? updated : user
                    ),
                }
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
            setError(apiErrorMessage(caught, t, t("user-update-error")))
        } finally {
            setIsUpdatingUser(false)
        }
    }

    async function handleDelete() {
        if (!deletingUser) return
        setError("")
        setSuccess("")
        setIsUpdatingUser(true)
        try {
            const { id, username } = deletingUser
            await deleteUser(id)
            setDeletingUser(null)
            userList.reload()
            setSuccess(t("user-deleted", { username }))
        } catch (caught) {
            setError(apiErrorMessage(caught, t, t("user-delete-error")))
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
            setError(apiErrorMessage(caught, t, t("user-update-error")))
        } finally {
            setIsUpdatingUser(false)
        }
    }

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-4 overflow-y-auto px-4 py-2 sm:px-6 lg:px-10">
            <NavbarAction>
                <Button variant="outline" onClick={onLogout}>
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
                    {reportTotal > 0 && (
                        <span className="rounded-full bg-background/20 px-1.5 py-0.5 text-xs">
                            {reportTotal}
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
                                    <PasswordInput
                                        id="new-password"
                                        name="password"
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
                                        className="text-sm text-success"
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
                                            count: userList.data?.total ?? 0,
                                        })}
                                    </p>
                                </div>
                            </div>

                            <div
                                key={userList.page}
                                className="animate-in divide-y duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
                            >
                                {userList.items.map((user) => (
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
                                                        ? "rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success"
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
                                                    <Button
                                                        size="sm"
                                                        variant="destructive"
                                                        onClick={() =>
                                                            setDeletingUser(
                                                                user
                                                            )
                                                        }
                                                        disabled={
                                                            isUpdatingUser
                                                        }
                                                    >
                                                        <Trash2 />
                                                        {t("delete")}
                                                    </Button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <Pagination
                                currentPage={userList.page}
                                totalPages={userList.totalPages}
                                onPageChange={userList.showPage}
                            />
                        </section>
                    </div>
                    <Dialog
                        open={deletingUser !== null}
                        onOpenChange={(open) => {
                            if (!open && !isUpdatingUser) setDeletingUser(null)
                        }}
                        title={t("delete-user")}
                        description={t("delete-user-help", {
                            username: deletingUser?.username,
                        })}
                        size="sm"
                    >
                        <div className="mt-4 flex justify-end gap-2">
                            <Button
                                variant="outline"
                                onClick={() => setDeletingUser(null)}
                                disabled={isUpdatingUser}
                            >
                                {t("cancel")}
                            </Button>
                            <Button
                                variant="destructive"
                                onClick={() => void handleDelete()}
                                disabled={isUpdatingUser}
                            >
                                {isUpdatingUser && (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                )}
                                {t("delete")}
                            </Button>
                        </div>
                    </Dialog>
                    <Dialog
                        open={recoveryUser !== null}
                        onOpenChange={(open) => {
                            if (!open && !isUpdatingUser) setRecoveryUser(null)
                        }}
                        title={t("account-recovery")}
                        description={t("account-recovery-help", {
                            username: recoveryUser?.username,
                        })}
                        size="sm"
                    >
                        <form
                            className="space-y-4"
                            onSubmit={handleCredentialReset}
                        >
                            <Field>
                                <FieldLabel htmlFor="recovery-password">
                                    {t("new-password")}
                                </FieldLabel>
                                <PasswordInput
                                    id="recovery-password"
                                    name="password"
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
                    reports={reportList.items}
                    page={reportList.page}
                    totalPages={reportList.totalPages}
                    total={reportTotal}
                    onPageChange={reportList.showPage}
                    onDeleted={reportList.reload}
                />
            )}
        </div>
    )
}
