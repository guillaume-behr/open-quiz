import type { QuizSession, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { cn, formatClassName } from "@/lib/utils"
import {
    CalendarDays,
    CheckCircle2,
    Eye,
    School,
    Trash2,
    TriangleAlert,
} from "lucide-react"
import { useTranslation } from "react-i18next"

export type ResultFilterValues = { quiz: string; class: string }

export function ResultFilters({
    filters,
    classes,
    areClassesLoading,
    onFilterChange,
    onReset,
}: {
    filters: ResultFilterValues
    classes: StudentClass[]
    areClassesLoading: boolean
    onFilterChange: (name: keyof ResultFilterValues, value: string) => void
    onReset: () => void
}) {
    const { t } = useTranslation()
    return (
        <aside className="h-fit rounded-xl border bg-background p-4">
            <h3 className="font-semibold">{t("filters")}</h3>
            <FieldGroup className="mt-4 gap-4">
                <Field>
                    <FieldLabel htmlFor="result-quiz-filter">
                        {t("quiz-title")}
                    </FieldLabel>
                    <Input
                        id="result-quiz-filter"
                        value={filters.quiz}
                        placeholder={t("search-quiz")}
                        onChange={(event) => {
                            onFilterChange("quiz", event.target.value)
                        }}
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="result-class-filter">
                        {t("class-name")}
                    </FieldLabel>
                    <select
                        id="result-class-filter"
                        className={NATIVE_SELECT_CLASS_NAME}
                        value={filters.class}
                        disabled={areClassesLoading}
                        onChange={(event) => {
                            onFilterChange("class", event.target.value)
                        }}
                    >
                        <option value="">{t("all-classes")}</option>
                        {classes.map((studentClass) => (
                            <option
                                key={studentClass.id}
                                value={studentClass.name}
                            >
                                {formatClassName(
                                    studentClass.grade_level,
                                    studentClass.name
                                )}
                            </option>
                        ))}
                    </select>
                </Field>
                {(filters.quiz || filters.class) && (
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                            onReset()
                        }}
                    >
                        {t("clear-filters")}
                    </Button>
                )}
            </FieldGroup>
        </aside>
    )
}

/** One finished exam in the card view. */
export function ResultCard({
    result,
    date,
    onView,
    onDelete,
}: {
    result: QuizSession
    date: string
    onView: () => void
    onDelete: () => void
}) {
    const { t } = useTranslation()
    return (
        <article className="flex flex-col rounded-2xl border bg-background p-5 shadow-sm transition-shadow hover:shadow-md">
            <div className="flex items-center gap-3">
                <div
                    role="img"
                    aria-label={t(
                        result.grades_published_at
                            ? "grades-published"
                            : "grades-not-published"
                    )}
                    className={cn(
                        "shrink-0 rounded-xl p-2.5",
                        result.grades_published_at
                            ? "bg-success/10 text-success"
                            : "bg-warning/10 text-warning"
                    )}
                >
                    {result.grades_published_at ? (
                        <CheckCircle2 className="size-5" aria-hidden="true" />
                    ) : (
                        <TriangleAlert className="size-5" aria-hidden="true" />
                    )}
                </div>
                <h3 className="min-w-0 flex-1 truncate text-lg font-bold">
                    {result.quiz_title}
                </h3>
                <span className="shrink-0 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                    {t("result-students", {
                        count: result.participant_count,
                    })}
                </span>
            </div>
            <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <p className="flex items-center gap-2">
                    <CalendarDays className="size-4 shrink-0" />
                    {date}
                </p>
                <p className="flex items-center gap-2">
                    <School className="size-4 shrink-0" />
                    {result.class_name}
                </p>
            </div>
            <div className="mt-5 flex gap-2">
                <Button className="flex-1" variant="outline" onClick={onView}>
                    <Eye />
                    {t("view-results")}
                </Button>
                <Button
                    variant="outline"
                    aria-label={t("delete-result")}
                    onClick={onDelete}
                >
                    <Trash2 />
                </Button>
            </div>
        </article>
    )
}
