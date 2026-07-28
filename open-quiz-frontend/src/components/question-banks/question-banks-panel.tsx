import {
    createQuestionBank,
    deleteQuestionBank,
    deleteQuestion,
    downloadQuestionBank,
    downloadQuestionBatchExample,
    getQuestionBanks,
    getQuestions,
    importQuestionBatch,
} from "@/api/question-banks"
import { ApiError } from "@/api/client"
import type { Question, QuestionBank } from "@/api/types"
import { QuestionForm } from "@/components/question-banks/question-form"
import { QuestionImage } from "@/components/question-banks/question-image"
import { ChoiceImage } from "@/components/question-banks/choice-image"
import { CodeBlock } from "@/components/question-banks/code-block"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
    BookOpenText,
    Download,
    Eye,
    FileJson,
    ImageIcon,
    LoaderCircle,
    Pencil,
    Plus,
    Settings2,
    Trash2,
    Upload,
} from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

const DEFAULT_GRADE_LEVELS = ["2de", "1re", "Terminale"]
const selectClassName =
    "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

function compareQuestionBanks(
    first: QuestionBank,
    second: QuestionBank
): number {
    return (
        first.grade_level.localeCompare(second.grade_level, "fr") ||
        first.chapter.localeCompare(second.chapter, "fr")
    )
}

function saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function exportFilename(bank: QuestionBank): string {
    const safeName = `${bank.grade_level}-${bank.chapter}`
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase()
    return `banque-${safeName || bank.id}.json`
}

type QuestionBanksPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}

