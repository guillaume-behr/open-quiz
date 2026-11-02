import type { GradeLevel, StudentAccount, StudentClass } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { Button } from "@/components/ui/button"
import { CollapsibleFilters } from "@/components/ui/collapsible-filters"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { formatClassName } from "@/lib/utils"
import { Check, LoaderCircle } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

type AssignmentProps = {
    accounts: StudentAccount[]
    gradeLevels: GradeLevel[]
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    isBusy: boolean
    error: string | null
    onCancel: () => void
    onAssign: (accountIds: Set<number>) => void
}

export function StudentAssignmentDialog({
    open,
    studentClass,
    ...props
}: AssignmentProps & { open: boolean; studentClass: StudentClass | null }) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={(isOpen) => !isOpen && props.onCancel()}
            title={t("assign-student")}
            description={t("assign-student-help", {
                className: studentClass?.name,
            })}
            size="xl"
        >
            <StudentAssignmentForm {...props} />
        </Dialog>
    )
}

/** Mounted while the dialog is open, so filters and selection start empty. */
function StudentAssignmentForm({
    accounts,
    gradeLevels,
    onDeleteGradeLevel,
    isBusy,
    error,
    onCancel,
    onAssign,
}: AssignmentProps) {
    const { t, i18n } = useTranslation()
    const [assignmentSearch, setAssignmentSearch] = useState("")
    const [assignmentClassFilter, setAssignmentClassFilter] = useState("")
    const [assignmentGradeLevelFilter, setAssignmentGradeLevelFilter] =
        useState("")
    const [selectedAccountIds, setSelectedAccountIds] = useState<Set<number>>(
        new Set()
    )

    const normalizedAssignmentSearch = assignmentSearch
        .trim()
        .toLocaleLowerCase()
    const assignmentClasses = Array.from(
        new Map(
            accounts
                .filter(
                    (account) =>
                        account.class_id !== null && account.class_name !== null
                )
                .map(
                    (account) =>
                        [
                            account.class_id!,
                            formatClassName(
                                account.grade_level,
                                account.class_name
                            ),
                        ] as const
                )
        ).entries()
    ).sort(([, firstName], [, secondName]) =>
        firstName.localeCompare(secondName, i18n.resolvedLanguage)
    )
    const filteredAccounts = accounts.filter((account) => {
        const matchesSearch = normalizedAssignmentSearch
            ? `${account.display_name} ${account.identifier} ${account.class_name ?? ""} ${account.grade_level ?? ""}`
                  .toLocaleLowerCase()
                  .includes(normalizedAssignmentSearch)
            : true
        const matchesClass =
            assignmentClassFilter === "unassigned"
                ? account.class_id === null
                : assignmentClassFilter
                  ? account.class_id === Number(assignmentClassFilter)
                  : true
        const matchesGradeLevel = assignmentGradeLevelFilter
            ? account.grade_level === assignmentGradeLevelFilter
            : true
        return matchesSearch && matchesClass && matchesGradeLevel
    })

    function toggleAccount(accountId: number) {
        setSelectedAccountIds((current) => {
            const next = new Set(current)
            if (next.has(accountId)) next.delete(accountId)
            else next.add(accountId)
            return next
        })
    }

    return (
        <>
            {accounts.length === 0 ? (
                <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                    {t("no-student-to-assign")}
                </p>
            ) : (
                <div className="space-y-4">
                    <CollapsibleFilters
                        activeCount={
                            Number(Boolean(assignmentSearch)) +
                            Number(Boolean(assignmentClassFilter)) +
                            Number(Boolean(assignmentGradeLevelFilter))
                        }
                    >
                        <div className="grid gap-3 sm:grid-cols-3">
                            <Field>
                                <FieldLabel htmlFor="assignment-student-search">
                                    {t("search")}
                                </FieldLabel>
                                <Input
                                    id="assignment-student-search"
                                    value={assignmentSearch}
                                    onChange={(event) =>
                                        setAssignmentSearch(event.target.value)
                                    }
                                    placeholder={t("search-student")}
                                />
                            </Field>
                            <Field>
                                <FieldLabel htmlFor="assignment-student-class">
                                    {t("student-class")}
                                </FieldLabel>
                                <select
                                    id="assignment-student-class"
                                    className={NATIVE_SELECT_CLASS_NAME}
                                    value={assignmentClassFilter}
                                    onChange={(event) =>
                                        setAssignmentClassFilter(
                                            event.target.value
                                        )
                                    }
                                >
                                    <option value="">{t("all-classes")}</option>
                                    <option value="unassigned">
                                        {t("student-unassigned")}
                                    </option>
                                    {assignmentClasses.map(
                                        ([classId, name]) => (
                                            <option
                                                key={classId}
                                                value={classId}
                                            >
                                                {name}
                                            </option>
                                        )
                                    )}
                                </select>
                            </Field>
                            <Field>
                                <FieldLabel htmlFor="assignment-student-grade-level">
                                    {t("grade-level")}
                                </FieldLabel>
                                <GradeLevelSelect
                                    id="assignment-student-grade-level"
                                    value={assignmentGradeLevelFilter}
                                    levels={gradeLevels}
                                    onChange={(value) =>
                                        setAssignmentGradeLevelFilter(value)
                                    }
                                    onDelete={onDeleteGradeLevel}
                                    required={false}
                                    placeholder={t("all-grade-levels")}
                                />
                            </Field>
                        </div>

                        {(assignmentSearch ||
                            assignmentClassFilter ||
                            assignmentGradeLevelFilter) && (
                            <div className="mt-3 flex justify-end">
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => {
                                        setAssignmentSearch("")
                                        setAssignmentClassFilter("")
                                        setAssignmentGradeLevelFilter("")
                                    }}
                                >
                                    {t("clear-filters")}
                                </Button>
                            </div>
                        )}
                    </CollapsibleFilters>

                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                        <p className="text-muted-foreground">
                            {t("selected-students", {
                                count: selectedAccountIds.size,
                            })}
                        </p>
                    </div>

                    {filteredAccounts.length === 0 ? (
                        <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                            {t("no-student-matching-filters")}
                        </p>
                    ) : (
                        <div className="grid gap-3 sm:grid-cols-2">
                            {filteredAccounts.map((account) => {
                                const isSelected = selectedAccountIds.has(
                                    account.id
                                )
                                return (
                                    <button
                                        key={account.id}
                                        type="button"
                                        aria-pressed={isSelected}
                                        onClick={() =>
                                            toggleAccount(account.id)
                                        }
                                        className={`relative rounded-xl border p-4 text-start transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none ${isSelected ? "border-primary bg-primary/5 ring-2 ring-primary/20" : "bg-background hover:border-primary/50 hover:bg-muted/40"}`}
                                    >
                                        <span
                                            className={`absolute end-4 top-4 flex size-6 items-center justify-center rounded-md border ${isSelected ? "border-primary bg-primary text-primary-foreground" : "text-transparent"}`}
                                            aria-hidden="true"
                                        >
                                            <Check className="size-4" />
                                        </span>
                                        <div className="pe-9">
                                            <p className="font-semibold break-words">
                                                {account.display_name}
                                            </p>
                                            <p className="mt-1 text-xs text-muted-foreground">
                                                {account.identifier}
                                            </p>
                                        </div>
                                        <div className="mt-4 grid grid-cols-2 gap-3 border-t pt-3 text-sm">
                                            <div className="min-w-0">
                                                <p className="text-xs text-muted-foreground">
                                                    {t("student-class")}
                                                </p>
                                                <p className="mt-1 truncate font-medium">
                                                    {account.class_name
                                                        ? formatClassName(
                                                              account.grade_level,
                                                              account.class_name
                                                          )
                                                        : t(
                                                              "student-unassigned"
                                                          )}
                                                </p>
                                            </div>
                                            <div className="min-w-0">
                                                <p className="text-xs text-muted-foreground">
                                                    {t("grade-level")}
                                                </p>
                                                <p className="mt-1 truncate font-medium">
                                                    {account.grade_level ??
                                                        t(
                                                            "student-no-grade-level"
                                                        )}
                                                </p>
                                            </div>
                                        </div>
                                    </button>
                                )
                            })}
                        </div>
                    )}
                </div>
            )}
            {error && <FieldError className="mt-4">{error}</FieldError>}
            <div className="mt-5 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={onCancel}>
                    {t("cancel")}
                </Button>
                <Button
                    type="button"
                    onClick={() => onAssign(selectedAccountIds)}
                    disabled={isBusy || selectedAccountIds.size === 0}
                >
                    {isBusy && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
                    {t("assign-selected-students", {
                        count: selectedAccountIds.size,
                    })}
                </Button>
            </div>
        </>
    )
}
