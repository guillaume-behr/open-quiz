import { getAllStudentClasses } from "@/api/classes"
import { getAllQuestionBanks } from "@/api/question-banks"
import {
    createQuiz,
    deleteQuiz,
    getQuizzes,
    launchQuiz,
    previewQuiz,
    updateQuiz,
} from "@/api/quizzes"
import type { GradeLevel, Quiz } from "@/api/types"
import { printExamSubjects } from "@/components/quizzes/print-quiz"
import { QuizFormDialog } from "@/components/quizzes/quiz-form-dialog"
import {
    availableQuestionCounts,
    emptyQuizForm,
    quizFormReducer,
} from "@/components/quizzes/quiz-form-state"
import {
    LaunchQuizDialog,
    PrintQuizDialog,
    QuizPreviewDialog,
} from "@/components/quizzes/quiz-secondary-dialogs"
import { QuizzesList } from "@/components/quizzes/quizzes-list"
import { LiveSessionDialogs } from "@/components/quizzes/live-session-dialogs"
import { useLiveQuizSessions } from "@/components/quizzes/use-live-quiz-sessions"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { useAsyncAction } from "@/hooks/use-async-action"
import { usePagedList } from "@/hooks/use-paged-list"
import { useResource } from "@/hooks/use-resource"
import { type FormEvent, useCallback, useReducer, useState } from "react"
import { useTranslation } from "react-i18next"
import { PAGE_SIZE } from "@/lib/utils"
import { apiErrorMessage } from "@/lib/errors"

type QuizzesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
    gradeLevels: GradeLevel[]
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}

function loadSupportData() {
    return Promise.all([getAllQuestionBanks(), getAllStudentClasses()])
}

/** With a focused quiz, the API answers the page that holds it. */
function loadQuizzes(
    page: number,
    filters: { search: string; gradeLevel: string },
    focus: number | null
) {
    return getQuizzes(
        page,
        filters.search.trim(),
        filters.gradeLevel,
        PAGE_SIZE,
        focus
    )
}

