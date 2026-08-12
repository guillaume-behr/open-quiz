import { logout } from "@/api/auth"
import { clearStudentSession } from "@/api/student-auth"
import {
    getPublicInformation,
    type PublicInformation,
} from "@/api/public-information"
import { Button } from "@/components/ui/button"
import { CircleAlert, ExternalLink, Trash2 } from "lucide-react"
import { type ReactNode, useEffect, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

const UPDATED_AT = new Date("2026-08-12T00:00:00+02:00")
const LOCAL_STORAGE_KEYS = ["i18nextLng", "vite-ui-theme"]

function usePublicInformation() {
    const [information, setInformation] = useState<PublicInformation | null>(
        null
    )
    const [loadFailed, setLoadFailed] = useState(false)

    useEffect(() => {
        let active = true
        getPublicInformation()
            .then((result) => {
                if (active) setInformation(result)
            })
            .catch(() => {
                if (active) setLoadFailed(true)
            })
        return () => {
            active = false
        }
    }, [])

    return { information, loadFailed }
}

function usePageTitle(title: string) {
    const { t } = useTranslation()
    useEffect(() => {
        const previousTitle = document.title
        document.title = t("legal-page-browser-title", { title })
        return () => {
            document.title = previousTitle
        }
    }, [t, title])
}

function LegalPage({
    titleKey,
    descriptionKey,
    children,
}: {
    titleKey: string
    descriptionKey: string
    children: ReactNode
}) {
    const { t, i18n } = useTranslation()
    const title = t(titleKey)
    usePageTitle(title)
    const updatedAt = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: "long",
        timeZone: "Europe/Paris",
    }).format(UPDATED_AT)

    return (
        <article
            lang={i18n.resolvedLanguage}
            className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-8 sm:py-12"
        >
            <header className="mb-10 border-b pb-8">
                <p className="mb-2 text-sm font-semibold text-primary">
                    {t("legal-page-instance-information")}
                </p>
                <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
                    {title}
                </h1>
                <p className="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">
                    {t(descriptionKey)}
                </p>
                <p className="mt-3 text-sm text-muted-foreground">
                    {t("legal-page-updated-at", { date: updatedAt })}
                </p>
            </header>
            <div className="space-y-10 [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_h2]:mb-3 [&_h2]:text-2xl [&_h2]:font-bold [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-bold [&_li]:leading-7 [&_p]:leading-7">
                {children}
            </div>
        </article>
    )
}

function LoadFailureNotice({ show }: { show: boolean }) {
    const { t } = useTranslation()
    if (!show) return null
    return (
        <div
            className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
            role="alert"
        >
            <CircleAlert
                className="mt-0.5 size-5 shrink-0 text-destructive"
                aria-hidden="true"
            />
            <p>{t("legal-page-load-error")}</p>
        </div>
    )
}

function ConfigValue({
    value,
    pending,
}: {
    value: string | undefined
    pending: boolean
}) {
    const { t } = useTranslation()
    if (pending) {
        return <span aria-busy="true">{t("legal-page-loading")}</span>
    }
    if (!value) {
        return (
            <strong className="text-destructive">
                {t("legal-page-not-configured")}
            </strong>
        )
    }
    return <span className="whitespace-pre-line">{value}</span>
}

function Definition({ term, children }: { term: string; children: ReactNode }) {
    return (
        <div className="grid gap-1 border-b py-4 last:border-b-0 sm:grid-cols-[13rem_1fr] sm:gap-6">
            <dt className="font-semibold">{term}</dt>
            <dd className="min-w-0 text-muted-foreground">{children}</dd>
        </div>
    )
}

function OfficialLink({
    href,
    children,
}: {
    href: string
    children: ReactNode
}) {
    let safeHref: string | null = null
    try {
        const parsed = new URL(href)
        if (parsed.protocol === "http:" || parsed.protocol === "https:") {
            safeHref = parsed.toString()
        }
    } catch {
        // Invalid or relative external links are rendered as plain text.
    }
    if (!safeHref) return <span>{children}</span>

    return (
        <a href={safeHref} target="_blank" rel="noreferrer">
            {children}
            <ExternalLink className="ms-1 inline size-3.5" aria-hidden="true" />
        </a>
    )
}

