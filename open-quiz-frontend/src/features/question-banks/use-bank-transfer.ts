import type { TFunction } from "i18next"
import {
    downloadQuestionBank,
    downloadQuestionBatchExample,
    importQuestionBatch,
} from "@/api/question-banks"
import { ApiError } from "@/api/client"
import type { QuestionBank } from "@/api/types"
import { useAsyncAction } from "@/hooks/use-async-action"
import { apiErrorMessage } from "@/lib/errors"
import { describeJsonImportFailure } from "@/lib/json-import"
import { saveBlob } from "@/lib/utils"
import { type FormEvent, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

type ImportedBank = Awaited<ReturnType<typeof importQuestionBatch>>

function exportFilename(bank: QuestionBank, t: TFunction): string {
    const safeName = `${bank.grade_level}-${bank.chapter}`
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase()
    return `${t("question-bank-export-filename", { name: safeName || bank.id })}.json`
}

/**
 * Moving question banks in and out as JSON files: the import dialog, the
 * export of one bank and the downloadable example, with their messages.
 */
export function useBankTransfer({
    onImported,
}: {
    /** A bank was created from a file: show it. */
    onImported: (imported: ImportedBank) => Promise<void>
}) {
    const { t } = useTranslation()
    const [isBatchBusy, setIsBatchBusy] = useState(false)
    const [batchMessage, setBatchMessage] = useState<string | null>(null)
    const [batchError, setBatchError] = useState<string | null>(null)
    const [isImportDialogOpen, setIsImportDialogOpen] = useState(false)
    const [importFile, setImportFile] = useState<File | null>(null)
    const importInputRef = useRef<HTMLInputElement>(null)
    const importing = useAsyncAction(importBank, (caughtError) =>
        apiErrorMessage(
            caughtError,
            t,
            caughtError instanceof ApiError && caughtError.status === 409
                ? t("json-import-duplicate-error")
                : describeJsonImportFailure(
                      caughtError,
                      t as unknown as (
                          key: string,
                          values?: Record<string, unknown>
                      ) => string,
                      t("json-import-error")
                  )
        )
    )

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
            saveBlob(
                await downloadQuestionBank(bank.id),
                exportFilename(bank, t)
            )
        } catch (caughtError) {
            setBatchError(
                apiErrorMessage(caughtError, t, t("json-export-error"))
            )
        } finally {
            setIsBatchBusy(false)
        }
    }

    async function importBank(file: File): Promise<void> {
        setBatchMessage(null)
        try {
            const imported = await importQuestionBatch(file)
            await onImported(imported)
            setBatchMessage(
                t("questions-imported", {
                    count: imported.questions.length,
                })
            )
            setIsImportDialogOpen(false)
            setImportFile(null)
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

    function closeImportDialog(): void {
        setIsImportDialogOpen(false)
        importing.setError(null)
        setImportFile(null)
    }

    return {
        isBusy: isBatchBusy || importing.isPending,
        batchError,
        batchMessage,
        isImportDialogOpen,
        importFile,
        setImportFile,
        importInputRef,
        importError: importing.error,
        handleDownloadExample,
        handleExport,
        openImportDialog,
        closeImportDialog,
        handleImportSubmit,
    }
}
