import type { MakeupSession, QuizParticipant, QuizSession } from "@/api/types"
import { QuizTimer } from "@/components/quizzes/quiz-timer"
import {
    publishSessionDisplay,
    sessionDisplayKey,
    sessionDisplayPath,
    sessionDisplayPayload,
} from "@/components/quizzes/session-display"
import { isActiveSessionStatus } from "@/lib/session-status"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { cn } from "@/lib/utils"
import {
    AlertTriangle,
    CircleCheck,
    LoaderCircle,
    Maximize,
    Pause,
    Play,
    RotateCcw,
    Trash2,
    UsersRound,
    XCircle,
} from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"

type SessionAction = "pause" | "resume" | "cancel" | "delete" | null

type ActiveQuizSessionDialogProps = {
    session: QuizSession | MakeupSession | null
    error: string | null
    isStarting: boolean
    action: SessionAction
    onClose: () => void
    onStart: () => void
    onPause: () => void
    onResume: () => void
    onFinish?: () => void
    onConfirmCancel: () => void
    onConfirmDelete: () => void
}

function sessionStatusKey(status: QuizSession["status"]): string {
    return {
        waiting: "waiting-for-students",
        in_progress: "quiz-started",
        paused: "quiz-paused",
        finished: "quiz-finished",
        cancelled: "quiz-cancelled",
    }[status]
}