export function LegalNoticesPage() {
    const { t } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const hostInformationMissing =
        information !== null &&
        (!information.host.name.trim() ||
            !information.host.address.trim() ||
            !information.host.phone?.trim())

    return (
        <LegalPage
            titleKey="legal-notice-title"
            descriptionKey="legal-notice-description"
        >
            <LoadFailureNotice show={loadFailed} />
            {hostInformationMissing ? (
                <div
                    className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
                    role="alert"
                >
                    <CircleAlert
                        className="mt-0.5 size-5 shrink-0 text-destructive"
                        aria-hidden="true"
                    />
                    <p>{t("legal-notice-host-warning")}</p>
                </div>
            ) : null}

            <section>
                <h2>{t("legal-notice-non-professional-title")}</h2>
                <p>{t("legal-notice-non-professional-text")}</p>
            </section>

            <section>
                <h2>{t("legal-notice-hosting-title")}</h2>
                <dl>
                    <Definition term={t("legal-notice-host-name")}>
                        <ConfigValue
                            value={information?.host.name}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("legal-notice-host-address")}>
                        <ConfigValue
                            value={information?.host.address}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("legal-notice-host-phone")}>
                        <ConfigValue
                            value={information?.host.phone}
                            pending={pending}
                        />
                    </Definition>
                </dl>
            </section>

            <section>
                <h2>{t("legal-notice-software-title")}</h2>
                <p>
                    {t("legal-notice-software-before-link")}{" "}
                    <OfficialLink href="https://github.com/guillaume-behr/open-quiz">
                        {t("legal-notice-repository-link")}
                    </OfficialLink>
                    {t("legal-notice-software-after-link")}
                </p>
                <p className="mt-3">{t("legal-notice-educational-content")}</p>
            </section>

            <section>
                <h2>{t("legal-notice-related-title")}</h2>
                <p>{t("legal-notice-related-intro")}</p>
                <ul className="mt-2 list-disc space-y-2 ps-6">
                    <li>
                        <Link to="/privacy">{t("privacy-title")}</Link>
                    </li>
                    <li>
                        <Link to="/accessibility">
                            {t("accessibility-title")}
                        </Link>
                    </li>
                </ul>
            </section>
        </LegalPage>
    )
}

