import {
    createQuestionBank,
    deleteQuestionBank,
    deleteQuestion,
    downloadQuestionBank,
    downloadQuestionBatchExample,
    getAllQuestionBanks,
    getQuestionBanks,
    getQuestions,
    importQuestionBatch,
    updateQuestionBank,
} from "@/api/question-banks"
import { naturalCompare, pageContaining, saveBlob } from "@/lib/utils"
import { describeJsonImportFailure } from "@/lib/json-import"
import { ApiError } from "@/api/client"
import type { GradeLevel, Question, QuestionBank } from "@/api/types"
import { QuestionBankFormDialog } from "@/components/question-banks/question-bank-form-dialog"
import {
    DeleteEntityDialog,
    ImportQuestionBankDialog,
    QuestionFormDialog,
} from "@/components/question-banks/question-bank-secondary-dialogs"
import { QuestionBanksList } from "@/components/question-banks/question-banks-list"
import { QuestionsManager } from "@/components/question-banks/questions-dialog"
import { type FormEvent, useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"
import { useAsyncAction } from "@/hooks/use-async-action"
import { useResource } from "@/hooks/use-resource"

function compareQuestionBanks(
    first: QuestionBank,
    second: QuestionBank
): number {
    return (
        naturalCompare(first.grade_level, second.grade_level) ||
        naturalCompare(first.chapter, second.chapter)
    )
}

const PAGE_SIZE = 8

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
    const [page, setPage] = useState(1)
    const [titleFilter, setTitleFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const bankList = useResource(
        useCallback(
            () => getQuestionBanks(page, titleFilter.trim(), gradeLevelFilter),
            [gradeLevelFilter, page, titleFilter]
        )
    )
    const questionBanks = bankList.data?.items ?? []
    const totalPages = bankList.data?.totalPages ?? 1
    const lastPage = bankList.data?.totalPages
    // A deletion can leave the current page past the end of the list.
    if (lastPage !== undefined && page > lastPage) setPage(lastPage)
    const [gradeLevel, setGradeLevel] = useState("")
    const [title, setTitle] = useState("")
    const [editingBank, setEditingBank] = useState<QuestionBank | null>(null)
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [selectedBankId, setSelectedBankId] = useState<number | null>(null)
    const questionList = useResource(
        useCallback(
            () =>
                selectedBankId === null
                    ? Promise.resolve([])
                    : getQuestions(selectedBankId),
            [selectedBankId]
        )
    )
    // Which dialog of the edited bank is in front: the bank with its
    // questions, the form of one question, or the deletion of one question.
    const [bankView, setBankView] = useState<
        "questions" | "question-form" | "delete-question" | null
    >(null)
    const [editingQuestion, setEditingQuestion] = useState<Question | null>(
        null
    )
    const [questionToDelete, setQuestionToDelete] = useState<Question | null>(
        null
    )
    const [isBatchBusy, setIsBatchBusy] = useState(false)
    const [batchMessage, setBatchMessage] = useState<string | null>(null)
    const [batchError, setBatchError] = useState<string | null>(null)
    const [isImportDialogOpen, setIsImportDialogOpen] = useState(false)
    const [importFile, setImportFile] = useState<File | null>(null)
    const [bankToDelete, setBankToDelete] = useState<QuestionBank | null>(null)
    const importInputRef = useRef<HTMLInputElement>(null)

    const saving = useAsyncAction(saveBank, (caughtError) =>
        apiErrorMessage(
            caughtError,
            t,
            caughtError instanceof ApiError && caughtError.status === 409
                ? t("question-bank-duplicate-error")
                : t("question-bank-create-error")
        )
    )
    const deletingBank = useAsyncAction(deleteSelectedBank, (caughtError) =>
        apiErrorMessage(
            caughtError,
            t,
            caughtError instanceof ApiError && caughtError.status === 409
                ? t("question-bank-in-use-error")
                : t("question-bank-delete-error")
        )
    )
    const deletingQuestion = useAsyncAction(
        deleteSelectedQuestion,
        (caughtError) =>
            apiErrorMessage(
                caughtError,
                t,
                caughtError instanceof ApiError && caughtError.status === 409
                    ? t("question-in-use-error")
                    : t("question-delete-error")
            )
    )
    const importing = useAsyncAction(importBank, (caughtError) =>
        apiErrorMessage(
            caughtError,
            t,
            caughtError instanceof ApiError && caughtError.status === 409
                ? t("json-import-duplicate-error")
                : describeJsonImportFailure(caughtError, t("json-import-error"))
        )
    )

    function updateBanks(update: (banks: QuestionBank[]) => QuestionBank[]) {
        bankList.setData(
            (current) => current && { ...current, items: update(current.items) }
        )
    }

    function changeQuestionCount(bankId: number, change: number): void {
        updateBanks((banks) =>
            banks.map((bank) =>
                bank.id === bankId
                    ? {
                          ...bank,
                          question_count: Math.max(
                              0,
                              bank.question_count + change
                          ),
                      }
                    : bank
            )
        )
    }

    async function saveBank(event: FormEvent<HTMLFormElement>): Promise<void> {
        event.preventDefault()
        const values = { grade_level: gradeLevel.trim(), chapter: title.trim() }
        const saved = editingBank
            ? await updateQuestionBank(editingBank.id, values)
            : await createQuestionBank(values)
        updateBanks((banks) =>
            (editingBank
                ? banks.map((bank) => (bank.id === saved.id ? saved : bank))
                : [...banks, saved]
            ).sort(compareQuestionBanks)
        )
        setGradeLevel("")
        setTitle("")
        setEditingBank(null)
        setBankView(null)
        setSelectedBankId(null)
        setTitleFilter("")
        setGradeLevelFilter("")
        const allBanks = await getAllQuestionBanks().catch(() => [])
        setPage(pageContaining(allBanks, saved.id, PAGE_SIZE))
        bankList.reload()
        onCreateDialogOpenChange(false)
    }

    async function addGradeLevel(): Promise<void> {
        const normalizedLevel = newGradeLevel.trim()
        if (!normalizedLevel) return
        saving.setError(null)
        try {
            const created = await onCreateGradeLevel(normalizedLevel)
            setGradeLevel(created.name)
            setNewGradeLevel("")
            setIsAddingGradeLevel(false)
        } catch (caughtError) {
            saving.setError(
                apiErrorMessage(caughtError, t, t("grade-level-create-error"))
            )
        }
    }

    const selectedBank = questionBanks.find(
        (bank) => bank.id === selectedBankId
    )

    function openBankEditor(bank: QuestionBank): void {
        if (bank.id === selectedBankId) questionList.reload()
        setSelectedBankId(bank.id)
        setEditingBank(bank)
        setGradeLevel(bank.grade_level)
        setTitle(bank.chapter)
        saving.setError(null)
        setBankView("questions")
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
        } catch (caughtError) {
            setBatchError(
                apiErrorMessage(caughtError, t, t("json-export-error"))
            )
        } finally {
            setIsBatchBusy(false)
        }
    }

    async function deleteSelectedBank(): Promise<void> {
        if (!bankToDelete) return
        await deleteQuestionBank(bankToDelete.id)
        updateBanks((banks) =>
            banks.filter((bank) => bank.id !== bankToDelete.id)
        )
        if (selectedBankId === bankToDelete.id) {
            setSelectedBankId(null)
            setBankView(null)
        }
        setBankToDelete(null)
        bankList.reload()
    }

    async function deleteSelectedQuestion(): Promise<void> {
        if (!questionToDelete || !selectedBank) return
        await deleteQuestion(questionToDelete.id)
        questionList.setData((current) =>
            current?.filter((question) => question.id !== questionToDelete.id)
        )
        changeQuestionCount(selectedBank.id, -1)
        setQuestionToDelete(null)
        setBankView("questions")
    }

    async function importBank(file: File): Promise<void> {
        setBatchMessage(null)
        try {
            const imported = await importQuestionBatch(file)
            updateBanks((banks) =>
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
            setPage(1)
            bankList.reload()
        } finally {
            if (importInputRef.current) importInputRef.current.value = ""
        }
    }

    function openImportDialog(): void {
        setBatchError(null)
        importing.setError(null)
        setBatchMessage(null)
        setImportFile(null)
        if (importInputRef.current) importInputRef.current.value = ""
        setIsImportDialogOpen(true)
    }

    function handleImportSubmit(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault()
        if (!importFile) return
        void importing.run(importFile)
    }

    return (
        <div className="mt-6">
            <QuestionBanksList
                banks={questionBanks}
                gradeLevels={gradeLevels}
                titleFilter={titleFilter}
                gradeLevelFilter={gradeLevelFilter}
                isLoading={!bankList.hasSettled}
                loadError={
                    bankList.error ? t("question-banks-load-error") : null
                }
                isBatchBusy={isBatchBusy || importing.isPending}
                batchError={batchError}
                batchMessage={batchMessage}
                onTitleFilterChange={(value) => {
                    setTitleFilter(value)
                    setPage(1)
                }}
                onGradeLevelFilterChange={(value) => {
                    setGradeLevelFilter(value)
                    setPage(1)
                }}
                onDeleteGradeLevel={onDeleteGradeLevel}
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                onImport={openImportDialog}
                onDownloadExample={() => void handleDownloadExample()}
                onExport={(bank) => void handleExport(bank)}
                onDelete={(bank) => {
                    deletingBank.setError(null)
                    setBankToDelete(bank)
                }}
                onEdit={openBankEditor}
            />

            <QuestionBankFormDialog
                open={
                    isCreateDialogOpen ||
                    (editingBank !== null && bankView === "questions")
                }
                editingBank={editingBank}
                gradeLevels={gradeLevels}
                gradeLevel={gradeLevel}
                title={title}
                newGradeLevel={newGradeLevel}
                isAddingGradeLevel={isAddingGradeLevel}
                isBusy={saving.isPending}
                error={saving.error}
                onGradeLevelChange={setGradeLevel}
                onTitleChange={setTitle}
                onNewGradeLevelChange={setNewGradeLevel}
                onAddingGradeLevelChange={setIsAddingGradeLevel}
                onDeleteGradeLevel={async (level) => {
                    saving.setError(null)
                    try {
                        await onDeleteGradeLevel(level)
                    } catch (error) {
                        saving.setError(
                            apiErrorMessage(
                                error,
                                t,
                                error instanceof ApiError &&
                                    error.status === 409
                                    ? t("grade-level-in-use-error")
                                    : t("grade-level-delete-error")
                            )
                        )
                        throw error
                    }
                }}
                onAddGradeLevel={() => void addGradeLevel()}
                onClose={() => {
                    onCreateDialogOpenChange(false)
                    setEditingBank(null)
                    setBankView(null)
                    setSelectedBankId(null)
                    setGradeLevel("")
                    setTitle("")
                    saving.setError(null)
                }}
                onSubmit={(event) => void saving.run(event)}
                questionManagement={
                    editingBank && selectedBank ? (
                        <QuestionsManager
                            questions={
                                questionList.isLoading
                                    ? []
                                    : (questionList.data ?? [])
                            }
                            isLoading={questionList.isLoading}
                            error={
                                questionList.error
                                    ? t("questions-load-error")
                                    : null
                            }
                            onAdd={() => {
                                setEditingQuestion(null)
                                setBankView("question-form")
                            }}
                            onEdit={(question) => {
                                setEditingQuestion(question)
                                setBankView("question-form")
                            }}
                            onDelete={(question) => {
                                deletingQuestion.setError(null)
                                setQuestionToDelete(question)
                                setBankView("delete-question")
                            }}
                        />
                    ) : undefined
                }
            />

            <ImportQuestionBankDialog
                open={isImportDialogOpen}
                file={importFile}
                inputRef={importInputRef}
                isBusy={isBatchBusy || importing.isPending}
                error={importing.error}
                onFileChange={setImportFile}
                onClose={() => {
                    setIsImportDialogOpen(false)
                    importing.setError(null)
                    setImportFile(null)
                }}
                onSubmit={handleImportSubmit}
            />

            <DeleteEntityDialog
                open={bankToDelete !== null}
                kind="bank"
                title={bankToDelete?.chapter ?? ""}
                isBusy={deletingBank.isPending}
                error={deletingBank.error}
                onClose={() => {
                    setBankToDelete(null)
                    deletingBank.setError(null)
                }}
                onConfirm={() => void deletingBank.run()}
            />

            {selectedBank && (
                <>
                    <DeleteEntityDialog
                        open={
                            bankView === "delete-question" &&
                            questionToDelete !== null
                        }
                        kind="question"
                        title={questionToDelete?.prompt ?? ""}
                        isBusy={deletingQuestion.isPending}
                        error={deletingQuestion.error}
                        onClose={() => {
                            setQuestionToDelete(null)
                            deletingQuestion.setError(null)
                            setBankView("questions")
                        }}
                        onConfirm={() => void deletingQuestion.run()}
                    />

                    <QuestionFormDialog
                        bank={selectedBank}
                        question={editingQuestion}
                        open={bankView === "question-form"}
                        onClose={() => {
                            setEditingQuestion(null)
                            setBankView("questions")
                        }}
                        onSaved={(savedQuestion) => {
                            if (!editingQuestion)
                                changeQuestionCount(selectedBank.id, 1)
                            questionList.setData((current = []) =>
                                editingQuestion
                                    ? current.map((question) =>
                                          question.id === savedQuestion.id
                                              ? savedQuestion
                                              : question
                                      )
                                    : [savedQuestion, ...current]
                            )
                            setEditingQuestion(null)
                            setBankView("questions")
                        }}
                    />
                </>
            )}
        </div>
    )
}
