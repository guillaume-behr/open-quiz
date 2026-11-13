import { logout } from "@/api/auth"
import { usePublicInformation } from "@/hooks/use-public-information"
import {
    clearStudentSession,
    logoutStudent,
    readStudentToken,
} from "@/api/student-auth"
import { Button } from "@/components/ui/button"
import { clearOpenQuizStorage } from "@/lib/device-storage"
import { Trash2 } from "lucide-react"
import { useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"
import { LegalPage, LoadFailureNotice, ConfigValue } from "./legal-page"

export function CookiesPage() {
    const { t } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const [clearStatus, setClearStatus] = useState<
        "idle" | "clearing" | "cleared" | "failed"
    >("idle")
    const statusId = useId()
    const maxAge = information?.cookies.authentication_max_age_days
    const twoFactorTrust = information?.cookies.two_factor_trust_enabled

    async function clearLocalData() {
        setClearStatus("clearing")
        // The server clears the session cookies even from a tab that did not
        // sign in; only a failed request leaves them in place.
        const cookiesCleared = await logout({ forgetBrowser: true })
        const studentToken = readStudentToken()
        if (studentToken) await logoutStudent(studentToken)
        clearStudentSession()
        const storageCleared = clearOpenQuizStorage()
        setClearStatus(cookiesCleared && storageCleared ? "cleared" : "failed")
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
                    <table className="w-full min-w-[42rem] border-collapse text-start">
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
                            {twoFactorTrust ? (
                                <tr className="border-b align-top">
                                    <td className="p-3 font-mono text-sm">
                                        open_quiz_two_factor_trust
                                    </td>
                                    <td className="p-3">
                                        {t("cookies-two-factor-purpose")}
                                    </td>
                                    <td className="p-3">
                                        {t("cookies-two-factor-duration")}
                                    </td>
                                    <td className="p-3">
                                        {t("cookies-two-factor-protection")}
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>
            </section>

            <section>
                <h2>{t("cookies-storage-title")}</h2>
                <div className="overflow-x-auto">
                    <table className="w-full min-w-[48rem] border-collapse text-start">
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
                            <StorageRow
                                name="open-quiz-exam-draft:…"
                                type={t("cookies-session-storage")}
                                purpose={t("cookies-exam-draft-purpose")}
                                duration={t("cookies-session-duration")}
                            />
                            <StorageRow
                                name="open-quiz-teacher-results-view"
                                type={t("cookies-local-storage")}
                                purpose={t("cookies-results-view-purpose")}
                                duration={t("cookies-device-duration")}
                            />
                            <StorageRow
                                name="open-quiz-session-display:…"
                                type={t("cookies-local-storage")}
                                purpose={t("cookies-session-display-purpose")}
                                duration={t("cookies-session-display-duration")}
                            />
                            <StorageRow
                                name="open-quiz-module-reload-at"
                                type={t("cookies-session-storage")}
                                purpose={t("cookies-module-reload-purpose")}
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
                    disabled={clearStatus === "clearing"}
                    onClick={() => void clearLocalData()}
                    aria-describedby={statusId}
                >
                    <Trash2 aria-hidden="true" />
                    {t(
                        clearStatus === "failed"
                            ? "cookies-clear-retry"
                            : "cookies-clear-button"
                    )}
                </Button>
                <p
                    id={statusId}
                    className={
                        clearStatus === "failed"
                            ? "mt-3 text-sm font-medium text-destructive"
                            : "mt-3 text-sm font-medium"
                    }
                    role="status"
                >
                    {clearStatus === "cleared"
                        ? t("cookies-clear-success")
                        : clearStatus === "failed"
                          ? t("cookies-clear-error")
                          : ""}
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