export function PrivacyPage() {
    const { t } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const quizDays = information?.privacy.quiz_result_retention_days
    const reportDays = information?.privacy.problem_report_retention_days

    return (
        <LegalPage
            titleKey="privacy-title"
            descriptionKey="privacy-description"
        >
            <LoadFailureNotice show={loadFailed} />

            <section>
                <h2>{t("privacy-controller-title")}</h2>
                <dl>
                    <Definition term={t("privacy-controller-name")}>
                        <ConfigValue
                            value={information?.privacy.controller_name}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-rights-contact")}>
                        <ConfigValue
                            value={information?.privacy.controller_contact}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-dpo-contact")}>
                        <ConfigValue
                            value={information?.privacy.dpo_contact}
                            pending={pending}
                        />
                    </Definition>
                </dl>
                <p className="mt-4 text-muted-foreground">
                    {t("privacy-controller-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-purposes-title")}</h2>
                <p>{t("privacy-purposes-text")}</p>
            </section>

            <section>
                <h2>{t("privacy-legal-basis-title")}</h2>
                <ConfigValue
                    value={information?.privacy.legal_basis}
                    pending={pending}
                />
                <p className="mt-3 text-muted-foreground">
                    {t("privacy-legal-basis-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-data-title")}</h2>
                <p>{t("privacy-data-text")}</p>
                <p className="mt-3">{t("privacy-data-source")}</p>
            </section>

            <section>
                <h2>{t("privacy-recipients-title")}</h2>
                <ConfigValue
                    value={information?.privacy.recipients}
                    pending={pending}
                />
                <p className="mt-3 text-muted-foreground">
                    {t("privacy-recipients-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-retention-title")}</h2>
                <dl>
                    <Definition term={t("privacy-retention-quiz-label")}>
                        {quizDays === undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            t("privacy-retention-quiz-value", {
                                count: quizDays,
                            })
                        )}
                    </Definition>
                    <Definition term={t("privacy-retention-teachers-label")}>
                        <ConfigValue
                            value={information?.privacy.teacher_data_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-retention-students-label")}>
                        <ConfigValue
                            value={information?.privacy.student_data_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-retention-security-label")}>
                        <ConfigValue
                            value={information?.privacy.security_log_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-retention-reports-label")}>
                        {reportDays === undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            t("privacy-retention-reports-value", {
                                count: reportDays,
                            })
                        )}
                    </Definition>
                </dl>
            </section>

            <section>
                <h2>{t("privacy-decisions-title")}</h2>
                <p>{t("privacy-decisions-text")}</p>
            </section>

            <section>
                <h2>{t("privacy-rights-title")}</h2>
                <p>{t("privacy-rights-text")}</p>
                <p className="mt-3">
                    {t("privacy-complaint-before-link")}{" "}
                    <OfficialLink href="https://www.cnil.fr/fr/plaintes">
                        {t("privacy-cnil-link")}
                    </OfficialLink>
                    {t("privacy-complaint-after-link")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-education-title")}</h2>
                <p>{t("privacy-education-text")}</p>
            </section>
        </LegalPage>
    )
}

export function AccessibilityPage() {
    const { t, i18n } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const updatedAt = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: "long",
    }).format(UPDATED_AT)

    return (
        <LegalPage
            titleKey="accessibility-title"
            descriptionKey="accessibility-description"
        >
            <LoadFailureNotice show={loadFailed} />

            <section className="rounded-lg border-2 border-destructive/40 bg-destructive/5 p-5">
                <h2>{t("accessibility-status-title")}</h2>
                <p className="text-lg font-bold">{t("accessibility-status")}</p>
                <p className="mt-2">{t("accessibility-status-text")}</p>
            </section>

            <section>
                <h2>{t("accessibility-tests-title")}</h2>
                <p>{t("accessibility-tests-text")}</p>
            </section>

            <section>
                <h2>{t("accessibility-statement-title")}</h2>
                <p>{t("accessibility-statement-text", { date: updatedAt })}</p>
                <p className="mt-3">{t("accessibility-technologies-text")}</p>
            </section>

            <section>
                <h2>{t("accessibility-plan-title")}</h2>
                <dl>
                    <Definition term={t("accessibility-scheme-label")}>
                        {information?.accessibility.scheme_url ? (
                            <OfficialLink
                                href={information.accessibility.scheme_url}
                            >
                                {t("accessibility-scheme-link")}
                            </OfficialLink>
                        ) : (
                            <ConfigValue value="" pending={pending} />
                        )}
                    </Definition>
                    <Definition term={t("accessibility-action-label")}>
                        {information?.accessibility.action_plan_url ? (
                            <OfficialLink
                                href={information.accessibility.action_plan_url}
                            >
                                {t("accessibility-action-link")}
                            </OfficialLink>
                        ) : (
                            <ConfigValue value="" pending={pending} />
                        )}
                    </Definition>
                </dl>
            </section>

            <section id="contact" tabIndex={-1}>
                <h2>{t("accessibility-contact-title")}</h2>
                <p>{t("accessibility-contact-text")}</p>
                <p className="mt-3 font-semibold">
                    <ConfigValue
                        value={information?.accessibility.contact}
                        pending={pending}
                    />
                </p>
            </section>

            <section>
                <h2>{t("accessibility-remedies-title")}</h2>
                <p>
                    {t("accessibility-remedies-before-link")}{" "}
                    <OfficialLink href="https://formulaire.defenseurdesdroits.fr/">
                        {t("accessibility-remedies-link")}
                    </OfficialLink>
                    {t("accessibility-remedies-after-link")}
                </p>
            </section>
        </LegalPage>
    )
}

