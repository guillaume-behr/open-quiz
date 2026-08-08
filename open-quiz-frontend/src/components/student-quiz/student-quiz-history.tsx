import { getStudentQuizHistory } from "@/api/student-auth"
import type { StudentQuizHistoryItem } from "@/api/types"
import { BookOpenCheck, LoaderCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

export function StudentQuizHistory({ token }: { token: string }) {
    const { t, i18n } = useTranslation()
    const [items, setItems] = useState<StudentQuizHistoryItem[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [hasError, setHasError] = useState(false)

    useEffect(() => {
        getStudentQuizHistory(token)
            .then(setItems)
            .catch(() => setHasError(true))
            .finally(() => setIsLoading(false))
    }, [token])

    if (isLoading)
        return (
            <div className="flex justify-center py-10">
                <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )

    if (hasError)
        return (
            <p className="py-8 text-center text-destructive" role="alert">
                {t("quiz-history-error")}
            </p>
        )

    if (!items.length)
        return (
            <div className="py-8 text-center text-muted-foreground">
                <BookOpenCheck className="mx-auto mb-3 size-9" />
                <p className="font-medium">{t("quiz-history-empty")}</p>
                <p className="mt-1 text-sm">{t("quiz-history-empty-help")}</p>
            </div>
        )

    return (
        <div
            key={items.map((item) => item.session_id).join(",")}
            className="grid animate-in gap-3 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
        >
            {items.map((item) => (
                <details
                    key={item.session_id}
                    className="group rounded-xl border bg-background"
                >
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4">
                        <span>
                            <span className="block font-semibold">
                                {item.quiz_title}
                            </span>
                            <span className="mt-1 block text-xs text-muted-foreground">
                                {item.class_name} ·{" "}
                                {new Intl.DateTimeFormat(i18n.language, {
                                    dateStyle: "long",
                                }).format(new Date(item.started_at))}
                            </span>
                            {item.score !== null &&
                                item.maximum_score !== null && (
                                    <span className="mt-2 block font-bold text-primary">
                                        {t("published-grade", {
                                            score: item.score,
                                            maximum: item.maximum_score,
                                        })}
                                    </span>
                                )}
                        </span>
                        <span className="text-sm font-medium text-primary">
                            {t("view-correction")}
                        </span>
                    </summary>
                    <div className="grid gap-3 border-t p-4">
                        {item.answers.map((answer) => (
                            <article
                                key={answer.question_id}
                                className="rounded-lg border p-3"
                            >
                                <p className="text-xs font-semibold text-muted-foreground">
                                    {t("question-number", {
                                        number: answer.position,
                                    })}
                                </p>
                                <h3 className="mt-1 font-semibold">
                                    {answer.prompt}
                                </h3>
                                <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                                    <div
                                        className={
                                            answer.is_correct
                                                ? "p-3"
                                                : "rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive"
                                        }
                                    >
                                        <p
                                            className={
                                                answer.is_correct
                                                    ? "font-medium text-muted-foreground"
                                                    : "font-medium"
                                            }
                                        >
                                            {t("student-answer")}
                                            {!answer.is_correct && (
                                                <span className="sr-only">
                                                    {` — ${t("training-incorrect")}`}
                                                </span>
                                            )}
                                        </p>
                                        <p
                                            className={`mt-1 whitespace-pre-wrap ${answer.is_correct ? "" : "text-destructive"}`}
                                        >
                                            {answer.submitted_answers.join(
                                                ", "
                                            ) || t("no-answer")}
                                        </p>
                                    </div>
                                    <div className="rounded-lg bg-emerald-500/10 p-3">
                                        <p className="font-medium text-emerald-700 dark:text-emerald-300">
                                            {t("correct-answer")}
                                        </p>
                                        <p className="mt-1 whitespace-pre-wrap">
                                            {answer.expected_answers.join(
                                                ", "
                                            ) || "—"}
                                        </p>
                                    </div>
                                </div>
                            </article>
                        ))}
                    </div>
                </details>
            ))}
        </div>
    )
}
