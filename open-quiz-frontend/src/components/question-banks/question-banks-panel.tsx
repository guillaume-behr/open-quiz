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
import type { GradeLevel, Question, QuestionBank } from "@/api/types"
import { QuestionBankFormDialog } from "@/components/question-banks/question-bank-form-dialog"
import {
    DeleteEntityDialog,
    ImportQuestionBankDialog,
    QuestionFormDialog,
} from "@/components/question-banks/question-bank-secondary-dialogs"
import { QuestionBanksList } from "@/components/question-banks/question-banks-list"
import { QuestionsDialog } from "@/components/question-banks/questions-dialog"
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

type QuestionBanksPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
    gradeLevels: GradeLevel[]
    onCreateGradeLevel: (name: string) => Promise<GradeLevel>
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}

export function QuestionBanksPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
    gradeLevels,
    onCreateGradeLevel,
    onDeleteGradeLevel,
}: QuestionBanksPanelProps) {
    const { t } = useTranslation()
    const [questionBanks, setQuestionBanks] = useState<QuestionBank[]>([])
    const [gradeLevel, setGradeLevel] = useState("")
    const [title, setTitle] = useState("")
    const [titleFilter, setTitleFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
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

    async function addGradeLevel(): Promise<void> {
        const normalizedLevel = newGradeLevel.trim()
        if (!normalizedLevel) return
        setCreateError(null)
        try {
            const created = await onCreateGradeLevel(normalizedLevel)
            setGradeLevel(created.name)
            setNewGradeLevel("")
            setIsAddingGradeLevel(false)
        } catch {
            setCreateError(t("grade-level-create-error"))
        }
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
            await onCreateGradeLevel(imported.question_bank.grade_level)
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
            <QuestionBanksList
                banks={questionBanks}
                filteredBanks={filteredQuestionBanks}
                gradeLevels={gradeLevels}
                titleFilter={titleFilter}
                gradeLevelFilter={gradeLevelFilter}
                isLoading={isLoading}
                loadError={loadError}
                isBatchBusy={isBatchBusy}
                batchError={batchError}
                batchMessage={batchMessage}
                onTitleFilterChange={setTitleFilter}
                onGradeLevelFilterChange={setGradeLevelFilter}
                onImport={openImportDialog}
                onDownloadExample={() => void handleDownloadExample()}
                onOpen={openQuestions}
                onExport={(bank) => void handleExport(bank)}
                onDelete={(bank) => {
                    setDeleteBankError(null)
                    setBankToDelete(bank)
                }}
            />

            <QuestionBankFormDialog
                open={isCreateDialogOpen}
                gradeLevels={gradeLevels}
                gradeLevel={gradeLevel}
                title={title}
                newGradeLevel={newGradeLevel}
                isAddingGradeLevel={isAddingGradeLevel}
                isBusy={isCreating}
                error={createError}
                onGradeLevelChange={setGradeLevel}
                onTitleChange={setTitle}
                onNewGradeLevelChange={setNewGradeLevel}
                onAddingGradeLevelChange={setIsAddingGradeLevel}
                onDeleteGradeLevel={async (level) => {
                    setCreateError(null)
                    try {
                        await onDeleteGradeLevel(level)
                    } catch (error) {
                        setCreateError(
                            error instanceof ApiError && error.status === 409
                                ? t("grade-level-in-use-error")
                                : t("grade-level-delete-error")
                        )
                        throw error
                    }
                }}
                onAddGradeLevel={() => void addGradeLevel()}
                onClose={() => {
                    onCreateDialogOpenChange(false)
                    setCreateError(null)
                }}
                onSubmit={handleSubmit}
            />

            <ImportQuestionBankDialog
                open={isImportDialogOpen}
                file={importFile}
                inputRef={importInputRef}
                isBusy={isBatchBusy}
                error={importError}
                onFileChange={setImportFile}
                onClose={() => {
                    setIsImportDialogOpen(false)
                    setImportError(null)
                    setImportFile(null)
                }}
                onSubmit={handleImportSubmit}
            />

            <DeleteEntityDialog
                open={bankToDelete !== null}
                kind="bank"
                title={bankToDelete?.chapter ?? ""}
                isBusy={isDeletingBank}
                error={deleteBankError}
                onClose={() => {
                    setBankToDelete(null)
                    setDeleteBankError(null)
                }}
                onConfirm={() => void handleDeleteBank()}
            />

            {selectedBank && (
                <>
                    <QuestionsDialog
                        bank={selectedBank}
                        questions={questions}
                        open={isQuestionsDialogOpen}
                        isLoading={areQuestionsLoading}
                        error={questionsError}
                        onOpenChange={setIsQuestionsDialogOpen}
                        onAdd={() => {
                            setIsQuestionsDialogOpen(false)
                            setEditingQuestion(null)
                            setIsQuestionFormOpen(true)
                        }}
                        onEdit={(question) => {
                            setEditingQuestion(question)
                            setIsQuestionsDialogOpen(false)
                            setIsQuestionFormOpen(true)
                        }}
                        onDelete={(question) => {
                            setDeleteQuestionError(null)
                            setQuestionToDelete(question)
                            setIsQuestionsDialogOpen(false)
                        }}
                    />

                    <DeleteEntityDialog
                        open={questionToDelete !== null}
                        kind="question"
                        title={questionToDelete?.prompt ?? ""}
                        isBusy={isDeletingQuestion}
                        error={deleteQuestionError}
                        onClose={() => {
                            setQuestionToDelete(null)
                            setDeleteQuestionError(null)
                            setIsQuestionsDialogOpen(true)
                        }}
                        onConfirm={() => void handleDeleteQuestion()}
                    />

                    <QuestionFormDialog
                        bank={selectedBank}
                        question={editingQuestion}
                        open={isQuestionFormOpen}
                        onClose={() => {
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
                                                      bank.question_count + 1,
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
                </>
            )}
        </div>
    )
}
