import { Button } from "@/components/ui/button"
import { FieldError } from "@/components/ui/field"
import { Eye, UserRound } from "lucide-react"
import { useTranslation } from "react-i18next"

type FullscreenPromptProps = {
    studentName: string
    error: string | null
    onEnterFullscreen: () => void
}

export function FullscreenPrompt({
    studentName,
    error,
    onEnterFullscreen,
}: FullscreenPromptProps) {
    const { t } = useTranslation()

    return (
        <div className="flex w-full max-w-lg flex-col gap-5 rounded-2xl border bg-secondary px-8 py-10 text-center shadow-lg">
            <StudentNameBadge name={studentName} />
            <p className="text-2xl font-bold">{t("fullscreen-required")}</p>
            <p className="text-muted-foreground">
                {t("fullscreen-required-help")}
            </p>
            <MonitoringNotice />
            <Button size="lg" onClick={onEnterFullscreen}>
                {t("enter-fullscreen")}
            </Button>
            {error && <FieldError>{error}</FieldError>}
        </div>
    )
}

/**
 * The events reported to the teacher are named before the exam starts: the
 * footer, and with it the privacy page, is hidden once the student is in the
 * exam, so this screen is the last place the information can be given.
 */
export function MonitoringNotice() {
    const { t } = useTranslation()

    return (
        <div className="flex gap-3 rounded-lg border bg-background/60 p-4 text-start">
            <Eye className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
            <div className="space-y-2 text-sm text-muted-foreground">
                <p>{t("exam-monitoring-notice")}</p>
                <p>
                    <a
                        className="font-medium text-primary underline underline-offset-4"
                        href="/privacy"
                        target="_blank"
                        rel="noreferrer"
                    >
                        {t("privacy")}
                    </a>
                </p>
            </div>
        </div>
    )
}

export function StudentNameBadge({ name }: { name: string }) {
    return (
        <div className="fixed start-4 top-4 z-50 flex max-w-[calc(100vw-10rem)] items-center gap-2 rounded-lg border bg-background/95 px-4 py-2.5 text-base font-bold shadow-sm backdrop-blur sm:text-lg">
            <UserRound className="size-5 shrink-0" aria-hidden="true" />
            <span className="truncate">{name}</span>
        </div>
    )
}
