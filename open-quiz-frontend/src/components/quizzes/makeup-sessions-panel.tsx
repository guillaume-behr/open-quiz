import { getAllStudentClasses } from "@/api/classes"
import { ApiError } from "@/api/client"
import {
    controlMakeupSession,
    createMakeupSession,
    getMakeupQuizOptions,
    getMakeupSessions,
} from "@/api/quizzes"
import type { MakeupSession, Quiz, StudentClass } from "@/api/types"
import { isActiveSessionStatus } from "@/lib/session-status"
import { formatClassName } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Toast } from "@/components/ui/toast"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { useEffect, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"

export function MakeupSessionsPanel() {
    const { t } = useTranslation()
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [quizOptions, setQuizOptions] = useState<Quiz[]>([])
    const [quizSearch, setQuizSearch] = useState("")
    const [sessions, setSessions] = useState<MakeupSession[]>([])
    const [classId, setClassId] = useState("")
    const [quizIds, setQuizIds] = useState<number[]>([])
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        Promise.all([getAllStudentClasses(), getMakeupSessions()])
            .then(([loadedClasses, loadedSessions]) => {
                setClasses(loadedClasses)
                setSessions(loadedSessions)
            })
            .catch(() => setError(t("makeup-load-error")))
    }, [t])

    useEffect(() => {
        if (!classId) return
        let active = true
        getMakeupQuizOptions(Number(classId))
            .then((options) => {
                if (active) setQuizOptions(options)
            })
            .catch(() => {
                if (active) {
                    setQuizOptions([])
                    setError(t("makeup-load-error"))
                }
            })
        return () => {
            active = false
        }
    }, [classId, t])

    const trimmedSearch = quizSearch.trim().toLowerCase()
    const filteredQuizOptions = trimmedSearch
        ? quizOptions.filter((quiz) =>
              quiz.title.toLowerCase().includes(trimmedSearch)
          )
        : quizOptions

    const hasActiveSession = sessions.some((item) =>
        isActiveSessionStatus(item.status)
    )

    useEffect(() => {
        if (!hasActiveSession) return
        let isActive = true
        let refreshInFlight = false
        const refresh = () => {
            if (document.hidden || refreshInFlight) return
            refreshInFlight = true
            void getMakeupSessions()
                .then((loaded) => {
                    if (isActive) setSessions(loaded)
                })
                .catch(() => undefined)
                .finally(() => {
                    refreshInFlight = false
                })
        }
        const interval = window.setInterval(refresh, 2000)
        document.addEventListener("visibilitychange", refresh)
        return () => {
            isActive = false
            window.clearInterval(interval)
            document.removeEventListener("visibilitychange", refresh)
        }
    }, [hasActiveSession])

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
                value === "cancel" || !updated
                    ? current.filter((session) => session.id !== item.id)
                    : current.map((session) =>
                          session.id === updated.id ? updated : session
                      )
            )
        } catch (caught) {
            setError(
                caught instanceof ApiError && caught.status === 409
                    ? value === "cancel"
                        ? t("makeup-cancel-with-answers-error")
                        : t("makeup-action-error")
                    : t("makeup-action-error")
            )
        } finally {
            setBusy(false)
        }
    }

    return (
        <div className="mt-6 grid gap-6">
            {error && <Toast message={error} variant="error" />}
            <form
                onSubmit={create}
                className="w-full max-w-md rounded-2xl border bg-card p-5"
            >
                <h2 className="text-xl font-bold">{t("makeup-create")}</h2>
                <div className="mt-4 grid gap-4">
                    <label className="grid max-w-md gap-1 text-sm font-medium">
                        {t("class-name")}
                        <select
                            className={NATIVE_SELECT_CLASS_NAME}
                            value={classId}
                            onChange={(event) => {
                                setClassId(event.target.value)
                                setQuizIds([])
                                setQuizSearch("")
                                setQuizOptions([])
                            }}
                            required
                        >
                            <option value="">{t("select-class")}</option>
                            {classes.map((item) => (
                                <option key={item.id} value={item.id}>
                                    {formatClassName(
                                        item.grade_level,
                                        item.name
                                    )}
                                </option>
                            ))}
                        </select>
                    </label>
                    {classId && (
                        <fieldset className="grid gap-2">
                            <legend className="mb-2 text-sm font-medium">
                                {t("makeup-authorized-quizzes")}
                            </legend>
                            <label className="grid max-w-md gap-1 text-sm">
                                {t("search")}
                                <Input
                                    value={quizSearch}
                                    placeholder={t("search-quiz")}
                                    onChange={(event) =>
                                        setQuizSearch(event.target.value)
                                    }
                                />
                            </label>
                            {quizOptions.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                    {t("makeup-no-eligible-quizzes")}
                                </p>
                            ) : (
                                filteredQuizOptions.map((quiz) => (
                                    <label
                                        key={quiz.id}
                                        className="flex cursor-pointer items-center justify-between rounded-lg border p-3 text-sm transition-colors focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 hover:border-primary/50"
                                    >
                                        <span className="flex items-center gap-3">
                                            <input
                                                type="checkbox"
                                                className="accent-primary"
                                                checked={quizIds.includes(
                                                    quiz.id
                                                )}
                                                onChange={(event) =>
                                                    setQuizIds((current) =>
                                                        event.target.checked
                                                            ? [
                                                                  ...current,
                                                                  quiz.id,
                                                              ]
                                                            : current.filter(
                                                                  (id) =>
                                                                      id !==
                                                                      quiz.id
                                                              )
                                                    )
                                                }
                                            />
                                            <span className="font-medium">
                                                {quiz.title}
                                            </span>
                                        </span>
                                        <span className="text-muted-foreground">
                                            {Math.round(
                                                quiz.duration_seconds / 60
                                            )}{" "}
                                            min
                                        </span>
                                    </label>
                                ))
                            )}
                        </fieldset>
                    )}
                    <Button
                        type="submit"
                        className="w-full max-w-md"
                        disabled={busy || !classId || !quizIds.length}
                    >
                        {t("makeup-launch")}
                    </Button>
                </div>
            </form>
            <div
                key={sessions.map((session) => session.id).join(",")}
                className="grid animate-in gap-3 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
            >
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
