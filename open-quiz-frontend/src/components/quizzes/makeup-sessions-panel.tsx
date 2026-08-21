import { getAllStudentClasses } from "@/api/classes"
import { ApiError, getLiveAccessToken } from "@/api/client"
import {
    controlMakeupSession,
    createMakeupSession,
    getMakeupQuizOptions,
} from "@/api/quizzes"
import type { MakeupSession, Quiz, StudentClass } from "@/api/types"
import { connectLiveUpdates } from "@/lib/live-updates"
import { formatClassName } from "@/lib/utils"
import { ActiveQuizSessionDialog } from "@/components/quizzes/active-quiz-session-dialog"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { LoaderCircle, Play } from "lucide-react"
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
    const [selectedSession, setSelectedSession] =
        useState<MakeupSession | null>(null)

    useEffect(() => {
        getAllStudentClasses()
            .then(setClasses)
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
    const activeSessions = sessions.filter(
        (session) =>
            session.status !== "finished" && session.status !== "cancelled"
    )

    useEffect(() => {
        return connectLiveUpdates<MakeupSession[]>({
            path: "/api/quizzes/live/teacher/makeup-sessions",
            getToken: getLiveAccessToken,
            onData: (items) => {
                setSessions(items)
                setSelectedSession((current) =>
                    current
                        ? (items.find((item) => item.id === current.id) ?? null)
                        : null
                )
            },
            onUnavailable: () => setError(t("makeup-load-error")),
        })
    }, [t])

    function resetCreateForm() {
        setClassId("")
        setQuizIds([])
        setQuizSearch("")
        setQuizOptions([])
        setError(null)
    }

    async function create(event: FormEvent) {
        event.preventDefault()
        if (!classId || !quizIds.length) return
        setBusy(true)
        setError(null)
        try {
            const created = await createMakeupSession(Number(classId), quizIds)
            setSessions((current) =>
                current.some((session) => session.id === created.id)
                    ? current.map((session) =>
                          session.id === created.id ? created : session
                      )
                    : [created, ...current]
            )
            setSelectedSession(created)
            resetCreateForm()
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
            if (!updated || value === "finish" || value === "cancel") {
                setSelectedSession(null)
            } else {
                setSelectedSession(updated)
            }
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
            {error && (
                <p
                    role="alert"
                    className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
                >
                    {error}
                </p>
            )}
            <section className="rounded-2xl border bg-card p-5 sm:p-6">
                <div className="mb-5">
                    <h3 className="text-lg font-bold">{t("makeup-create")}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("makeup-professor-help")}
                    </p>
                </div>
                <form onSubmit={create}>
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="makeup-class">
                                {t("class-name")}
                            </FieldLabel>
                            <select
                                id="makeup-class"
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
                        </Field>
                        {classId && (
                            <fieldset className="grid gap-2">
                                <legend className="mb-2 text-sm font-medium">
                                    {t("makeup-authorized-quizzes")}
                                </legend>
                                <Field>
                                    <FieldLabel htmlFor="makeup-quiz-search">
                                        {t("search")}
                                    </FieldLabel>
                                    <Input
                                        id="makeup-quiz-search"
                                        value={quizSearch}
                                        placeholder={t("search-quiz")}
                                        onChange={(event) =>
                                            setQuizSearch(event.target.value)
                                        }
                                    />
                                </Field>
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
                        <div className="flex justify-end border-t pt-4">
                            <Button
                                type="submit"
                                size="lg"
                                disabled={busy || !classId || !quizIds.length}
                            >
                                {busy ? (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : (
                                    <Play />
                                )}
                                {t("makeup-launch")}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </section>
            <div
                key={activeSessions.map((session) => session.id).join(",")}
                className="grid animate-in gap-3 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
            >
                {activeSessions.map((item) => (
                    <article
                        key={item.id}
                        className="rounded-2xl border bg-card p-5"
                    >
                        <div className="flex flex-wrap justify-between gap-3">
                            <div>
                                <h3 className="font-bold">
                                    {item.class_name} ·{" "}
                                    <span className="font-mono tracking-wider text-primary slashed-zero">
                                        {item.join_code}
                                    </span>
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
                            <Button
                                disabled={busy}
                                onClick={(event) => {
                                    event.stopPropagation()
                                    setSelectedSession(item)
                                }}
                            >
                                {t("open-waiting-room")}
                            </Button>
                        </div>
                    </article>
                ))}
            </div>
            <ActiveQuizSessionDialog
                session={selectedSession}
                error={error}
                isStarting={busy}
                action={busy ? "pause" : null}
                onClose={() => setSelectedSession(null)}
                onStart={() =>
                    selectedSession && void action(selectedSession, "start")
                }
                onPause={() =>
                    selectedSession && void action(selectedSession, "pause")
                }
                onResume={() =>
                    selectedSession && void action(selectedSession, "resume")
                }
                onFinish={() =>
                    selectedSession && void action(selectedSession, "finish")
                }
                onConfirmCancel={() =>
                    selectedSession && void action(selectedSession, "cancel")
                }
                onConfirmDelete={() => setSelectedSession(null)}
            />
        </div>
    )
}
