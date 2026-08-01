import type { GradeLevel, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import { Eye, LoaderCircle, Pencil, Trash2, UsersRound } from "lucide-react"
import { useTranslation } from "react-i18next"

const selectClassName =
    "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

type StudentClassesListProps = {
    classes: StudentClass[]
    filteredClasses: StudentClass[]
    gradeLevels: GradeLevel[]
    isLoading: boolean
    loadError: string | null
    classFilter: string
    gradeLevelFilter: string
    onClassFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
    onManageClass: (classId: number) => void
    onEditClass: (studentClass: StudentClass) => void
    onDeleteClass: (studentClass: StudentClass) => void
    page: number
    totalPages: number
    onPageChange: (page: number) => void
}

export function StudentClassesList({
    classes,
    filteredClasses,
    gradeLevels,
    isLoading,
    loadError,
    classFilter,
    gradeLevelFilter,
    onClassFilterChange,
    onGradeLevelFilterChange,
    onManageClass,
    onEditClass,
    onDeleteClass,
    page,
    totalPages,
    onPageChange,
}: StudentClassesListProps) {
    const { t } = useTranslation()

    if (isLoading) {
        return (
            <div className="flex min-h-40 items-center justify-center">
                <LoaderCircle className="size-7 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
            <ClassFilters
                gradeLevels={gradeLevels}
                classFilter={classFilter}
                gradeLevelFilter={gradeLevelFilter}
                onClassFilterChange={onClassFilterChange}
                onGradeLevelFilterChange={onGradeLevelFilterChange}
            />
            {loadError ? (
                <p
                    role="alert"
                    className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                >
                    {loadError}
                </p>
            ) : classes.length === 0 ? (
                <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                    <UsersRound className="mb-2 size-8" />
                    <p className="font-medium">{t("no-class")}</p>
                    <p className="mt-1 text-sm">{t("no-class-help")}</p>
                </div>
            ) : filteredClasses.length === 0 ? (
                <p className="rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                    {t("no-class-filtered")}
                </p>
            ) : (
                <div>
                    <div
                        key={filteredClasses
                            .map((studentClass) => studentClass.id)
                            .join(",")}
                        className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none lg:grid-cols-2"
                    >
                        {filteredClasses.map((studentClass) => (
                            <ClassCard
                                key={studentClass.id}
                                studentClass={studentClass}
                                onManage={() => onManageClass(studentClass.id)}
                                onEdit={() => onEditClass(studentClass)}
                                onDelete={() => onDeleteClass(studentClass)}
                            />
                        ))}
                    </div>
                    <Pagination
                        currentPage={page}
                        totalPages={totalPages}
                        onPageChange={onPageChange}
                    />
                </div>
            )}
        </div>
    )
}

function ClassFilters({
    gradeLevels,
    classFilter,
    gradeLevelFilter,
    onClassFilterChange,
    onGradeLevelFilterChange,
}: {
    gradeLevels: GradeLevel[]
    classFilter: string
    gradeLevelFilter: string
    onClassFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
}) {
    const { t } = useTranslation()

    return (
        <aside className="h-fit rounded-xl border bg-background p-4">
            <h3 className="font-semibold">{t("filters")}</h3>
            <FieldGroup className="mt-4 gap-4">
                <Field>
                    <FieldLabel htmlFor="class-filter">
                        {t("search")}
                    </FieldLabel>
                    <Input
                        id="class-filter"
                        value={classFilter}
                        onChange={(event) =>
                            onClassFilterChange(event.target.value)
                        }
                        placeholder={t("search-class")}
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="class-grade-filter">
                        {t("grade-level")}
                    </FieldLabel>
                    <select
                        id="class-grade-filter"
                        className={selectClassName}
                        value={gradeLevelFilter}
                        onChange={(event) =>
                            onGradeLevelFilterChange(event.target.value)
                        }
                    >
                        <option value="">{t("all-grade-levels")}</option>
                        {gradeLevels.map((level) => (
                            <option key={level.id} value={level.name}>
                                {level.name}
                            </option>
                        ))}
                    </select>
                </Field>
                {(classFilter || gradeLevelFilter) && (
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                            onClassFilterChange("")
                            onGradeLevelFilterChange("")
                        }}
                    >
                        {t("clear-filters")}
                    </Button>
                )}
            </FieldGroup>
        </aside>
    )
}

function ClassCard({
    studentClass,
    onManage,
    onEdit,
    onDelete,
}: {
    studentClass: StudentClass
    onManage: () => void
    onEdit: () => void
    onDelete: () => void
}) {
    const { t, i18n } = useTranslation()
    const latestQuizDate = studentClass.latest_quiz_at
        ? new Intl.DateTimeFormat(i18n.language, {
              dateStyle: "medium",
          }).format(new Date(studentClass.latest_quiz_at))
        : "—"

    return (
        <article className="flex h-full flex-col rounded-xl border bg-background p-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        {studentClass.grade_level}
                    </p>
                    <h3 className="mt-1 truncate text-lg font-semibold">
                        {studentClass.name}
                    </h3>
                </div>
                <div className="flex shrink-0 gap-1">
                    <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label={t("edit-class")}
                        onClick={onEdit}
                    >
                        <Pencil />
                    </Button>
                    <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label={t("delete-class")}
                        className="text-destructive hover:text-destructive"
                        onClick={onDelete}
                    >
                        <Trash2 />
                    </Button>
                </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
                <ClassMetric
                    value={studentClass.student_count}
                    label={t("students")}
                />
                <ClassMetric
                    value={latestQuizDate}
                    label={t("latest-quiz")}
                    title={studentClass.latest_quiz_title ?? undefined}
                />
            </div>
            <Button
                type="button"
                className="mt-4 w-full"
                variant="outline"
                onClick={onManage}
            >
                <Eye />
                {t("manage-students")}
            </Button>
        </article>
    )
}

function ClassMetric({
    value,
    label,
    title,
}: {
    value: number | string
    label: string
    title?: string
}) {
    return (
        <div className="rounded-lg bg-primary/5 p-3" title={title}>
            <p className="text-xl font-bold text-primary">{value}</p>
            <p className="text-sm text-muted-foreground">{label}</p>
        </div>
    )
}
