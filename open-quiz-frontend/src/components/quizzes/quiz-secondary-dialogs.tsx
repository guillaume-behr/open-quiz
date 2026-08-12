import type { FormEvent } from "react"
import type { Question, Quiz, StudentClass } from "@/api/types"
import { formatClassName } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { LoaderCircle, Play, RefreshCw, Trash2, XCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

export function QuizPreviewDialog({
    quiz,
    questions,
    isLoading,
    error,
    onClose,
    onRefresh,
}: {
    quiz: Quiz | null
    questions: Question[]
    isLoading: boolean
    error: string | null
    onClose: () => void
    onRefresh: (quiz: Quiz) => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={quiz !== null}
            onOpenChange={(open) => {
                if (!open) onClose()
            }}
            title={quiz?.title ?? t("preview-quiz")}
            description={t("quiz-random-preview-help")}
            size="xl"
        >
            <div className="flex justify-end">
                <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={isLoading || !quiz}
                    onClick={() => quiz && onRefresh(quiz)}
                >
                    <RefreshCw />
                    {t("draw-again")}
                </Button>
            </div>
            {isLoading ? (
                <div
                    className="flex min-h-40 items-center justify-center"
                    role="status"
                    aria-label={t("page-loading")}
                >
                    <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
                </div>
            ) : error ? (
                <FieldError>{error}</FieldError>
            ) : (
                <ol className="mt-4 space-y-3">
                    {questions.map((question, index) => (
                        <li key={question.id} className="rounded-xl border p-4">
                            <div className="flex items-start justify-between gap-3">
                                <p className="font-semibold">
                                    {index + 1}. {question.prompt}
                                </p>
                                <span className="rounded-full bg-muted px-2 py-1 text-xs">
                                    {t(`difficulty-${question.difficulty}`)}
                                </span>
                            </div>
                            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                                {question.choices.map((choice) => (
                                    <li
                                        key={choice.id}
                                        className="rounded-lg bg-muted/60 px-3 py-2 text-sm"
                                    >
                                        {choice.is_correct ? "✓ " : "○ "}
                                        {choice.label}
                                        {" · "}
                                        {t("points-count", {
                                            count: choice.points,
                                        })}
                                    </li>
                                ))}
                            </ul>
                        </li>
                    ))}
                </ol>
            )}
        </Dialog>
    )
}

export function LaunchQuizDialog({
    quiz,
    classes,
    selectedClassId,
    isBusy,
    error,
    onSelectedClassIdChange,
    onClose,
    onSubmit,
}: {
    quiz: Quiz | null
    classes: StudentClass[]
    selectedClassId: string
    isBusy: boolean
    error: string | null
    onSelectedClassIdChange: (value: string) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={quiz !== null}
            onOpenChange={(open) => {
                if (!open && !isBusy) onClose()
            }}
            title={t("launch-quiz")}
            description={quiz?.title}
            size="sm"
        >
            <form onSubmit={onSubmit}>
                <FieldGroup>
                    <Field>
                        <FieldLabel htmlFor="quiz-class-name">
                            {t("class-name")}
                        </FieldLabel>
                        <select
                            id="quiz-class-name"
                            className={NATIVE_SELECT_CLASS_NAME}
                            value={selectedClassId}
                            onChange={(event) =>
                                onSelectedClassIdChange(event.target.value)
                            }
                            required
                        >
                            <option value="" disabled>
                                {t("choose-class")}
                            </option>
                            {classes.map((studentClass) => (
                                <option
                                    key={studentClass.id}
                                    value={studentClass.id}
                                >
                                    {formatClassName(
                                        studentClass.grade_level,
                                        studentClass.name
                                    )}{" "}
                                    ({studentClass.student_count})
                                </option>
                            ))}
                        </select>
                        {classes.length === 0 && (
                            <FieldError>{t("quiz-needs-class")}</FieldError>
                        )}
                    </Field>
                    {error && <FieldError>{error}</FieldError>}
                    <div className="flex justify-end gap-2">
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isBusy}
                            onClick={onClose}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            type="submit"
                            disabled={isBusy || !selectedClassId}
                        >
                            {isBusy ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : (
                                <Play />
                            )}
                            {t("open-waiting-room")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

export function SessionActionDialog({
    actionToConfirm,
    currentAction,
    error,
    onClose,
    onConfirm,
}: {
    actionToConfirm: "cancel" | "delete" | null
    currentAction: "pause" | "resume" | "cancel" | "delete" | null
    error: string | null
    onClose: () => void
    onConfirm: (action: "cancel" | "delete") => void
}) {
    const { t } = useTranslation()
    const isDelete = actionToConfirm === "delete"
    return (
        <Dialog
            open={actionToConfirm !== null}
            onOpenChange={(open) => {
                if (!open && currentAction === null) onClose()
            }}
            title={t(isDelete ? "delete-session" : "cancel-quiz")}
            description={t(
                isDelete ? "delete-session-help" : "cancel-quiz-help"
            )}
            size="sm"
        >
            {error && <FieldError className="mb-4">{error}</FieldError>}
            <div className="flex justify-end gap-2">
                <Button
                    type="button"
                    variant="outline"
                    disabled={currentAction !== null}
                    onClick={onClose}
                >
                    {t("cancel")}
                </Button>
                <Button
                    type="button"
                    variant="destructive"
                    disabled={currentAction !== null}
                    onClick={() =>
                        actionToConfirm && onConfirm(actionToConfirm)
                    }
                >
                    {currentAction !== null ? (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    ) : isDelete ? (
                        <Trash2 />
                    ) : (
                        <XCircle />
                    )}
                    {t(isDelete ? "delete" : "confirm-cancellation")}
                </Button>
            </div>
        </Dialog>
    )
}
