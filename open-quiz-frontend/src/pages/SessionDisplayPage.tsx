import { QuizTimer } from "@/components/quizzes/quiz-timer"
import {
    isSessionDisplayKey,
    readSessionDisplay,
    subscribeSessionDisplay,
    type SessionDisplayPayload,
} from "@/components/quizzes/session-display"
import { Button } from "@/components/ui/button"
import { Maximize, Minimize, Pause, UsersRound } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useParams } from "react-router"

const statusKeys: Record<SessionDisplayPayload["status"], string> = {
    waiting: "waiting-for-students",
    in_progress: "quiz-started",
    paused: "quiz-paused",
    finished: "quiz-finished",
    cancelled: "quiz-cancelled",
}

export function SessionDisplayPage() {
    const { t } = useTranslation()
    const { sessionKey } = useParams()
    const validKey = isSessionDisplayKey(sessionKey) ? sessionKey : null
    const [session, setSession] = useState<SessionDisplayPayload | null>(() =>
        validKey ? readSessionDisplay(validKey) : null
    )
    const [isFullscreen, setIsFullscreen] = useState(false)

    useEffect(() => {
        if (!validKey) return
        return subscribeSessionDisplay(validKey, setSession)
    }, [validKey])

    useEffect(() => {
        const update = () =>
            setIsFullscreen(document.fullscreenElement !== null)
        update()
        document.addEventListener("fullscreenchange", update)
        return () => document.removeEventListener("fullscreenchange", update)
    }, [])

    useEffect(() => {
        document.title = session
            ? `${session.joinCode} — ${session.title}`
            : t("app-name")
    }, [session, t])

    const toggleFullscreen = useCallback(() => {
        const request = document.fullscreenElement
            ? document.exitFullscreen()
            : document.documentElement.requestFullscreen()
        void request.catch(() => undefined)
    }, [])

    if (!session) {
        return (
            <main className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background px-6 py-10 text-center">
                <h1 className="text-2xl font-extrabold">
                    {t("session-display-unavailable")}
                </h1>
                <p className="max-w-xl text-muted-foreground">
                    {t("session-display-unavailable-help")}
                </p>
            </main>
        )
    }

    return (
        <main className="flex min-h-dvh flex-col bg-background px-4 py-4 sm:px-8">
            <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                    <h1 className="truncate text-xl font-extrabold sm:text-3xl">
                        {session.title}
                    </h1>
                    <p className="truncate text-muted-foreground">
                        {session.className} — {t(statusKeys[session.status])}
                    </p>
                </div>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={toggleFullscreen}
                >
                    {isFullscreen ? <Minimize /> : <Maximize />}
                    {t(isFullscreen ? "exit-fullscreen" : "enter-fullscreen")}
                </Button>
            </div>
            <div className="flex flex-1 flex-col items-center justify-center gap-6 py-6">
                <div className="w-full text-center">
                    <p className="text-lg font-semibold text-muted-foreground sm:text-2xl">
                        {t("quiz-join-code")}
                    </p>
                    <p className="mt-2 font-mono text-[clamp(4rem,20vw,18rem)] leading-none font-black tracking-[0.15em] text-primary slashed-zero">
                        {session.joinCode}
                    </p>
                </div>
                {session.status === "in_progress" && session.endsAt && (
                    <QuizTimer endsAt={session.endsAt} variant="display" />
                )}
                {session.status === "paused" && (
                    <p className="flex items-center gap-3 text-[clamp(2rem,8vw,6rem)] leading-none font-black text-warning">
                        <Pause className="size-[0.8em]" />
                        {t("quiz-paused")}
                    </p>
                )}
            </div>
            <p className="flex flex-wrap items-center justify-center gap-x-6 gap-y-1 text-base font-semibold sm:text-xl">
                <span className="flex items-center gap-2">
                    <UsersRound className="size-5" />
                    {t("joined-students", { count: session.participantCount })}
                </span>
                <span className="text-success">
                    {t("students-finished", { count: session.finishedCount })}
                </span>
            </p>
        </main>
    )
}
