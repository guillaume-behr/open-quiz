// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react"
import type { FormEvent } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/api/client"
import type { QuestionBank } from "@/api/types"

import { useBankTransfer } from "./use-bank-transfer"

const api = vi.hoisted(() => ({
    downloadQuestionBank: vi.fn(),
    downloadQuestionBatchExample: vi.fn(),
    importQuestionBatch: vi.fn(),
}))
vi.mock("@/api/question-banks", () => api)
const utils = vi.hoisted(() => ({ saveBlob: vi.fn() }))
vi.mock("@/lib/utils", async (importOriginal) => ({
    ...(await importOriginal<object>()),
    ...utils,
}))

const bank = {
    id: 4,
    grade_level: "Tle",
    chapter: "Équations & co",
} as QuestionBank
const submit = {
    preventDefault: vi.fn(),
} as unknown as FormEvent<HTMLFormElement>

function transfer() {
    const onImported = vi.fn(() => Promise.resolve())
    return { onImported, ...renderHook(() => useBankTransfer({ onImported })) }
}

describe("useBankTransfer", () => {
    beforeEach(() => {
        api.downloadQuestionBank.mockResolvedValue(new Blob(["bank"]))
        api.downloadQuestionBatchExample.mockResolvedValue(
            new Blob(["example"])
        )
        api.importQuestionBatch.mockResolvedValue({ questions: [{}, {}] })
    })

    it("exports a bank under a safe file name, or says why not", async () => {
        const { result } = transfer()
        await act(() => result.current.handleExport(bank))
        expect(utils.saveBlob).toHaveBeenCalledWith(
            expect.any(Blob),
            'question-bank-export-filename {"name":"tle-equations-co"}.json'
        )
        await act(() =>
            result.current.handleExport({
                ...bank,
                grade_level: "",
                chapter: "!!",
            })
        )
        expect(utils.saveBlob).toHaveBeenLastCalledWith(
            expect.any(Blob),
            'question-bank-export-filename {"name":4}.json'
        )
        api.downloadQuestionBank.mockRejectedValue(new Error("down"))
        await act(() => result.current.handleExport(bank))
        expect(result.current.batchError).toBe("json-export-error")
        expect(result.current.isBusy).toBe(false)
    })

    it("downloads the example, or says why not", async () => {
        const { result } = transfer()
        await act(() => result.current.handleDownloadExample())
        expect(utils.saveBlob).toHaveBeenCalledWith(
            expect.any(Blob),
            "open-quiz-questions-example.json"
        )
        api.downloadQuestionBatchExample.mockRejectedValue(new Error("down"))
        await act(() => result.current.handleDownloadExample())
        expect(result.current.batchError).toBe("json-download-error")
    })

    it("imports the chosen file and reports a duplicate", async () => {
        const { result, onImported } = transfer()
        act(() => result.current.openImportDialog())
        expect(result.current.isImportDialogOpen).toBe(true)
        act(() => result.current.handleImportSubmit(submit))
        expect(api.importQuestionBatch).not.toHaveBeenCalled()

        const file = new File(["{}"], "bank.json")
        act(() => result.current.setImportFile(file))
        // The handler starts the import without awaiting it; the async act
        // flushes the promise it leaves running.
        await act(async () => {
            result.current.handleImportSubmit(submit)
            await Promise.resolve()
        })
        expect(onImported).toHaveBeenCalled()
        expect(result.current.batchMessage).toBe(
            'questions-imported {"count":2}'
        )
        expect(result.current.isImportDialogOpen).toBe(false)

        act(() => result.current.openImportDialog())
        act(() => result.current.setImportFile(file))
        api.importQuestionBatch.mockRejectedValue(
            new ApiError("taken", 409, { code: "QUESTION_BANK_NAME_TAKEN" })
        )
        // The handler starts the import without awaiting it; the async act
        // flushes the promise it leaves running.
        await act(async () => {
            result.current.handleImportSubmit(submit)
            await Promise.resolve()
        })
        expect(result.current.importError).toBeTruthy()
        expect(result.current.isImportDialogOpen).toBe(true)

        api.importQuestionBatch.mockRejectedValue(new SyntaxError("bad json"))
        // The handler starts the import without awaiting it; the async act
        // flushes the promise it leaves running.
        await act(async () => {
            result.current.handleImportSubmit(submit)
            await Promise.resolve()
        })
        expect(result.current.importError).toBeTruthy()
        act(() => result.current.closeImportDialog())
        expect(result.current.importError).toBeNull()
        expect(result.current.importFile).toBeNull()
    })
})
