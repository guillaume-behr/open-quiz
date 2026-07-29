import type { GradeLevel, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Eye, LoaderCircle, UsersRound } from "lucide-react"
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
}: StudentClassesListProps) {
    const { t } = useTranslation()

    if (isLoading) {
        return (
            <div className="flex min-h-40 items-center justify-center">
                <LoaderCircle className="size-7 animate-spin text-primary" />
            </div>
        )
    }

    if (loadError) {
        return (
            <p
                role="alert"
                className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
            >
                {loadError}
            </p>
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
            {classes.length === 0 ? (
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
                <div className="grid gap-4 lg:grid-cols-2">
                    {filteredClasses.map((studentClass) => (
                        <ClassCard
                            key={studentClass.id}
                            studentClass={studentClass}
                            onManage={() => onManageClass(studentClass.id)}
                        />
                    ))}
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
}: {
    studentClass: StudentClass
    onManage: () => void
}) {
    const { t } = useTranslation()

    return (
        <article className="flex h-full flex-col rounded-xl border bg-background p-4">
            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {studentClass.grade_level}
            </p>
            <h3 className="mt-1 text-lg font-semibold">{studentClass.name}</h3>
            <div className="mt-4 grid grid-cols-2 gap-3">
                <ClassMetric
                    value={studentClass.student_count}
                    label={t("students")}
                />
                <ClassMetric
                    value={studentClass.completed_quiz_count}
                    label={t("completed-quizzes")}
                />
            </div>
            <Button
                type="button"
                className="mt-4 w-full"
                variant="outline"
                onClick={onManage}
            >
                <Eye />
                {t("view-class")}
            </Button>
        </article>
    )
}

function ClassMetric({ value, label }: { value: number; label: string }) {
    return (
        <div className="rounded-lg bg-primary/5 p-3">
            <p className="text-2xl font-bold text-primary">{value}</p>
            <p className="text-sm text-muted-foreground">{label}</p>
        </div>
    )
}
