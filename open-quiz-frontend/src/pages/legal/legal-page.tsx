import { usePageTitle } from "@/hooks/use-page-title"
import { CircleAlert, ExternalLink } from "lucide-react"
import { type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { UPDATED_AT } from "./updated-at"

export function LegalPage({
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

export function LoadFailureNotice({ show }: { show: boolean }) {
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

export function ConfigValue({
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

export function Definition({
    term,
    children,
}: {
    term: string
    children: ReactNode
}) {
    return (
        <div className="grid gap-1 border-b py-4 last:border-b-0 sm:grid-cols-[13rem_1fr] sm:gap-6">
            <dt className="font-semibold">{term}</dt>
            <dd className="min-w-0 text-muted-foreground">{children}</dd>
        </div>
    )
}

export function OfficialLink({
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
