import {
    createUser,
    deleteUser,
    getUsers,
    resetUserCredentials,
    updateUserStatus,
} from "@/api/admin"
import { getProblemReports } from "@/api/problem-reports"
import type { NewUser, User } from "@/api/types"
import {
    AccountRecoveryDialog,
    CreateTeacherForm,
} from "@/components/admin/teacher-account-forms"
import { ProblemReportsPanel } from "@/components/admin/problem-reports-panel"
import { useAsyncAction } from "@/hooks/use-async-action"
import { usePagedList } from "@/hooks/use-paged-list"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { Button } from "@/components/ui/button"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { FieldError } from "@/components/ui/field"
import { ListStatus } from "@/components/ui/list-status"
import { Pagination } from "@/components/ui/pagination"
import { apiErrorMessage } from "@/lib/errors"
import {
    KeyRound,
    Trash2,
    LogOut,
    MessageSquareWarning,
    ShieldCheck,
    UserCheck,
    UserX,
    Users,
} from "lucide-react"
import { useSectionParam } from "@/hooks/use-section-param"
import { useState, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"

const adminSections = ["users", "reports"] as const

function loadUsers(
    page: number,
    _filters: unknown,
    _focus: unknown,
    signal: AbortSignal
) {
    return getUsers(page, signal)
}

function loadReports(
    page: number,
    _filters: unknown,
    _focus: unknown,
    signal: AbortSignal
) {
    return getProblemReports(page, signal)
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
    const [activeSection, setActiveSection] = useSectionParam(adminSections)
    const [success, setSuccess] = useState("")
    const [recoveryUser, setRecoveryUser] = useState<User | null>(null)
    const [deletingUser, setDeletingUser] = useState<User | null>(null)

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

    // Each action keeps its own error, shown where the action was taken: a
    // dialog's failure inside that dialog, not behind it.
    const creation = useAsyncAction(
        async (formElement: HTMLFormElement) => {
            setSuccess("")
            const form = new FormData(formElement)
            const newUser: NewUser = {
                username: String(form.get("username")),
                display_name: String(form.get("displayName")),
                password: String(form.get("password")),
            }
            const created = await createUser(newUser)
            userList.showPage(1)
            userList.reload()
            setSuccess(t("user-created", { username: created.username }))
            formElement.reset()
        },
        (caught) => apiErrorMessage(caught, t, t("create-user-error"))
    )

    const statusChange = useAsyncAction(
        async (user: User) => {
            setSuccess("")
            const updated = await updateUserStatus(user.id, !user.is_active)
            replaceUser(updated)
            setSuccess(
                t(updated.is_active ? "user-enabled" : "user-disabled", {
                    username: updated.username,
                })
            )
        },
        (caught) => apiErrorMessage(caught, t, t("user-update-error"))
    )

    const deletion = useAsyncAction(
        async (user: User) => {
            setSuccess("")
            await deleteUser(user.id)
            setDeletingUser(null)
            userList.reload()
            setSuccess(t("user-deleted", { username: user.username }))
        },
        (caught) => apiErrorMessage(caught, t, t("user-delete-error"))
    )

    const credentialReset = useAsyncAction(
        async (user: User, password: string) => {
            setSuccess("")
            const updated = await resetUserCredentials(user.id, password, true)
            replaceUser(updated)
            setRecoveryUser(null)
            setSuccess(
                t("user-credentials-reset", { username: updated.username })
            )
        },
        (caught) => apiErrorMessage(caught, t, t("user-update-error"))
    )

    const isUpdatingUser =
        statusChange.isPending ||
        deletion.isPending ||
        credentialReset.isPending

    function handleCreateUser(event: SyntheticEvent<HTMLFormElement>) {
        event.preventDefault()
        void creation.run(event.currentTarget)
    }

    function openDeletion(user: User | null) {
        deletion.setError(null)
        setDeletingUser(user)
    }

    function openRecovery(user: User | null) {
        credentialReset.setError(null)
        setRecoveryUser(user)
    }

    function handleCredentialReset(event: SyntheticEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!recoveryUser) return
        const form = new FormData(event.currentTarget)
        void credentialReset.run(recoveryUser, String(form.get("password")))
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
                        <CreateTeacherForm
                            error={creation.error}
                            success={success}
                            isCreating={creation.isPending}
                            onSubmit={handleCreateUser}
                        />

                        <section className="rounded-2xl border bg-card p-4 shadow-sm sm:p-5">
                            <div className="mb-5 flex items-center gap-3">
                                <div className="rounded-xl bg-primary/10 p-2 text-primary">
                                    <Users />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold">
                                        {t("users")}
                                    </h2>
                                    {userList.data && (
                                        <p className="text-sm text-muted-foreground">
                                            {t("user-count", {
                                                count: userList.data.total,
                                            })}
                                        </p>
                                    )}
                                </div>
                            </div>

                            {statusChange.error && (
                                <FieldError className="mb-4">
                                    {statusChange.error}
                                </FieldError>
                            )}
                            <ListStatus
                                isLoading={
                                    userList.isLoading &&
                                    userList.data === undefined
                                }
                                error={
                                    userList.error
                                        ? t("users-load-error")
                                        : null
                                }
                                onRetry={userList.reload}
                            >
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
                                                                openRecovery(
                                                                    user
                                                                )
                                                            }
                                                            disabled={
                                                                isUpdatingUser
                                                            }
                                                        >
                                                            <KeyRound />
                                                            {t(
                                                                "account-recovery"
                                                            )}
                                                        </Button>
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            onClick={() =>
                                                                void statusChange.run(
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
                                                                openDeletion(
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
                            </ListStatus>
                        </section>
                    </div>
                    <ConfirmDeleteDialog
                        open={deletingUser !== null}
                        title={t("delete-user")}
                        description={t("delete-user-help", {
                            username: deletingUser?.username,
                        })}
                        isBusy={deletion.isPending}
                        error={deletion.error}
                        onClose={() => openDeletion(null)}
                        onConfirm={() =>
                            deletingUser && void deletion.run(deletingUser)
                        }
                    />
                    <AccountRecoveryDialog
                        user={recoveryUser}
                        isBusy={credentialReset.isPending}
                        error={credentialReset.error}
                        onClose={() => openRecovery(null)}
                        onSubmit={handleCredentialReset}
                    />
                </>
            ) : (
                <ProblemReportsPanel
                    isLoading={
                        reportList.isLoading && reportList.data === undefined
                    }
                    loadError={
                        reportList.error
                            ? t("problem-reports-load-error")
                            : null
                    }
                    onRetry={reportList.reload}
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
