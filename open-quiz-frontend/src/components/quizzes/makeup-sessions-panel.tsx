import { getAllStudentClasses } from "@/api/classes"
import {
    controlMakeupSession,
    createMakeupSession,
    getAllQuizzes,
    getMakeupSessions,
} from "@/api/quizzes"
import type { MakeupSession, Quiz, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

export function MakeupSessionsPanel() {
    const { t } = useTranslation()
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [quizzes, setQuizzes] = useState<Quiz[]>([])
    const [sessions, setSessions] = useState<MakeupSession[]>([])
    const [classId, setClassId] = useState("")
    const [quizIds, setQuizIds] = useState<number[]>([])
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        Promise.all([
            getAllStudentClasses(),
            getAllQuizzes(),
            getMakeupSessions(),
        ])
            .then(([loadedClasses, loadedQuizzes, loadedSessions]) => {
                setClasses(loadedClasses)
                setQuizzes(loadedQuizzes)
                setSessions(loadedSessions)
            })
            .catch(() => setError(t("makeup-load-error")))
    }, [t])

    useEffect(() => {
        if (
            !sessions.some((item) =>
                ["waiting", "in_progress", "paused"].includes(item.status)
            )
        )
            return
        const interval = window.setInterval(() => {
            void getMakeupSessions()
                .then(setSessions)
                .catch(() => undefined)
        }, 2000)
        return () => window.clearInterval(interval)
    }, [sessions])

    async function create(event: FormEvent) {
        event.preventDefault()
        if (!classId || !quizIds.length) return
        setBusy(true)
        setError(null)
        try {
            const created = await createMakeupSession(Number(classId), quizIds)
            setSessions((current) => [created, ...current])
            setQuizIds([])
        } catch {
            setError(t("makeup-create-error"))
        } finally {
            setBusy(false)
        }
    }

    async function action(
        item: MakeupSession,
        value: "start" | "pause" | "resume" | "finish" | "cancel"
    ) {
        setBusy(true)
        setError(null)
        try {
            const updated = await controlMakeupSession(item.id, value)
            setSessions((current) =>
                current.map((session) =>
                    session.id === updated.id ? updated : session
                )
            )
        } catch {
            setError(t("makeup-action-error"))
        } finally {
            setBusy(false)
        }
    }

    return (
        <div className="grid gap-6">
            <form onSubmit={create} className="rounded-2xl border bg-card p-5">
                <h2 className="text-xl font-bold">{t("makeup-create")}</h2>
                <div className="mt-4 grid gap-4">
                    <label className="grid gap-1 text-sm font-medium">
                        {t("class-name")}
                        <select
                            className="h-10 rounded-md border bg-background px-3"
                            value={classId}
                            onChange={(event) => setClassId(event.target.value)}
                            required
                        >
                            <option value="">{t("select-class")}</option>
                            {classes.map((item) => (
                                <option key={item.id} value={item.id}>
                                    {item.name}
                                </option>
                            ))}
                        </select>
                    </label>
                    <fieldset className="grid gap-2">
                        <legend className="mb-2 text-sm font-medium">
                            {t("makeup-authorized-quizzes")}
                        </legend>
                        {quizzes.map((quiz) => (
                            <label
                                key={quiz.id}
                                className="flex cursor-pointer items-center justify-between rounded-lg border p-3 text-sm transition-colors focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 hover:border-primary/50"
                            >
                                <span className="flex items-center gap-3">
                                    <input
                                        type="checkbox"
                                        className="accent-primary"
                                        checked={quizIds.includes(quiz.id)}
                                        onChange={(event) =>
                                            setQuizIds((current) =>
                                                event.target.checked
                                                    ? [...current, quiz.id]
                                                    : current.filter(
                                                          (id) => id !== quiz.id
                                                      )
                                            )
                                        }
                                    />
                                    <span className="font-medium">
                                        {quiz.title}
                                    </span>
                                </span>
                                <span className="text-muted-foreground">
                                    {Math.round(quiz.duration_seconds / 60)} min
                                </span>
                            </label>
                        ))}
                    </fieldset>
                    <Button disabled={busy || !classId || !quizIds.length}>
                        {t("makeup-launch")}
                    </Button>
                </div>
            </form>
            {error && (
                <p className="text-sm text-destructive" role="alert">
                    {error}
                </p>
            )}
            <div className="grid gap-3">
                {sessions.map((item) => (
                    <article
                        key={item.id}
                        className="rounded-2xl border bg-card p-5"
                    >
                        <div className="flex flex-wrap justify-between gap-3">
                            <div>
                                <h3 className="font-bold">
                                    {item.class_name} · {item.join_code}
                                </h3>
                                <p className="mt-1 text-sm text-muted-foreground">
                                    {t("makeup-session-summary", {
                                        quizzes: item.quizzes.length,
                                        students: item.participant_count,
                                    })}
                                </p>
                            </div>
                            <span className="text-sm font-semibold">
                                {t(`makeup-status-${item.status}`)}
                            </span>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2">
                            {item.status === "waiting" && (
                                <>
                                    <Button
                                        disabled={busy}
                                        onClick={() =>
                                            void action(item, "start")
                                        }
                                    >
                                        {t("start-quiz")}
                                    </Button>
                                    <Button
                                        variant="outline"
                                        disabled={busy}
                                        onClick={() =>
                                            void action(item, "cancel")
                                        }
                                    >
                                        {t("cancel")}
                                    </Button>
                                </>
                            )}
                            {item.status === "in_progress" && (
                                <>
                                    <Button
                                        variant="outline"
                                        disabled={busy}
                                        onClick={() =>
                                            void action(item, "pause")
                                        }
                                    >
                                        {t("pause-quiz")}
                                    </Button>
                                    <Button
                                        disabled={busy}
                                        onClick={() =>
                                            void action(item, "finish")
                                        }
                                    >
                                        {t("finish-quiz")}
                                    </Button>
                                </>
                            )}
                            {item.status === "paused" && (
                                <Button
                                    disabled={busy}
                                    onClick={() => void action(item, "resume")}
                                >
                                    {t("resume-quiz")}
                                </Button>
                            )}
                        </div>
                    </article>
                ))}
            </div>
        </div>
    )
}
