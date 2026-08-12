import {
    getTrainingHistory,
    getTrainingQuestionBanks,
    startTrainingQuiz,
} from "@/api/quizzes"
import type {
    QuestionBank,
    StudentAccount,
    TrainingHistoryItem,
} from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { naturalCompare } from "@/lib/utils"
import { BarChart3, Dumbbell, LoaderCircle, Play } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

export function TrainingQuizzesPanel({
    student,
    token,
}: {
    student: StudentAccount
    token: string
}) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [banks, setBanks] = useState<QuestionBank[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [startingId, setStartingId] = useState<number | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [historyBank, setHistoryBank] = useState<QuestionBank | null>(null)
    const [history, setHistory] = useState<TrainingHistoryItem[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyError, setHistoryError] = useState<string | null>(null)
    const sortedBanks = [...banks].sort((first, second) =>
        naturalCompare(first.chapter, second.chapter)
    )

    useEffect(() => {
        let active = true
        getTrainingQuestionBanks(token)
            .then((items) => {
                if (active) setBanks(items)
            })
            .catch(() => active && setError(t("training-load-error")))
            .finally(() => active && setIsLoading(false))
        return () => {
            active = false
        }
    }, [t, token])

    async function start(bank: QuestionBank) {
        setStartingId(bank.id)
        setError(null)
        try {
            const joined = await startTrainingQuiz(bank.id, token)
            const { participant_token: participantToken, ...session } = joined
            try {
                sessionStorage.setItem(
                    "open-quiz-training-session",
                    JSON.stringify({
                        joinCode: session.join_code,
                        participantToken,
                    })
                )
            } catch {
                // Route state keeps the current training usable without storage.
            }
            navigate("/student/training", {
                state: { student, token, session, participantToken },
            })
        } catch {
            setError(t("training-start-error"))
        } finally {
            setStartingId(null)
        }
    }

    async function openHistory(bank: QuestionBank) {
        setHistoryBank(bank)
        setHistory([])
        setHistoryError(null)
        setHistoryLoading(true)
        try {
            setHistory(await getTrainingHistory(bank.id, token))
        } catch {
            setHistoryError(t("training-history-error"))
        } finally {
            setHistoryLoading(false)
        }
    }

    if (isLoading) {
        return (
            <div
                className="flex min-h-48 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle className="size-8 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )
    }

    return (
        <div>
            {error && (
                <p className="mb-4 text-sm text-destructive" role="alert">
                    {error}
                </p>
            )}
            {sortedBanks.length === 0 ? (
                <div className="flex min-h-48 flex-col items-center justify-center rounded-xl border border-dashed text-center text-muted-foreground">
                    <Dumbbell className="mb-3 size-9" />
                    <p className="font-semibold">{t("no-training-quiz")}</p>
                    <p className="mt-1 text-sm">{t("no-training-quiz-help")}</p>
                </div>
            ) : (
                <div
                    key={sortedBanks.map((bank) => bank.id).join(",")}
                    className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none sm:grid-cols-2"
                >
                    {sortedBanks.map((bank) => (
                        <article
                            key={bank.id}
                            className="flex flex-col rounded-xl border bg-background p-5"
                        >
                            <div className="flex items-center gap-3">
                                <Dumbbell className="size-7 shrink-0 text-primary" />
                                <h3 className="text-lg font-bold">
                                    {bank.chapter}
                                </h3>
                            </div>
                            <p className="mt-1 text-sm text-muted-foreground">
                                {bank.grade_level} ·{" "}
                                {t("training-quiz-summary", {
                                    count: bank.question_count,
                                })}
                            </p>
                            <p className="mt-3 text-xs text-muted-foreground">
                                {t("training-no-score-help")}
                            </p>
                            <Button
                                className="mt-5"
                                onClick={() => void start(bank)}
                                disabled={
                                    startingId !== null ||
                                    bank.question_count === 0
                                }
                            >
                                {startingId === bank.id ? (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : (
                                    <Play />
                                )}
                                {t("start-training")}
                            </Button>
                            <Button
                                className="mt-2"
                                variant="outline"
                                onClick={() => void openHistory(bank)}
                            >
                                <BarChart3 />
                                {t("training-history")}
                            </Button>
                        </article>
                    ))}
                </div>
            )}
            <Dialog
                open={historyBank !== null}
                onOpenChange={(open) => !open && setHistoryBank(null)}
                title={t("training-history-title", {
                    bank: historyBank?.chapter ?? "",
                })}
                description={t("training-history-help")}
                className="max-w-4xl"
            >
                {historyLoading ? (
                    <div className="flex min-h-40 items-center justify-center">
                        <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
                    </div>
                ) : historyError ? (
                    <p role="alert" className="text-sm text-destructive">
                        {historyError}
                    </p>
                ) : history.length === 0 ? (
                    <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                        {t("training-history-empty")}
                    </p>
                ) : (
                    <TrainingHistoryChart items={history} />
                )}
            </Dialog>
        </div>
    )
}

function TrainingHistoryChart({ items }: { items: TrainingHistoryItem[] }) {
    const { t, i18n } = useTranslation()
    const percentages = items.map((item) =>
        item.maximum_score > 0
            ? Math.max(
                  0,
                  Math.min(100, (item.score / item.maximum_score) * 100)
              )
            : 0
    )
    const points = percentages
        .map((value, index) => {
            const x =
                items.length === 1 ? 50 : (index / (items.length - 1)) * 100
            return `${x},${100 - value}`
        })
        .join(" ")
    return (
        <div className="space-y-5">
            <div className="rounded-xl border bg-muted/20 p-4">
                <svg
                    viewBox="-4 -8 108 116"
                    className="h-56 w-full overflow-visible"
                    role="img"
                    aria-label={t("training-history-chart-label")}
                >
                    {[0, 25, 50, 75, 100].map((value) => (
                        <line
                            key={value}
                            x1="0"
                            x2="100"
                            y1={100 - value}
                            y2={100 - value}
                            className="stroke-border"
                            strokeWidth="0.5"
                        />
                    ))}
                    <polyline
                        points={points}
                        fill="none"
                        className="stroke-primary"
                        strokeWidth="2"
                        vectorEffect="non-scaling-stroke"
                    />
                    {percentages.map((value, index) => {
                        const x =
                            items.length === 1
                                ? 50
                                : (index / (items.length - 1)) * 100
                        return (
                            <circle
                                key={items[index].session_id}
                                cx={x}
                                cy={100 - value}
                                r="2.5"
                                className="fill-primary"
                            />
                        )
                    })}
                </svg>
            </div>
            <ol
                className="space-y-2"
                aria-label={t("training-history-details")}
            >
                {items.map((item, index) => (
                    <li
                        key={item.session_id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
                    >
                        <time dateTime={item.started_at}>
                            {new Intl.DateTimeFormat(i18n.resolvedLanguage, {
                                dateStyle: "medium",
                                timeStyle: "short",
                            }).format(new Date(item.started_at))}
                        </time>
                        <span className="font-semibold">
                            {t("training-history-score", {
                                score: item.score,
                                maximum: item.maximum_score,
                                percent: Math.round(percentages[index]),
                            })}
                        </span>
                    </li>
                ))}
            </ol>
        </div>
    )
}
