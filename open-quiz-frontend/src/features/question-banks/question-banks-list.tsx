import type { GradeLevel, QuestionBank } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-levels/grade-level-select"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import {
    BookOpenText,
    Download,
    FileJson,
    Pencil,
    Trash2,
    Upload,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { LoadingState } from "@/components/ui/loading-state"
import { AnimatedGrid } from "@/components/ui/animated-grid"
import { FilterSidebar } from "@/components/ui/filter-sidebar"

type QuestionBanksListProps = {
    banks: QuestionBank[]
    gradeLevels: GradeLevel[]
    titleFilter: string
    gradeLevelFilter: string
    isLoading: boolean
    loadError: string | null
    isBatchBusy: boolean
    batchError: string | null
    batchMessage: string | null
    onTitleFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onImport: () => void
    onDownloadExample: () => void
    onExport: (bank: QuestionBank) => void
    onEdit: (bank: QuestionBank) => void
    onDelete: (bank: QuestionBank) => void
    page: number
    totalPages: number
    onPageChange: (page: number) => void
}

export function QuestionBanksList({
    banks,
    gradeLevels,
    titleFilter,
    gradeLevelFilter,
    isLoading,
    loadError,
    isBatchBusy,
    batchError,
    batchMessage,
    onTitleFilterChange,
    onGradeLevelFilterChange,
    onDeleteGradeLevel,
    onImport,
    onDownloadExample,
    onExport,
    onEdit,
    onDelete,
    page,
    totalPages,
    onPageChange,
}: QuestionBanksListProps) {
    const { t } = useTranslation()
    const clearFilters = () => {
        onTitleFilterChange("")
        onGradeLevelFilterChange("")
    }

    return (
        <div className="grid gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
            <FilterSidebar
                hasFilters={Boolean(titleFilter || gradeLevelFilter)}
                onClear={clearFilters}
            >
                <Field>
                    <FieldLabel htmlFor="question-bank-title-filter">
                        {t("search")}
                    </FieldLabel>
                    <Input
                        id="question-bank-title-filter"
                        value={titleFilter}
                        onChange={(event) =>
                            onTitleFilterChange(event.target.value)
                        }
                        placeholder={t("search-question-bank")}
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="question-bank-grade-filter">
                        {t("grade-level")}
                    </FieldLabel>
                    <GradeLevelSelect
                        id="question-bank-grade-filter"
                        value={gradeLevelFilter}
                        levels={gradeLevels}
                        onChange={onGradeLevelFilterChange}
                        onDelete={onDeleteGradeLevel}
                        required={false}
                        placeholder={t("all-grade-levels")}
                    />
                </Field>
            </FilterSidebar>
            <div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-semibold">{t("my-question-banks")}</h3>
                    <div className="flex flex-wrap gap-2">
                        <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={isBatchBusy}
                            onClick={onImport}
                        >
                            <Upload />
                            {t("import-json")}
                        </Button>
                        <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={isBatchBusy}
                            onClick={onDownloadExample}
                        >
                            <FileJson />
                            {t("download-json-example")}
                        </Button>
                    </div>
                </div>
                {batchError && (
                    <p role="alert" className="mt-3 text-sm text-destructive">
                        {batchError}
                    </p>
                )}
                {batchMessage && (
                    <p role="status" className="mt-3 text-sm text-primary">
                        {batchMessage}
                    </p>
                )}
                <BanksContent
                    banks={banks}
                    hasActiveFilters={Boolean(titleFilter || gradeLevelFilter)}
                    isLoading={isLoading}
                    loadError={loadError}
                    isBatchBusy={isBatchBusy}
                    onClearFilters={clearFilters}
                    onExport={onExport}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    page={page}
                    totalPages={totalPages}
                    onPageChange={onPageChange}
                />
            </div>
        </div>
    )
}

function BanksContent({
    banks,
    hasActiveFilters,
    isLoading,
    loadError,
    isBatchBusy,
    onClearFilters,
    onExport,
    onEdit,
    onDelete,
    page,
    totalPages,
    onPageChange,
}: {
    banks: QuestionBank[]
    hasActiveFilters: boolean
    isLoading: boolean
    loadError: string | null
    isBatchBusy: boolean
    onClearFilters: () => void
    onExport: (bank: QuestionBank) => void
    onEdit: (bank: QuestionBank) => void
    onDelete: (bank: QuestionBank) => void
    page: number
    totalPages: number
    onPageChange: (page: number) => void
}) {
    const { t } = useTranslation()
    if (isLoading) return <LoadingState className="min-h-32" size={6} />
    if (loadError)
        return (
            <p
                role="alert"
                className="mt-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
            >
                {loadError}
            </p>
        )
    if (banks.length === 0 && hasActiveFilters)
        return (
            <div className="mt-3 flex min-h-32 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                <p className="font-medium">{t("no-question-bank-filtered")}</p>
                <Button
                    type="button"
                    className="mt-3"
                    variant="outline"
                    onClick={onClearFilters}
                >
                    {t("clear-filters")}
                </Button>
            </div>
        )
    if (banks.length === 0)
        return (
            <div className="mt-3 flex min-h-32 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                <BookOpenText className="mb-2 size-8" />
                <p className="font-medium">{t("no-question-bank")}</p>
                <p className="mt-1 text-sm">{t("no-question-bank-help")}</p>
            </div>
        )

    return (
        <>
            <AnimatedGrid
                as="ul"
                ids={banks.map((bank) => bank.id)}
                className="mt-3 gap-3 sm:grid-cols-2"
            >
                {banks.map((bank) => (
                    <li
                        key={bank.id}
                        className="relative rounded-xl border bg-background p-4"
                    >
                        <Button
                            type="button"
                            size="icon-sm"
                            variant="ghost"
                            className="absolute end-12 top-4 z-10"
                            aria-label={t("edit-question-bank-named", {
                                name: bank.chapter,
                            })}
                            title={t("edit-question-bank")}
                            onClick={() => onEdit(bank)}
                        >
                            <Pencil />
                        </Button>
                        <Button
                            type="button"
                            size="icon-sm"
                            variant="destructive"
                            className="absolute end-4 top-4"
                            aria-label={t("delete-question-bank-named", {
                                name: bank.chapter,
                            })}
                            title={t("delete-question-bank")}
                            onClick={() => onDelete(bank)}
                        >
                            <Trash2 />
                        </Button>
                        <div className="flex items-start gap-3 pe-20">
                            <div className="rounded-lg bg-primary/10 p-2 text-primary">
                                <BookOpenText className="size-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                                <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                                    {bank.grade_level}
                                </p>
                                <div className="mt-1 flex flex-wrap items-center gap-2">
                                    <p className="font-semibold break-words">
                                        {bank.chapter}
                                    </p>
                                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                                        {t("question-count", {
                                            count: bank.question_count,
                                        })}
                                    </span>
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={isBatchBusy}
                                        onClick={() => onExport(bank)}
                                    >
                                        <Download />
                                        {t("export-json")}
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </li>
                ))}
            </AnimatedGrid>
            <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPageChange={onPageChange}
            />
        </>
    )
}