export function CookiesPage() {
    const { t } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const [cleared, setCleared] = useState(false)
    const statusId = useId()
    const maxAge = information?.cookies.authentication_max_age_days

    async function clearLocalData() {
        await logout().catch(() => undefined)
        try {
            for (const key of LOCAL_STORAGE_KEYS) {
                localStorage.removeItem(key)
            }
            clearStudentSession()
        } catch {
            // Browser storage can be disabled while the server session is revoked.
        }
        setCleared(true)
    }

    return (
        <LegalPage
            titleKey="cookies-title"
            descriptionKey="cookies-description"
        >
            <LoadFailureNotice show={loadFailed} />

            <section>
                <h2>{t("cookies-no-tracking-title")}</h2>
                <p>{t("cookies-no-tracking-text")}</p>
            </section>

            <section>
                <h2>{t("cookies-required-title")}</h2>
                <div className="overflow-x-auto">
                    <table className="w-full min-w-[42rem] border-collapse text-left">
                        <caption className="sr-only">
                            {t("cookies-auth-caption")}
                        </caption>
                        <thead>
                            <tr className="border-b">
                                <th className="p-3">
                                    {t("cookies-name-column")}
                                </th>
                                <th className="p-3">
                                    {t("cookies-purpose-column")}
                                </th>
                                <th className="p-3">
                                    {t("cookies-duration-column")}
                                </th>
                                <th className="p-3">
                                    {t("cookies-protection-column")}
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr className="border-b align-top">
                                <td className="p-3 font-mono text-sm">
                                    open_quiz_refresh
                                </td>
                                <td className="p-3">
                                    {t("cookies-auth-purpose")}
                                </td>
                                <td className="p-3">
                                    {maxAge === undefined ? (
                                        <ConfigValue
                                            value=""
                                            pending={!loadFailed}
                                        />
                                    ) : (
                                        t("cookies-auth-duration", {
                                            count: maxAge,
                                        })
                                    )}
                                </td>
                                <td className="p-3">
                                    {t("cookies-auth-protection")}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section>
                <h2>{t("cookies-storage-title")}</h2>
                <div className="overflow-x-auto">
                    <table className="w-full min-w-[48rem] border-collapse text-left">
                        <caption className="sr-only">
                            {t("cookies-storage-caption")}
                        </caption>
                        <thead>
                            <tr className="border-b">
                                <th className="p-3">
                                    {t("cookies-name-column")}
                                </th>
                                <th className="p-3">
                                    {t("cookies-type-column")}
                                </th>
                                <th className="p-3">
                                    {t("cookies-content-column")}
                                </th>
                                <th className="p-3">
                                    {t("cookies-duration-column")}
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            <StorageRow
                                name="i18nextLng"
                                type={t("cookies-local-storage")}
                                purpose={t("cookies-language-purpose")}
                                duration={t("cookies-device-duration")}
                            />
                            <StorageRow
                                name="vite-ui-theme"
                                type={t("cookies-local-storage")}
                                purpose={t("cookies-theme-purpose")}
                                duration={t("cookies-device-duration")}
                            />
                            <StorageRow
                                name="open-quiz-student-access-token"
                                type={t("cookies-session-storage")}
                                purpose={t("cookies-student-auth-purpose")}
                                duration={t("cookies-session-duration")}
                            />
                            <StorageRow
                                name="open-quiz-student-session"
                                type={t("cookies-session-storage")}
                                purpose={t("cookies-activity-purpose")}
                                duration={t("cookies-session-duration")}
                            />
                            <StorageRow
                                name="open-quiz-training-session"
                                type={t("cookies-session-storage")}
                                purpose={t("cookies-activity-purpose")}
                                duration={t("cookies-session-duration")}
                            />
                            <StorageRow
                                name="open-quiz-refresh-proof"
                                type={t("cookies-session-storage")}
                                purpose={t("cookies-auth-purpose")}
                                duration={t("cookies-session-duration")}
                            />
                        </tbody>
                    </table>
                </div>
            </section>

            <section>
                <h2>{t("cookies-clear-title")}</h2>
                <p>
                    {t("cookies-clear-before-link")}{" "}
                    <Link to="/privacy">{t("privacy-title")}</Link>
                    {t("cookies-clear-after-link")}
                </p>
                <Button
                    className="mt-4"
                    variant="outline"
                    onClick={() => void clearLocalData()}
                    aria-describedby={statusId}
                >
                    <Trash2 aria-hidden="true" />
                    {t("cookies-clear-button")}
                </Button>
                <p
                    id={statusId}
                    className="mt-3 text-sm font-medium"
                    role="status"
                >
                    {cleared ? t("cookies-clear-success") : ""}
                </p>
            </section>

            <section>
                <h2>{t("cookies-evolution-title")}</h2>
                <p>{t("cookies-evolution-text")}</p>
            </section>
        </LegalPage>
    )
}

function StorageRow({
    name,
    type,
    purpose,
    duration,
}: {
    name: string
    type: string
    purpose: string
    duration: string
}) {
    return (
        <tr className="border-b align-top">
            <td className="p-3 font-mono text-sm">{name}</td>
            <td className="p-3">{type}</td>
            <td className="p-3">{purpose}</td>
            <td className="p-3">{duration}</td>
        </tr>
    )
}