export function QuestionBanksPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: QuestionBanksPanelProps) {
    const { t } = useTranslation()
    const [questionBanks, setQuestionBanks] = useState<QuestionBank[]>([])
    const [gradeLevel, setGradeLevel] = useState("")
    const [title, setTitle] = useState("")
    const [titleFilter, setTitleFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const [gradeLevels, setGradeLevels] = useState(DEFAULT_GRADE_LEVELS)
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isLoading, setIsLoading] = useState(true)
    const [isCreating, setIsCreating] = useState(false)
    const [createError, setCreateError] = useState<string | null>(null)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [selectedBankId, setSelectedBankId] = useState<number | null>(null)
    const [questions, setQuestions] = useState<Question[]>([])
    const [areQuestionsLoading, setAreQuestionsLoading] = useState(false)
    const [questionsError, setQuestionsError] = useState<string | null>(null)
    const [isQuestionFormOpen, setIsQuestionFormOpen] = useState(false)
    const [isQuestionsDialogOpen, setIsQuestionsDialogOpen] = useState(false)
    const [editingQuestion, setEditingQuestion] = useState<Question | null>(
        null
    )
    const [isBatchBusy, setIsBatchBusy] = useState(false)
    const [batchMessage, setBatchMessage] = useState<string | null>(null)
    const [batchError, setBatchError] = useState<string | null>(null)
    const [importError, setImportError] = useState<string | null>(null)
    const [isImportDialogOpen, setIsImportDialogOpen] = useState(false)
    const [importFile, setImportFile] = useState<File | null>(null)
    const [bankToDelete, setBankToDelete] = useState<QuestionBank | null>(null)
    const [isDeletingBank, setIsDeletingBank] = useState(false)
    const [deleteBankError, setDeleteBankError] = useState<string | null>(null)
    const [questionToDelete, setQuestionToDelete] = useState<Question | null>(
        null
    )
    const [isDeletingQuestion, setIsDeletingQuestion] = useState(false)
    const [deleteQuestionError, setDeleteQuestionError] = useState<
        string | null
    >(null)
    const importInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        let isActive = true

        getQuestionBanks()
            .then((banks) => {
                if (!isActive) return
                setQuestionBanks(banks)
                setGradeLevels((levels) => [
                    ...levels,
                    ...Array.from(
                        new Set(
                            banks
                                .map((bank) => bank.grade_level)
                                .filter((level) => !levels.includes(level))
                        )
                    ),
                ])
            })
            .catch(() => {
                if (isActive) setLoadError(t("question-banks-load-error"))
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })

        return () => {
            isActive = false
        }
    }, [t])

    useEffect(() => {
        if (!isQuestionsDialogOpen || selectedBankId === null) return
        let isActive = true

        getQuestions(selectedBankId)
            .then((loadedQuestions) => {
                if (isActive) setQuestions(loadedQuestions)
            })
            .catch(() => {
                if (isActive) setQuestionsError(t("questions-load-error"))
            })
            .finally(() => {
                if (isActive) setAreQuestionsLoading(false)
            })

        return () => {
            isActive = false
        }
    }, [isQuestionsDialogOpen, selectedBankId, t])

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setCreateError(null)
        setIsCreating(true)

        try {
            const created = await createQuestionBank({
                grade_level: gradeLevel.trim(),
                chapter: title.trim(),
            })
            setQuestionBanks((banks) =>
                [...banks, created].sort(compareQuestionBanks)
            )
            setGradeLevel("")
            setTitle("")
            onCreateDialogOpenChange(false)
        } catch (caughtError) {
            setCreateError(
                caughtError instanceof ApiError && caughtError.status === 409
                    ? t("question-bank-duplicate-error")
                    : t("question-bank-create-error")
            )
        } finally {
            setIsCreating(false)
        }
    }

    function addGradeLevel(): void {
        const normalizedLevel = newGradeLevel.trim()
        if (!normalizedLevel) return
        setGradeLevels((levels) =>
            levels.includes(normalizedLevel)
                ? levels
                : [...levels, normalizedLevel]
        )
        setGradeLevel(normalizedLevel)
        setNewGradeLevel("")
        setIsAddingGradeLevel(false)
    }

    const selectedBank = questionBanks.find(
        (bank) => bank.id === selectedBankId
    )
    const filteredQuestionBanks = questionBanks.filter((bank) => {
        const matchesGradeLevel =
            !gradeLevelFilter || bank.grade_level === gradeLevelFilter
        const matchesTitle = bank.chapter
            .toLocaleLowerCase("fr")
            .includes(titleFilter.trim().toLocaleLowerCase("fr"))
        return matchesGradeLevel && matchesTitle
    })

    function openQuestions(bankId: number): void {
        setAreQuestionsLoading(true)
        setQuestionsError(null)
        setQuestions([])
        setSelectedBankId(bankId)
        setIsQuestionsDialogOpen(true)
    }

    async function handleDownloadExample(): Promise<void> {
        setBatchError(null)
        setIsBatchBusy(true)
        try {
            saveBlob(
                await downloadQuestionBatchExample(),
                "open-quiz-questions-example.json"
            )
        } catch {
            setBatchError(t("json-download-error"))
        } finally {
            setIsBatchBusy(false)
        }
    }

    async function handleExport(bank: QuestionBank): Promise<void> {
        setBatchError(null)
        setBatchMessage(null)
        setIsBatchBusy(true)
        try {
            saveBlob(await downloadQuestionBank(bank.id), exportFilename(bank))
        } catch {
            setBatchError(t("json-export-error"))
        } finally {
            setIsBatchBusy(false)
        }
    }

    async function handleDeleteBank(): Promise<void> {
        if (!bankToDelete) return

        setDeleteBankError(null)
        setIsDeletingBank(true)
        try {
            await deleteQuestionBank(bankToDelete.id)
            setQuestionBanks((banks) =>
                banks.filter((bank) => bank.id !== bankToDelete.id)
            )
            if (selectedBankId === bankToDelete.id) {
                setSelectedBankId(null)
                setIsQuestionsDialogOpen(false)
            }
            setBankToDelete(null)
        } catch (caughtError) {
            setDeleteBankError(
                caughtError instanceof ApiError && caughtError.status === 409
                    ? t("question-bank-in-use-error")
                    : t("question-bank-delete-error")
            )
        } finally {
            setIsDeletingBank(false)
        }
    }

    async function handleDeleteQuestion(): Promise<void> {
        if (!questionToDelete || !selectedBank) return

        setDeleteQuestionError(null)
        setIsDeletingQuestion(true)
        try {
            await deleteQuestion(questionToDelete.id)
            setQuestions((current) =>
                current.filter(
                    (question) => question.id !== questionToDelete.id
                )
            )
            setQuestionBanks((banks) =>
                banks.map((bank) =>
                    bank.id === selectedBank.id
                        ? {
                              ...bank,
                              question_count: Math.max(
                                  0,
                                  bank.question_count - 1
                              ),
                          }
                        : bank
                )
            )
            setQuestionToDelete(null)
            setIsQuestionsDialogOpen(true)
        } catch (caughtError) {
            setDeleteQuestionError(
                caughtError instanceof ApiError && caughtError.status === 409
                    ? t("question-in-use-error")
                    : t("question-delete-error")
            )
        } finally {
            setIsDeletingQuestion(false)
        }
    }

    async function handleImport(file: File): Promise<void> {
        setImportError(null)
        setBatchMessage(null)
        setIsBatchBusy(true)
        try {
            const imported = await importQuestionBatch(file)
            setQuestionBanks((banks) =>
                [...banks, imported.question_bank].sort(compareQuestionBanks)
            )
            setGradeLevels((levels) =>
                levels.includes(imported.question_bank.grade_level)
                    ? levels
                    : [...levels, imported.question_bank.grade_level]
            )
            setBatchMessage(
                t("questions-imported", {
                    count: imported.questions.length,
                })
            )
            setIsImportDialogOpen(false)
            setImportFile(null)
        } catch (caughtError) {
            setImportError(
                caughtError instanceof ApiError && caughtError.status === 409
                    ? t("json-import-duplicate-error")
                    : t("json-import-error")
            )
        } finally {
            setIsBatchBusy(false)
            if (importInputRef.current) importInputRef.current.value = ""
        }
    }

    function openImportDialog(): void {
        setBatchError(null)
        setImportError(null)
        setBatchMessage(null)
        setImportFile(null)
        if (importInputRef.current) importInputRef.current.value = ""
        setIsImportDialogOpen(true)
    }

    function handleImportSubmit(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault()
        if (!importFile) return
        void handleImport(importFile)
    }

    return (
        <div className="mt-6">
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
                                    setTitleFilter(event.target.value)
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
                                className={selectClassName}
                                value={gradeLevelFilter}
                                onChange={(event) =>
                                    setGradeLevelFilter(event.target.value)
                                }
                            >
                                <option value="">
                                    {t("all-grade-levels")}
                                </option>
                                {gradeLevels.map((level) => (
                                    <option key={level} value={level}>
                                        {level}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        {(titleFilter || gradeLevelFilter) && (
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                    setTitleFilter("")
                                    setGradeLevelFilter("")
                                }}
                            >
                                {t("clear-filters")}
                            </Button>
                        )}
                    </FieldGroup>
                </aside>

                <div>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="font-semibold">
                            {t("my-question-banks")}
                        </h3>
                        <div className="flex flex-wrap gap-2">
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={isBatchBusy}
                                onClick={openImportDialog}
                            >
                                <Upload />
                                {t("import-json")}
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={isBatchBusy}
                                onClick={() => void handleDownloadExample()}
                            >
                                <FileJson />
                                {t("download-json-example")}
                            </Button>
                        </div>
                    </div>
                    {batchError && (
                        <p
                            role="alert"
                            className="mt-3 text-sm text-destructive"
                        >
                            {batchError}
                        </p>
                    )}
                    {batchMessage && (
                        <p role="status" className="mt-3 text-sm text-primary">
                            {batchMessage}
                        </p>
                    )}
                    {isLoading ? (
                        <div className="flex min-h-32 items-center justify-center">
                            <LoaderCircle className="size-6 animate-spin text-primary" />
                        </div>
                    ) : loadError ? (
                        <p
                            role="alert"
                            className="mt-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                        >
                            {loadError}
                        </p>
                    ) : questionBanks.length === 0 ? (
                        <div className="mt-3 flex min-h-32 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                            <BookOpenText className="mb-2 size-8" />
                            <p className="font-medium">
                                {t("no-question-bank")}
                            </p>
                            <p className="mt-1 text-sm">
                                {t("no-question-bank-help")}
                            </p>
                        </div>
                    ) : filteredQuestionBanks.length === 0 ? (
                        <div className="mt-3 flex min-h-32 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                            <p className="font-medium">
                                {t("no-question-bank-filtered")}
                            </p>
                            <Button
                                type="button"
                                className="mt-3"
                                variant="outline"
                                onClick={() => {
                                    setTitleFilter("")
                                    setGradeLevelFilter("")
                                }}
                            >
                                {t("clear-filters")}
                            </Button>
                        </div>
                    ) : (
                        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
                            {filteredQuestionBanks.map((bank) => (
                                <li
                                    key={bank.id}
                                    className="relative rounded-xl border bg-background p-4 pb-16"
                                >
                                    <span className="absolute top-4 right-4 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                                        {t("question-count", {
                                            count: bank.question_count,
                                        })}
                                    </span>
                                    <div className="flex items-start gap-3 pr-16">
                                        <div className="rounded-lg bg-primary/10 p-2 text-primary">
                                            <BookOpenText className="size-5" />
                                        </div>
                                        <div className="min-w-0">
                                            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                                                {bank.grade_level}
                                            </p>
                                            <p className="mt-1 font-semibold break-words">
                                                {bank.chapter}
                                            </p>
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                        openQuestions(bank.id)
                                                    }
                                                >
                                                    <Eye />
                                                    {t("view-questions")}
                                                </Button>
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant="outline"
                                                    disabled={isBatchBusy}
                                                    onClick={() =>
                                                        void handleExport(bank)
                                                    }
                                                >
                                                    <Download />
                                                    {t("export-json")}
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                    <Button
                                        type="button"
                                        size="icon"
                                        variant="destructive"
                                        className="absolute right-4 bottom-4"
                                        aria-label={t("delete-question-bank")}
                                        title={t("delete-question-bank")}
                                        onClick={() => {
                                            setDeleteBankError(null)
                                            setBankToDelete(bank)
                                        }}
                                    >
                                        <Trash2 />
                                    </Button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </div>

            <Dialog
                open={isCreateDialogOpen}
                onOpenChange={(open) => {
                    if (!isCreating) {
                        onCreateDialogOpenChange(open)
                        if (!open) setCreateError(null)
                    }
                }}
                title={t("create-question-bank")}
                description={t("create-question-bank-help")}
                className="max-w-lg"
            >
                <form onSubmit={handleSubmit}>
                    <FieldGroup className="gap-4">
                        <Field>
                            <FieldLabel htmlFor="question-bank-grade-level">
                                {t("grade-level")}
                            </FieldLabel>
                            <div className="flex gap-2">
                                <select
                                    id="question-bank-grade-level"
                                    className={selectClassName}
                                    value={gradeLevel}
                                    onChange={(event) =>
                                        setGradeLevel(event.target.value)
                                    }
                                    required
                                >
                                    <option value="" disabled>
                                        {t("choose-grade-level")}
                                    </option>
                                    {gradeLevels.map((level) => (
                                        <option key={level} value={level}>
                                            {level}
                                        </option>
                                    ))}
                                </select>
                                <Button
                                    type="button"
                                    size="icon"
                                    variant="outline"
                                    aria-label={t("add-grade-level")}
                                    onClick={() =>
                                        setIsAddingGradeLevel((value) => !value)
                                    }
                                >
                                    <Plus />
                                </Button>
                            </div>
                            {isAddingGradeLevel && (
                                <div className="mt-2 flex gap-2">
                                    <Input
                                        value={newGradeLevel}
                                        onChange={(event) =>
                                            setNewGradeLevel(event.target.value)
                                        }
                                        maxLength={80}
                                        placeholder={t(
                                            "grade-level-placeholder"
                                        )}
                                    />
                                    <Button
                                        type="button"
                                        size="sm"
                                        onClick={addGradeLevel}
                                    >
                                        {t("save-grade-level")}
                                    </Button>
                                </div>
                            )}
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="question-bank-title">
                                {t("question-bank-title")}
                            </FieldLabel>
                            <Input
                                id="question-bank-title"
                                value={title}
                                onChange={(event) =>
                                    setTitle(event.target.value)
                                }
                                maxLength={160}
                                placeholder={t(
                                    "question-bank-title-placeholder"
                                )}
                                required
                            />
                        </Field>
                        {createError && <FieldError>{createError}</FieldError>}
                        <div className="flex justify-end gap-2 border-t pt-4">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={isCreating}
                                onClick={() => onCreateDialogOpenChange(false)}
                            >
                                {t("cancel")}
                            </Button>
                            <Button type="submit" disabled={isCreating}>
                                {isCreating ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Plus />
                                )}
                                {isCreating
                                    ? t("creating-question-bank")
                                    : t("create-question-bank-action")}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={isImportDialogOpen}
                onOpenChange={(open) => {
                    setIsImportDialogOpen(open)
                    if (!open) {
                        setImportError(null)
                        setImportFile(null)
                    }
                }}
                title={t("import-json-title")}
                description={t("import-json-help")}
                className="max-w-lg"
            >
                <form onSubmit={handleImportSubmit}>
                    <FieldGroup className="gap-4">
                        <Field>
                            <FieldLabel htmlFor="import-json-file">
                                {t("json-file")}
                            </FieldLabel>
                            <Input
                                ref={importInputRef}
                                id="import-json-file"
                                type="file"
                                accept="application/json,.json"
                                onChange={(event) =>
                                    setImportFile(
                                        event.target.files?.[0] ?? null
                                    )
                                }
                                required
                            />
                        </Field>
                        {importError && <FieldError>{importError}</FieldError>}
                        <div className="flex justify-end gap-2 border-t pt-4">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setIsImportDialogOpen(false)}
                            >
                                {t("cancel")}
                            </Button>
                            <Button
                                type="submit"
                                disabled={isBatchBusy || !importFile}
                            >
                                {isBatchBusy ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Upload />
                                )}
                                {isBatchBusy
                                    ? t("importing-json")
                                    : t("import-json")}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={bankToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !isDeletingBank) {
                        setBankToDelete(null)
                        setDeleteBankError(null)
                    }
                }}
                title={t("delete-question-bank")}
                description={t("delete-question-bank-help", {
                    title: bankToDelete?.chapter ?? "",
                })}
                className="max-w-md"
            >
                <div className="space-y-4">
                    {deleteBankError && (
                        <FieldError>{deleteBankError}</FieldError>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isDeletingBank}
                            onClick={() => setBankToDelete(null)}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            type="button"
                            variant="destructive"
                            disabled={isDeletingBank}
                            onClick={() => void handleDeleteBank()}
                        >
                            {isDeletingBank && (
                                <LoaderCircle className="animate-spin" />
                            )}
                            {t("delete-question-bank")}
                        </Button>
                    </div>
                </div>
            </Dialog>

            {selectedBank && (
                <>
                    <Dialog
                        open={isQuestionsDialogOpen}
                        onOpenChange={setIsQuestionsDialogOpen}
                        title={selectedBank.chapter}
                        description={`${selectedBank.grade_level} — ${t("bank-questions")}`}
                    >
                        <div className="flex flex-wrap justify-end gap-2">
                            <Button
                                type="button"
                                onClick={() => {
                                    setIsQuestionsDialogOpen(false)
                                    setEditingQuestion(null)
                                    setIsQuestionFormOpen(true)
                                }}
                            >
                                <Plus />
                                {t("add-question")}
                            </Button>
                        </div>

                        <div className="mt-5">
                            <h4 className="font-semibold">
                                {t("bank-questions")}
                            </h4>
                            {areQuestionsLoading ? (
                                <div className="flex min-h-24 items-center justify-center">
                                    <LoaderCircle className="size-6 animate-spin text-primary" />
                                </div>
                            ) : questionsError ? (
                                <p
                                    role="alert"
                                    className="mt-3 text-sm text-destructive"
                                >
                                    {questionsError}
                                </p>
                            ) : questions.length === 0 ? (
                                <p className="mt-3 rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                                    {t("no-question")}
                                </p>
                            ) : (
                                <ol className="mt-3 space-y-3">
                                    {questions.map((question, index) => (
                                        <li
                                            key={question.id}
                                            className="rounded-xl border bg-background p-4"
                                        >
                                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                                <p className="min-w-0 font-semibold break-words">
                                                    {index + 1}.{" "}
                                                    {question.prompt}
                                                </p>
                                                <div className="flex shrink-0 flex-wrap items-center gap-2">
                                                    <span className="rounded-full bg-muted px-2 py-1 text-xs whitespace-nowrap">
                                                        {t(
                                                            `difficulty-${question.difficulty}`
                                                        )}
                                                    </span>
                                                    <Button
                                                        type="button"
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() => {
                                                            setEditingQuestion(
                                                                question
                                                            )
                                                            setIsQuestionsDialogOpen(
                                                                false
                                                            )
                                                            setIsQuestionFormOpen(
                                                                true
                                                            )
                                                        }}
                                                    >
                                                        <Pencil />
                                                        {t("edit")}
                                                    </Button>
                                                    <Button
                                                        type="button"
                                                        size="icon"
                                                        variant="destructive"
                                                        aria-label={t(
                                                            "delete-question"
                                                        )}
                                                        title={t(
                                                            "delete-question"
                                                        )}
                                                        onClick={() => {
                                                            setDeleteQuestionError(
                                                                null
                                                            )
                                                            setQuestionToDelete(
                                                                question
                                                            )
                                                            setIsQuestionsDialogOpen(
                                                                false
                                                            )
                                                        }}
                                                    >
                                                        <Trash2 />
                                                    </Button>
                                                </div>
                                            </div>
                                            {question.has_image && (
                                                <>
                                                    <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                                                        <ImageIcon className="size-3.5" />
                                                        {t("image-attached")}
                                                    </div>
                                                    <QuestionImage
                                                        questionId={question.id}
                                                        alt={question.prompt}
                                                    />
                                                </>
                                            )}
                                            {question.code_content &&
                                                question.code_language && (
                                                    <div className="mt-3">
                                                        <CodeBlock
                                                            code={
                                                                question.code_content
                                                            }
                                                            language={
                                                                question.code_language
                                                            }
                                                        />
                                                    </div>
                                                )}
                                            <ul
                                                className={`mt-3 grid gap-2 ${
                                                    question.answer_mode ===
                                                    "written"
                                                        ? ""
                                                        : "sm:grid-cols-2"
                                                }`}
                                            >
                                                {question.choices.map(
                                                    (choice) => (
                                                        <li
                                                            key={choice.id}
                                                            className="rounded-lg bg-muted/60 px-3 py-2 text-sm"
                                                        >
                                                            <div className="flex items-center gap-2">
                                                                {question.answer_mode !==
                                                                    "written" && (
                                                                    <span
                                                                        className={
                                                                            choice.is_correct
                                                                                ? "text-primary"
                                                                                : "text-muted-foreground"
                                                                        }
                                                                    >
                                                                        {choice.is_correct
                                                                            ? "✓"
                                                                            : "○"}
                                                                    </span>
                                                                )}
                                                                <span className="min-w-0 flex-1 whitespace-pre-wrap">
                                                                    {question.answer_mode ===
                                                                        "written" && (
                                                                        <span className="mb-1 block text-xs font-semibold text-muted-foreground">
                                                                            {t(
                                                                                "expected-written-answer"
                                                                            )}
                                                                        </span>
                                                                    )}
                                                                    {
                                                                        choice.label
                                                                    }
                                                                </span>
                                                                {question.answer_mode !==
                                                                    "written" && (
                                                                    <span className="shrink-0 rounded-full bg-background px-2 py-0.5 text-xs font-semibold">
                                                                        {t(
                                                                            "points-value",
                                                                            {
                                                                                count: choice.points,
                                                                            }
                                                                        )}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            {choice.has_image && (
                                                                <ChoiceImage
                                                                    choiceId={
                                                                        choice.id
                                                                    }
                                                                    alt={
                                                                        choice.label
                                                                    }
                                                                />
                                                            )}
                                                            {choice.code_content &&
                                                                choice.code_language && (
                                                                    <div className="mt-2">
                                                                        <CodeBlock
                                                                            code={
                                                                                choice.code_content
                                                                            }
                                                                            language={
                                                                                choice.code_language
                                                                            }
                                                                        />
                                                                    </div>
                                                                )}
                                                        </li>
                                                    )
                                                )}
                                            </ul>
                                            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                                                <span className="flex items-center gap-1">
                                                    <Settings2 className="size-3.5" />
                                                    {t(
                                                        question.answer_mode ===
                                                            "single"
                                                            ? "single-choice"
                                                            : question.answer_mode ===
                                                                "multiple"
                                                              ? "multiple-choice"
                                                              : "written-answer"
                                                    )}
                                                </span>
                                                {!question.answer_mode_disclosed && (
                                                    <>
                                                        <span>•</span>
                                                        <span>
                                                            {t(
                                                                "answer-mode-not-disclosed"
                                                            )}
                                                        </span>
                                                    </>
                                                )}
                                            </div>
                                        </li>
                                    ))}
                                </ol>
                            )}
                        </div>
                    </Dialog>

                    <Dialog
                        open={questionToDelete !== null}
                        onOpenChange={(open) => {
                            if (!open && !isDeletingQuestion) {
                                setQuestionToDelete(null)
                                setDeleteQuestionError(null)
                                setIsQuestionsDialogOpen(true)
                            }
                        }}
                        title={t("delete-question")}
                        description={t("delete-question-help", {
                            title: questionToDelete?.prompt ?? "",
                        })}
                        className="max-w-md"
                    >
                        <div className="space-y-4">
                            {deleteQuestionError && (
                                <FieldError>{deleteQuestionError}</FieldError>
                            )}
                            <div className="flex justify-end gap-2">
                                <Button
                                    type="button"
                                    variant="outline"
                                    disabled={isDeletingQuestion}
                                    onClick={() => {
                                        setQuestionToDelete(null)
                                        setDeleteQuestionError(null)
                                        setIsQuestionsDialogOpen(true)
                                    }}
                                >
                                    {t("cancel")}
                                </Button>
                                <Button
                                    type="button"
                                    variant="destructive"
                                    disabled={isDeletingQuestion}
                                    onClick={() => void handleDeleteQuestion()}
                                >
                                    {isDeletingQuestion && (
                                        <LoaderCircle className="animate-spin" />
                                    )}
                                    {t("delete-question")}
                                </Button>
                            </div>
                        </div>
                    </Dialog>

                    <Dialog
                        open={isQuestionFormOpen}
                        onOpenChange={(open) => {
                            setIsQuestionFormOpen(open)
                            if (!open) setEditingQuestion(null)
                        }}
                        title={t(
                            editingQuestion ? "edit-question" : "add-question"
                        )}
                        description={`${selectedBank.grade_level} — ${selectedBank.chapter}`}
                    >
                        <QuestionForm
                            key={editingQuestion?.id ?? "new"}
                            questionBankId={selectedBank.id}
                            question={editingQuestion ?? undefined}
                            onCancel={() => {
                                setIsQuestionFormOpen(false)
                                setEditingQuestion(null)
                                setIsQuestionsDialogOpen(true)
                            }}
                            onSaved={(savedQuestion) => {
                                if (!editingQuestion) {
                                    setQuestionBanks((banks) =>
                                        banks.map((bank) =>
                                            bank.id === selectedBank.id
                                                ? {
                                                      ...bank,
                                                      question_count:
                                                          bank.question_count +
                                                          1,
                                                  }
                                                : bank
                                        )
                                    )
                                }
                                setQuestions((current) =>
                                    editingQuestion
                                        ? current.map((question) =>
                                              question.id === savedQuestion.id
                                                  ? savedQuestion
                                                  : question
                                          )
                                        : [savedQuestion, ...current]
                                )
                                setIsQuestionFormOpen(false)
                                setEditingQuestion(null)
                                setIsQuestionsDialogOpen(true)
                            }}
                        />
                    </Dialog>
                </>
            )}
        </div>
    )
}
