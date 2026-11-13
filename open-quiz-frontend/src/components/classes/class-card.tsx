import type { GradeLevel, StudentClass } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { formatClassName } from "@/lib/utils"
import { Pencil, Printer, Trash2, UsersRound } from "lucide-react"
import { useTranslation } from "react-i18next"
import { FilterSidebar } from "@/components/ui/filter-sidebar"

type ClassFilterValues = { search: string; gradeLevel: string }

export function ClassFilters({
    filters,
    gradeLevels,
    onFilterChange,
    onReset,
    onDeleteGradeLevel,
}: {
    filters: ClassFilterValues
    gradeLevels: GradeLevel[]
    onFilterChange: (name: keyof ClassFilterValues, value: string) => void
    onReset: () => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}) {
    const { t } = useTranslation()
    return (
        <FilterSidebar
            hasFilters={Boolean(filters.search || filters.gradeLevel)}
            onClear={onReset}
        >
            <Field>
                <FieldLabel htmlFor="class-filter-search">
                    {t("search")}
                </FieldLabel>
                <Input
                    id="class-filter-search"
                    value={filters.search}
                    onChange={(event) => {
                        onFilterChange("search", event.target.value)
                    }}
                    placeholder={t("search-class")}
                />
            </Field>
            <Field>
                <FieldLabel htmlFor="class-filter-grade-level">
                    {t("grade-level")}
                </FieldLabel>
                <GradeLevelSelect
                    id="class-filter-grade-level"
                    value={filters.gradeLevel}
                    levels={gradeLevels}
                    onChange={(value) => {
                        onFilterChange("gradeLevel", value)
                    }}
                    onDelete={onDeleteGradeLevel}
                    required={false}
                    placeholder={t("all-grade-levels")}
                />
            </Field>
        </FilterSidebar>
    )
}

/** One class in the list, with its actions. */
export function ClassCard({
    studentClass,
    isBusy,
    onEdit,
    onDelete,
    onPrint,
}: {
    studentClass: StudentClass
    isBusy: boolean
    onEdit: () => void
    onDelete: () => void
    onPrint: () => void
}) {
    const { t } = useTranslation()
    return (
        <article className="relative rounded-xl border bg-background p-4">
            <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                className="absolute end-12 top-4"
                onClick={onEdit}
                aria-label={t("edit-class-named", { name: studentClass.name })}
                title={t("edit-class")}
            >
                <Pencil />
            </Button>
            <Button
                type="button"
                size="icon-sm"
                variant="destructive"
                className="absolute end-4 top-4"
                onClick={onDelete}
                aria-label={t("delete-class-named", {
                    name: studentClass.name,
                })}
                title={t("delete-class")}
            >
                <Trash2 />
            </Button>
            <div className="flex items-start gap-3 pe-20">
                <div className="rounded-lg bg-primary/10 p-2 text-primary">
                    <UsersRound className="size-5" />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                        <p className="font-semibold break-words">
                            {formatClassName(
                                studentClass.grade_level,
                                studentClass.name
                            )}
                        </p>
                        <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                            {t("student-count", {
                                count: studentClass.student_count,
                            })}
                        </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={onPrint}
                            disabled={isBusy}
                        >
                            <Printer />
                            {t("print-student-credentials")}
                        </Button>
                    </div>
                </div>
            </div>
        </article>
    )
}
