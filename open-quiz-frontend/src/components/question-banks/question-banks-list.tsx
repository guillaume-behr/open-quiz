import type { GradeLevel, QuestionBank } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Pagination } from "@/components/ui/pagination"
import {
    BookOpenText,
    Download,
    FileJson,
    LoaderCircle,
    Pencil,
    Trash2,
    Upload,
} from "lucide-react"
import { useTranslation } from "react-i18next"

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
    onImport: () => void
    onDownloadExample: () => void
    onOpen: (bankId: number) => void
    onExport: (bank: QuestionBank) => void
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
    onImport,
    onDownloadExample,
    onOpen,
    onExport,
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
            <aside className="h-fit rounded-xl border bg-background p-4">
                <h3 className="font-semibold">{t("filters")}</h3>
                <FieldGroup className="mt-4 gap-4">
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
                        <select
                            id="question-bank-grade-filter"
                            className={NATIVE_SELECT_CLASS_NAME}
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
                    {(titleFilter || gradeLevelFilter) && (
                        <Button
                            type="button"
                            variant="outline"
                            onClick={clearFilters}
                        >
                            {t("clear-filters")}
                        </Button>
                    )}
                </FieldGroup>
            </aside>
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
                    onOpen={onOpen}
                    onExport={onExport}
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
    onOpen,
    onExport,
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
    onOpen: (id: number) => void
    onExport: (bank: QuestionBank) => void
    onDelete: (bank: QuestionBank) => void
    page: number
    totalPages: number
    onPageChange: (page: number) => void
}) {
    const { t } = useTranslation()
    if (isLoading)
        return (
            <div className="flex min-h-32 items-center justify-center">
                <LoaderCircle className="size-6 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )
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
            <ul
                key={banks.map((bank) => bank.id).join(",")}
                className="mt-3 grid animate-in gap-3 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none sm:grid-cols-2"
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
                            className="absolute top-4 right-12 z-10"
                            aria-label={t("add-edit-questions")}
                            title={t("add-edit-questions")}
                            onClick={() => onOpen(bank.id)}
                        >
                            <Pencil />
                        </Button>
                        <Button
                            type="button"
                            size="icon-sm"
                            variant="destructive"
                            className="absolute top-4 right-4"
                            aria-label={t("delete-question-bank")}
                            title={t("delete-question-bank")}
                            onClick={() => onDelete(bank)}
                        >
                            <Trash2 />
                        </Button>
                        <div className="flex items-start gap-3 pr-20">
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
            </ul>
            <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPageChange={onPageChange}
            />
        </>
    )
}