export function ActiveQuizSessionDialog({
    session,
    error,
    isStarting,
    action,
    onClose,
    onStart,
    onPause,
    onResume,
    onFinish,
    onConfirmCancel,
    onConfirmDelete,
}: ActiveQuizSessionDialogProps) {
    const { t } = useTranslation()
    const title =
        session && "quiz_title" in session
            ? session.quiz_title
            : t("makeup-tab")

    return (
        <Dialog
            open={session !== null}
            onOpenChange={(open) => {
                if (!open) onClose()
            }}
            title={title}
            description={
                session
                    ? `${session.class_name} — ${t(
                          sessionStatusKey(session.status)
                      )}`
                    : undefined
            }
            size="lg"
        >
            {session && (
                <div>
                    <SessionSummary session={session} title={title} />
                    <Participants session={session} />
                    {error && <FieldError className="mt-4">{error}</FieldError>}
                    <div className="mt-5 flex flex-wrap justify-end gap-2 border-t pt-4">
                        {session.status === "waiting" && (
                            <Button
                                type="button"
                                size="lg"
                                disabled={
                                    isStarting ||
                                    session.participant_count === 0
                                }
                                onClick={onStart}
                            >
                                {isStarting ? (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : (
                                    <Play />
                                )}
                                {t("start-quiz")}
                            </Button>
                        )}
                        {session.status === "in_progress" && (
                            <Button
                                type="button"
                                variant="outline"
                                disabled={action !== null}
                                onClick={onPause}
                            >
                                {action === "pause" ? (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : (
                                    <Pause />
                                )}
                                {t("pause-quiz")}
                            </Button>
                        )}
                        {session.status === "paused" && (
                            <Button
                                type="button"
                                disabled={action !== null}
                                onClick={onResume}
                            >
                                {action === "resume" ? (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : (
                                    <RotateCcw />
                                )}
                                {t("resume-quiz")}
                            </Button>
                        )}
                        {session.status === "in_progress" && onFinish && (
                            <Button
                                type="button"
                                disabled={action !== null}
                                onClick={onFinish}
                            >
                                <CircleCheck />
                                {t("finish-quiz")}
                            </Button>
                        )}
                        {isActiveSessionStatus(session.status) && (
                            <Button
                                type="button"
                                variant="destructive"
                                disabled={isStarting || action !== null}
                                onClick={onConfirmCancel}
                            >
                                <XCircle />
                                {t("cancel-quiz")}
                            </Button>
                        )}
                        {["cancelled", "finished"].includes(session.status) && (
                            <Button
                                type="button"
                                variant="destructive"
                                disabled={action !== null}
                                onClick={onConfirmDelete}
                            >
                                <Trash2 />
                                {t("delete-session")}
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </Dialog>
    )
}

function SessionSummary({
    session,
    title,
}: {
    session: QuizSession | MakeupSession
    title: string
}) {
    const { t } = useTranslation()

    // The projection tab has no session of its own: this dialog mirrors every
    // live update it receives to whichever tab is showing the code.
    useEffect(() => {
        publishSessionDisplay(sessionDisplayPayload(session, title))
    }, [session, title])

    function openDisplay() {
        publishSessionDisplay(sessionDisplayPayload(session, title))
        window.open(
            sessionDisplayPath(sessionDisplayKey(session)),
            "_blank",
            "noopener"
        )
    }

    return (
        <div className="relative rounded-xl bg-primary/10 p-5 text-center">
            {isActiveSessionStatus(session.status) && (
                <Button
                    className="absolute end-2 top-2"
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={openDisplay}
                >
                    <Maximize />
                    {t("enlarge-session")}
                </Button>
            )}
            <p className="text-sm text-muted-foreground">
                {t("quiz-join-code")}
            </p>
            <p className="mt-1 font-mono text-4xl font-black tracking-[0.2em] text-primary slashed-zero">
                {session.join_code}
            </p>
            {session.status === "in_progress" && "ends_at" in session && (
                <div className="mt-3">
                    <QuizTimer endsAt={session.ends_at} />
                </div>
            )}
            {session.status === "paused" && (
                <p className="mt-3 flex items-center justify-center gap-2 font-semibold text-warning">
                    <Pause />
                    {t("quiz-paused")}
                </p>
            )}
        </div>
    )
}

type SupervisedParticipant = QuizParticipant & {
    quiz_title?: string
    total_questions?: number
}

function Participants({ session }: { session: QuizSession | MakeupSession }) {
    const { t } = useTranslation()
    const participants = (
        [...(session.participants ?? [])] as SupervisedParticipant[]
    ).sort(
        (left, right) => Number(right.has_finished) - Number(left.has_finished)
    )
    return (
        <>
            <div className="mt-5 flex items-center justify-between gap-3">
                <h4 className="flex items-center gap-2 font-semibold">
                    <UsersRound className="size-5" />
                    {t("joined-students", {
                        count: session.participant_count,
                    })}
                </h4>
                {session.status === "waiting" && (
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="size-2 animate-pulse rounded-full bg-success motion-reduce:animate-none" />
                        {t("live-updates")}
                    </span>
                )}
            </div>
            {participants.length === 0 ? (
                <p className="mt-3 rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                    {t("no-student-joined")}
                </p>
            ) : (
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                    {participants.map((participant) => {
                        const totalQuestions =
                            participant.total_questions ??
                            ("total_questions" in session
                                ? session.total_questions
                                : 0)
                        // The exam is over for this student: outline them so
                        // the class list shows at a glance who is still
                        // working, during the exam and during a retake alike.
                        const showAsFinished =
                            participant.has_finished &&
                            ["in_progress", "paused"].includes(session.status)
                        return (
                            <li
                                key={participant.id}
                                className={cn(
                                    "rounded-lg border bg-background px-3 py-2 font-medium",
                                    showAsFinished &&
                                        "border-success bg-success/10 ring-2 ring-success/40"
                                )}
                            >
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <span>
                                        {participant.student_display_name ??
                                            participant.student_identifier}
                                    </span>
                                    {showAsFinished && (
                                        <span className="flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                                            <CircleCheck className="size-3.5" />
                                            {t("quiz-finished")}
                                        </span>
                                    )}
                                </div>
                                {participant.student_display_name && (
                                    <span className="block text-xs font-normal text-muted-foreground">
                                        {participant.student_identifier}
                                    </span>
                                )}
                                {participant.quiz_title && (
                                    <span className="block text-xs font-normal text-muted-foreground">
                                        {participant.quiz_title}
                                    </span>
                                )}
                                {["in_progress", "paused", "finished"].includes(
                                    session.status
                                ) && (
                                    <span className="block text-sm font-semibold text-primary">
                                        {t("teacher-student-progress", {
                                            count: participant.answered_count,
                                            total: totalQuestions,
                                        })}
                                    </span>
                                )}
                                {participant.violation_count > 0 && (
                                    <span className="mt-1 flex items-center gap-1 text-xs font-semibold text-destructive">
                                        <AlertTriangle className="size-3" />
                                        {t("student-monitoring-alert", {
                                            count: participant.violation_count,
                                            event: t(
                                                `violation-${participant.last_violation_type}`
                                            ),
                                        })}
                                    </span>
                                )}
                            </li>
                        )
                    })}
                </ul>
            )}
        </>
    )
}
