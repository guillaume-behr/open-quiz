import {
    createUser,
    getUsers,
    login,
    logout,
    restoreSession,
    verifyTwoFactor,
    type NewUser,
    type TwoFactorChallenge,
    type User,
} from "@/api/api"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { TwoFactorForm } from "@/components/forms/two-factor-form"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
    LoaderCircle,
    LogOut,
    ShieldCheck,
    UserPlus,
    Users,
} from "lucide-react"
import { useEffect, useState, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"

async function requireAdmin(user: User, errorMessage: string): Promise<void> {
    if (!user.is_admin) {
        await logout()
        throw new Error(errorMessage)
    }
}

export function AdminDashboard() {
    const { t } = useTranslation()
    const [currentUser, setCurrentUser] = useState<User | null>(null)
    const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null)
    const [users, setUsers] = useState<User[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState("")
    const [success, setSuccess] = useState("")
    const [isCreating, setIsCreating] = useState(false)

    useEffect(() => {
        restoreSession()
            .then(async (user) => {
                await requireAdmin(user, t("admin-only"))
                const loadedUsers = await getUsers()
                setCurrentUser(user)
                setUsers(loadedUsers)
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
        setUsers(await getUsers())
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
            setUsers((existing) => [created, ...existing])
            setSuccess(t("user-created", { username: created.username }))
            formElement.reset()
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : t("create-user-error")
            )
        } finally {
            setIsCreating(false)
        }
    }

    function handleLogout() {
        void logout().finally(() => {
            setCurrentUser(null)
            setUsers([])
        })
    }

    if (isLoading) {
        return (
            <div className="flex flex-1 items-center justify-center">
                <LoaderCircle className="size-9 animate-spin text-primary" />
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
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-sm font-medium text-primary">
                        {t("administration")}
                    </p>
                    <h1 className="text-3xl font-extrabold">
                        {t("user-management")}
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("signed-in-as", { name: currentUser.display_name })}
                    </p>
                </div>
                <Button variant="outline" onClick={handleLogout}>
                    <LogOut />
                    {t("sign-out")}
                </Button>
            </div>

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
                                minLength={12}
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
                                className="text-sm text-green-700 dark:text-green-400"
                                role="status"
                            >
                                {success}
                            </p>
                        )}

                        <Button type="submit" disabled={isCreating}>
                            {isCreating ? (
                                <LoaderCircle className="animate-spin" />
                            ) : (
                                <UserPlus />
                            )}
                            {isCreating ? t("creating-user") : t("create-user")}
                        </Button>
                    </FieldGroup>
                </form>

                <section className="rounded-2xl border bg-card p-4 shadow-sm sm:p-5">
                    <div className="mb-5 flex items-center gap-3">
                        <div className="rounded-xl bg-primary/10 p-2 text-primary">
                            <Users />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold">{t("users")}</h2>
                            <p className="text-sm text-muted-foreground">
                                {t("user-count", { count: users.length })}
                            </p>
                        </div>
                    </div>

                    <div className="divide-y">
                        {users.map((user) => (
                            <div
                                key={user.id}
                                className="flex items-center justify-between gap-3 py-4 first:pt-0 last:pb-0"
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
                                <span className="shrink-0 rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium text-green-800 dark:bg-green-950 dark:text-green-300">
                                    {t("active")}
                                </span>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    )
}
