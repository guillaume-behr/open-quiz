import { ANSWER_MODES, QUESTION_DIFFICULTIES, type Question } from "@/api/types"
import { Button } from "@/components/ui/button"
import { CollapsibleFilters } from "@/components/ui/collapsible-filters"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Plus } from "lucide-react"
import { useLayoutEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { QuestionCard } from "./question-card"
import {
    type QuestionFilterValues,
    useQuestionFilters,
} from "./use-question-filters"
import { LoadingState } from "@/components/ui/loading-state"

/**
 * Where the teacher stood in the question list: its order, its filters and
 * how far the list and its dialog were scrolled. The list unmounts while the
 * form or the deletion of a question replaces its dialog, and gets it back
 * on return.
 */
export type QuestionsView = QuestionFilterValues & {
    filtersOpen: boolean
    listScrollTop: number
    dialogScrollTop: number
}

type QuestionsManagerProps = {
    questions: Question[]
    isLoading: boolean
    error: string | null
    notice?: string | null
    /** The view to restore, as the list last reported it on leaving. */
    initialView?: QuestionsView | null
    onAdd: (view: QuestionsView) => void
    onEdit: (question: Question, view: QuestionsView) => void
    onDelete: (question: Question, view: QuestionsView) => void
}

/** The scrolling body of the dialog holding an element, if any. */
function dialogBodyOf(element: HTMLElement | null) {
    return element?.closest<HTMLElement>("[data-dialog-body]") ?? null
}

export function QuestionsManager({
    questions,
    isLoading,
    error,
    notice = null,
    initialView = null,
    onAdd,
    onEdit,
    onDelete,
}: QuestionsManagerProps) {
    const { t } = useTranslation()
    const sectionRef = useRef<HTMLElement>(null)
    const listRef = useRef<HTMLOListElement>(null)
    // The scroll positions still to restore, once the list is shown.
    const pendingScroll = useRef(initialView)
    const filters = useQuestionFilters(questions, initialView)
    const {
        sort,
        minimumPoints,
        maximumPoints,
        minimumDifficulty,
        maximumDifficulty,
        answerModes,
    } = filters.values
    const [filtersOpen, setFiltersOpen] = useState(
        initialView?.filtersOpen ?? false
    )

    useLayoutEffect(() => {
        const view = pendingScroll.current
        if (!view || !listRef.current) return
        listRef.current.scrollTop = view.listScrollTop
        const dialogBody = dialogBodyOf(listRef.current)
        if (dialogBody) dialogBody.scrollTop = view.dialogScrollTop
        pendingScroll.current = null
    }, [questions, isLoading])

    function currentView(): QuestionsView {
        return {
            ...filters.values,
            filtersOpen,
            listScrollTop: listRef.current?.scrollTop ?? 0,
            dialogScrollTop: dialogBodyOf(sectionRef.current)?.scrollTop ?? 0,
        }
    }

    return (
        <section ref={sectionRef} className="border-t pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="font-semibold">{t("bank-questions")}</h3>
                    <p className="text-xs text-muted-foreground">
                        {t("add-edit-questions")}
                    </p>
                </div>
                <Button type="button" onClick={() => onAdd(currentView())}>
                    <Plus />
                    {t("add-question")}
                </Button>
            </div>
            <CollapsibleFilters
                className="mt-5"
                open={filtersOpen}
                onOpenChange={setFiltersOpen}
                activeCount={filters.activeCount}
            >
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <label className="grid gap-1 text-sm font-medium">
                        {t("question-sort")}
                        <select
                            className={NATIVE_SELECT_CLASS_NAME}
                            value={sort}
                            onChange={(event) =>
                                filters.setSort(event.target.value)
                            }
                        >
                            <option value="default">{t("sort-default")}</option>
                            <option value="difficulty-asc">
                                {t("sort-difficulty-asc")}
                            </option>
                            <option value="difficulty-desc">
                                {t("sort-difficulty-desc")}
                            </option>
                            <option value="points-asc">
                                {t("sort-points-asc")}
                            </option>
                            <option value="points-desc">
                                {t("sort-points-desc")}
                            </option>
                        </select>
                    </label>
                    <fieldset>
                        <legend className="text-sm font-medium">
                            {t("points-range")}
                        </legend>
                        <div className="mt-1 grid grid-cols-2 gap-2">
                            <Input
                                type="number"
                                min={0}
                                step="0.25"
                                value={minimumPoints}
                                placeholder={t("minimum")}
                                aria-label={t("minimum-points")}
                                onChange={(event) =>
                                    filters.setMinimumPoints(event.target.value)
                                }
                            />
                            <Input
                                type="number"
                                min={0}
                                step="0.25"
                                value={maximumPoints}
                                placeholder={t("maximum")}
                                aria-label={t("maximum-points")}
                                onChange={(event) =>
                                    filters.setMaximumPoints(event.target.value)
                                }
                            />
                        </div>
                    </fieldset>
                    <fieldset>
                        <legend className="text-sm font-medium">
                            {t("difficulty-range")}
                        </legend>
                        <div className="mt-1 grid grid-cols-2 gap-2">
                            <select
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={minimumDifficulty}
                                aria-label={t("minimum-difficulty")}
                                onChange={(event) =>
                                    filters.setMinimumDifficulty(
                                        event.target.value
                                    )
                                }
                            >
                                <option value="">{t("minimum")}</option>
                                {QUESTION_DIFFICULTIES.map((difficulty) => (
                                    <option key={difficulty} value={difficulty}>
                                        {t(`difficulty-${difficulty}`)}
                                    </option>
                                ))}
                            </select>
                            <select
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={maximumDifficulty}
                                aria-label={t("maximum-difficulty")}
                                onChange={(event) =>
                                    filters.setMaximumDifficulty(
                                        event.target.value
                                    )
                                }
                            >
                                <option value="">{t("maximum")}</option>
                                {QUESTION_DIFFICULTIES.map((difficulty) => (
                                    <option key={difficulty} value={difficulty}>
                                        {t(`difficulty-${difficulty}`)}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </fieldset>
                </div>
                <fieldset className="mt-4">
                    <legend className="text-sm font-medium">
                        {t("question-types")}
                    </legend>
                    <div className="mt-2 flex flex-wrap gap-2">
                        {ANSWER_MODES.map((mode) => (
                            <label
                                key={mode}
                                className="flex cursor-pointer items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm"
                            >
                                <input
                                    type="checkbox"
                                    checked={answerModes.includes(mode)}
                                    onChange={() =>
                                        filters.toggleAnswerMode(mode)
                                    }
                                />
                                {t(
                                    mode === "single"
                                        ? "single-choice"
                                        : mode === "multiple"
                                          ? "multiple-choice"
                                          : "written-answer"
                                )}
                            </label>
                        ))}
                        {filters.hasFilters && (
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={filters.clearFilters}
                            >
                                {t("clear-filters")}
                            </Button>
                        )}
                    </div>
                </fieldset>
            </CollapsibleFilters>
            <div className="mt-5">
                {notice && (
                    <p role="status" className="mb-3 text-sm">
                        {notice}
                    </p>
                )}
                {isLoading ? (
                    <LoadingState className="min-h-24" size={6} />
                ) : error ? (
                    <p role="alert" className="mt-3 text-sm text-destructive">
                        {error}
                    </p>
                ) : questions.length === 0 ? (
                    <p className="mt-3 rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                        {t("no-question")}
                    </p>
                ) : (
                    <ol
                        ref={listRef}
                        className="max-h-[32rem] space-y-3 overflow-y-auto pe-1"
                    >
                        {filters.visibleQuestions.map((question, index) => (
                            <QuestionCard
                                key={question.id}
                                question={question}
                                index={index}
                                onEdit={() => onEdit(question, currentView())}
                                onDelete={() =>
                                    onDelete(question, currentView())
                                }
                            />
                        ))}
                        {filters.visibleQuestions.length === 0 && (
                            <li className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                                {t("no-question-matches-filters")}
                            </li>
                        )}
                    </ol>
                )}
            </div>
        </section>
    )
}
