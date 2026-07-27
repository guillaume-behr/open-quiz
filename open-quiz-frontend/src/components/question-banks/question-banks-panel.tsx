import {
    ApiError,
    createQuestionBank,
    downloadQuestionBank,
    downloadQuestionBatchExample,
    getQuestionBanks,
    getQuestions,
    importQuestionBatch,
    type Question,
    type QuestionBank,
} from "@/api/api"
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
    Upload,
} from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

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

export function QuestionBanksPanel() {
    const { t } = useTranslation()
    const [questionBanks, setQuestionBanks] = useState<QuestionBank[]>([])
    const [gradeLevel, setGradeLevel] = useState("")
    const [chapter, setChapter] = useState("")
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
    const importInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        let isActive = true

        getQuestionBanks()
            .then((banks) => {
                if (isActive) setQuestionBanks(banks)
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
        if (selectedBankId === null) return
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
    }, [selectedBankId, t])

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setCreateError(null)
        setIsCreating(true)

        try {
            const created = await createQuestionBank({
                grade_level: gradeLevel.trim(),
                chapter: chapter.trim(),
            })
            setQuestionBanks((banks) =>
                [...banks, created].sort(compareQuestionBanks)
            )
            setGradeLevel("")
            setChapter("")
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

    const selectedBank = questionBanks.find(
        (bank) => bank.id === selectedBankId
    )

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

    async function handleImport(file: File): Promise<void> {
        setImportError(null)
        setBatchMessage(null)
        setIsBatchBusy(true)
        try {
            const imported = await importQuestionBatch(file)
            setQuestionBanks((banks) =>
                [...banks, imported.question_bank].sort(compareQuestionBanks)
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
            <div className="grid gap-5 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
                <form
                    className="h-fit rounded-xl border bg-background p-4"
                    onSubmit={handleSubmit}
                >
                    <h3 className="font-semibold">
                        {t("create-question-bank")}
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("create-question-bank-help")}
                    </p>

                    <FieldGroup className="mt-4 gap-4">
                        <Field>
                            <FieldLabel htmlFor="question-bank-grade-level">
                                {t("grade-level")}
                            </FieldLabel>
                            <Input
                                id="question-bank-grade-level"
                                value={gradeLevel}
                                onChange={(event) =>
                                    setGradeLevel(event.target.value)
                                }
                                maxLength={80}
                                placeholder={t("grade-level-placeholder")}
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="question-bank-chapter">
                                {t("chapter")}
                            </FieldLabel>
                            <Input
                                id="question-bank-chapter"
                                value={chapter}
                                onChange={(event) =>
                                    setChapter(event.target.value)
                                }
                                maxLength={160}
                                placeholder={t("chapter-placeholder")}
                                required
                            />
                        </Field>
                        {createError && <FieldError>{createError}</FieldError>}
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
                    </FieldGroup>
                </form>

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
                    {loadError && (
                        <p
                            role="alert"
                            className="mt-3 text-sm text-destructive"
                        >
                            {loadError}
                        </p>
                    )}
                    {isLoading ? (
                        <div className="flex min-h-32 items-center justify-center">
                            <LoaderCircle className="size-6 animate-spin text-primary" />
                        </div>
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
                    ) : (
                        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
                            {questionBanks.map((bank) => (
                                <li
                                    key={bank.id}
                                    className="relative rounded-xl border bg-background p-4"
                                >
                                    <span className="absolute top-4 right-4 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                                        {t("question-count", {
                                            count: bank.question_count,
                                        })}
                                    </span>
                                    <div className="flex items-start gap-3 pr-24">
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
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </div>

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
                                            <div className="flex items-start justify-between gap-3">
                                                <p className="font-semibold">
                                                    {index + 1}.{" "}
                                                    {question.prompt}
                                                </p>
                                                <div className="flex shrink-0 items-center gap-2">
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
                                            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                                                {question.choices.map(
                                                    (choice) => (
                                                        <li
                                                            key={choice.id}
                                                            className="rounded-lg bg-muted/60 px-3 py-2 text-sm"
                                                        >
                                                            <div className="flex items-center gap-2">
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
                                                                <span className="min-w-0 flex-1">
                                                                    {
                                                                        choice.label
                                                                    }
                                                                </span>
                                                                <span className="shrink-0 rounded-full bg-background px-2 py-0.5 text-xs font-semibold">
                                                                    {t(
                                                                        "points-value",
                                                                        {
                                                                            count: choice.points,
                                                                        }
                                                                    )}
                                                                </span>
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
                                                            : "multiple-choice"
                                                    )}
                                                </span>
                                                <span>•</span>
                                                <span>
                                                    {t(
                                                    question.correction_mode ===
                                                    "automatic"
                                                        ? "automatic-correction-full"
                                                        : "manual-correction-full"
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
                            onCancel={() => setIsQuestionFormOpen(false)}
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