export function QuizzesPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
    gradeLevels,
    onDeleteGradeLevel,
}: QuizzesPanelProps) {
    const { t, i18n } = useTranslation()
    const support = useResource(loadSupportData)
    const [banks, classes] = support.data ?? [[], []]
    const quizList = usePagedList(loadQuizzes, { search: "", gradeLevel: "" })
    const quizzes = quizList.items
    const live = useLiveQuizSessions()
    const [form, dispatchForm] = useReducer(quizFormReducer, emptyQuizForm)
    const [previewedQuiz, setPreviewedQuiz] = useState<Quiz | null>(null)
    const preview = useResource(
        useCallback(
            () =>
                previewedQuiz
                    ? previewQuiz(previewedQuiz.id)
                    : Promise.resolve([]),
            [previewedQuiz]
        )
    )
    const [quizToLaunch, setQuizToLaunch] = useState<Quiz | null>(null)
    const [selectedClassId, setSelectedClassId] = useState("")
    const [quizToPrint, setQuizToPrint] = useState<Quiz | null>(null)
    const [printClassId, setPrintClassId] = useState("")
    const [quizToDelete, setQuizToDelete] = useState<Quiz | null>(null)

    const availableByDifficulty = availableQuestionCounts(
        banks,
        form.selectedBankIds
    )
    const questionCount = Object.values(form.difficultyCounts).reduce(
        (total, count) => total + count,
        0
    )
    const loadError =
        support.error || quizList.error || live.liveSessionsLoadFailed
            ? t("quizzes-load-error")
            : null

    const saving = useAsyncAction(saveQuiz, (caught) =>
        apiErrorMessage(
            caught,
            t,
            t(form.editingQuiz ? "quiz-update-error" : "quiz-create-error")
        )
    )
    const launching = useAsyncAction(launchSelectedQuiz, (caught) =>
        apiErrorMessage(caught, t, t("quiz-launch-error"))
    )
    const printing = useAsyncAction(printSelectedQuiz, () =>
        t("quiz-print-error")
    )
    const deleting = useAsyncAction(deleteSelectedQuiz, (caught) =>
        apiErrorMessage(caught, t, t("quiz-delete-error"))
    )

    function resetCreationForm(): void {
        dispatchForm({ type: "reset" })
        saving.setError(null)
    }

    function openQuizEditor(quiz: Quiz): void {
        dispatchForm({ type: "edit", quiz })
        saving.setError(null)
    }

    async function printSelectedQuiz(
        event: FormEvent<HTMLFormElement>
    ): Promise<void> {
        event.preventDefault()
        if (!quizToPrint) return
        const studentClass = classes.find(
            (item) => String(item.id) === printClassId
        )
        if (!studentClass || studentClass.students.length === 0) return
        const printWindow = window.open("", "_blank")
        if (!printWindow) {
            printing.setError(t("quiz-print-popup-error"))
            return
        }
        printWindow.opener = null
        try {
            await printExamSubjects(
                quizToPrint,
                studentClass,
                printWindow,
                t,
                i18n.resolvedLanguage ?? "fr"
            )
        } catch (caught) {
            printWindow.close()
            throw caught
        }
        setQuizToPrint(null)
        setPrintClassId("")
    }

    async function saveQuiz(event: FormEvent<HTMLFormElement>): Promise<void> {
        event.preventDefault()
        if (questionCount === 0 || form.selectedBankIds.length === 0) return
        const { editingQuiz } = form
        const payload = {
            mode: "exam" as const,
            title: form.title.trim(),
            source_language:
                editingQuiz?.source_language ?? i18n.resolvedLanguage ?? "fr",
            question_bank_ids: form.selectedBankIds,
            duration_seconds: form.durationMinutes * 60,
            allow_previous_questions: form.allowPreviousQuestions,
            allow_answer_review: form.allowAnswerReview,
            allow_negative_points: form.allowNegativePoints,
            same_questions_for_all: form.sameQuestionsForAll,
            easy_question_count: form.difficultyCounts.easy,
            medium_question_count: form.difficultyCounts.medium,
            hard_question_count: form.difficultyCounts.hard,
        }
        if (editingQuiz) {
            const quiz = await updateQuiz(editingQuiz.id, payload)
            quizList.setData(
                (current) =>
                    current && {
                        ...current,
                        items: current.items.map((item) =>
                            item.id === quiz.id ? quiz : item
                        ),
                    }
            )
            onCreateDialogOpenChange(false)
            dispatchForm({ type: "reset" })
            quizList.reload()
        } else {
            const quiz = await createQuiz(payload)
            onCreateDialogOpenChange(false)
            dispatchForm({ type: "reset" })
            quizList.focus(quiz.id)
        }
    }

    function openPreview(quiz: Quiz): void {
        if (quiz === previewedQuiz) preview.reload()
        else setPreviewedQuiz(quiz)
    }

    async function launchSelectedQuiz(
        event: FormEvent<HTMLFormElement>
    ): Promise<void> {
        event.preventDefault()
        if (!quizToLaunch) return
        const session = await launchQuiz(
            quizToLaunch.id,
            Number(selectedClassId)
        )
        setQuizToLaunch(null)
        setSelectedClassId("")
        live.showLaunchedSession(session)
    }

    async function deleteSelectedQuiz(): Promise<void> {
        if (!quizToDelete) return
        await deleteQuiz(quizToDelete.id)
        setQuizToDelete(null)
        quizList.reload()
    }

    return (
        <div className="mt-6">
            <QuizzesList
                quizzes={quizzes}
                sessions={live.sessions}
                gradeLevels={gradeLevels}
                isLoading={!support.hasSettled || !quizList.hasSettled}
                loadError={loadError}
                quizFilter={quizList.filters.search}
                gradeLevelFilter={quizList.filters.gradeLevel}
                onQuizFilterChange={(value) => {
                    quizList.setFilter("search", value)
                }}
                onGradeLevelFilterChange={(value) => {
                    quizList.setFilter("gradeLevel", value)
                }}
                onDeleteGradeLevel={onDeleteGradeLevel}
                page={quizList.page}
                totalPages={quizList.totalPages}
                onPageChange={quizList.showPage}
                onEdit={openQuizEditor}
                onPreview={openPreview}
                onLaunch={(quiz) => {
                    launching.setError(null)
                    setQuizToLaunch(quiz)
                }}
                onDelete={(quiz) => {
                    deleting.setError(null)
                    setQuizToDelete(quiz)
                }}
                onPrint={(quiz) => {
                    printing.setError(null)
                    setPrintClassId("")
                    setQuizToPrint(quiz)
                }}
                onOpenSession={(quizSession) => {
                    live.openSession(quizSession)
                }}
            />

            <QuizFormDialog
                open={isCreateDialogOpen || form.editingQuiz !== null}
                editingQuiz={form.editingQuiz}
                banks={banks}
                gradeLevels={gradeLevels}
                quizGradeLevel={form.gradeLevel}
                title={form.title}
                durationMinutes={form.durationMinutes}
                selectedBankIds={form.selectedBankIds}
                allowPreviousQuestions={form.allowPreviousQuestions}
                allowAnswerReview={form.allowAnswerReview}
                allowNegativePoints={form.allowNegativePoints}
                sameQuestionsForAll={form.sameQuestionsForAll}
                difficultyCounts={form.difficultyCounts}
                availableByDifficulty={availableByDifficulty}
                isBusy={saving.isPending}
                error={saving.error}
                onTitleChange={(value) =>
                    dispatchForm({ type: "set", field: "title", value })
                }
                onDurationChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "durationMinutes",
                        value,
                    })
                }
                onQuizGradeLevelChange={(gradeLevel) =>
                    dispatchForm({ type: "grade-level", gradeLevel })
                }
                onDeleteGradeLevel={onDeleteGradeLevel}
                onSelectedBankIdsChange={(ids) =>
                    dispatchForm({ type: "banks", ids, banks })
                }
                onAllowPreviousQuestionsChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "allowPreviousQuestions",
                        value,
                    })
                }
                onAllowAnswerReviewChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "allowAnswerReview",
                        value,
                    })
                }
                onAllowNegativePointsChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "allowNegativePoints",
                        value,
                    })
                }
                onSameQuestionsForAllChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "sameQuestionsForAll",
                        value,
                    })
                }
                onDifficultyCountsChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "difficultyCounts",
                        value,
                    })
                }
                onClose={() => {
                    onCreateDialogOpenChange(false)
                    resetCreationForm()
                }}
                onSubmit={(event) => void saving.run(event)}
            />

            <QuizPreviewDialog
                quiz={previewedQuiz}
                questions={preview.isLoading ? [] : (preview.data ?? [])}
                isLoading={previewedQuiz !== null && preview.isLoading}
                error={
                    preview.error
                        ? apiErrorMessage(
                              preview.error,
                              t,
                              t("quiz-preview-error")
                          )
                        : null
                }
                onClose={() => setPreviewedQuiz(null)}
                onRefresh={openPreview}
            />

            <LaunchQuizDialog
                quiz={quizToLaunch}
                classes={classes}
                selectedClassId={selectedClassId}
                isBusy={launching.isPending}
                error={launching.error}
                onSelectedClassIdChange={setSelectedClassId}
                onClose={() => setQuizToLaunch(null)}
                onSubmit={(event) => void launching.run(event)}
            />

            <PrintQuizDialog
                quiz={quizToPrint}
                classes={classes}
                selectedClassId={printClassId}
                isBusy={printing.isPending}
                error={printing.error}
                onSelectedClassIdChange={setPrintClassId}
                onClose={() => {
                    setQuizToPrint(null)
                    setPrintClassId("")
                    printing.setError(null)
                }}
                onSubmit={(event) => void printing.run(event)}
            />

            <LiveSessionDialogs live={live} />

            <ConfirmDeleteDialog
                open={quizToDelete !== null}
                title={t("delete-quiz")}
                description={t("delete-quiz-help", {
                    title: quizToDelete?.title ?? "",
                })}
                isBusy={deleting.isPending}
                error={deleting.error}
                onClose={() => setQuizToDelete(null)}
                onConfirm={() => void deleting.run()}
            />
        </div>
    )
}
