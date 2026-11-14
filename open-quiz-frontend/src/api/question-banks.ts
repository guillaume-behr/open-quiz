import { PAGE_SIZE } from "@/lib/utils"

import {
    LARGE_REQUEST_TIMEOUT_MS,
    request,
    requestBlob,
    requestPage,
} from "./client"
import { ALL_PAGES_SIZE, fetchAllPages } from "./pagination"
import type {
    NewQuestion,
    NewQuestionBank,
    Question,
    QuestionBank,
    QuestionBankImportResult,
    QuestionUpdate,
    Page,
    UpdatedQuestion,
} from "./types"
import { readJsonImportFile } from "@/lib/json-import"

/** With `focus`, the page returned is the one holding that bank. */
export function getQuestionBanks(
    page = 1,
    search = "",
    gradeLevel = "",
    pageSize = PAGE_SIZE,
    focus: number | null = null,
    signal?: AbortSignal
): Promise<Page<QuestionBank>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    if (focus !== null) params.set("focus", String(focus))
    return requestPage<QuestionBank>(`/api/question-banks?${params}`, {
        signal,
    })
}

export function getAllQuestionBanks(): Promise<QuestionBank[]> {
    return fetchAllPages((page) =>
        getQuestionBanks(page, "", "", ALL_PAGES_SIZE)
    )
}

export function createQuestionBank(
    questionBank: NewQuestionBank
): Promise<QuestionBank> {
    return request<QuestionBank>("/api/question-banks", {
        method: "POST",
        body: JSON.stringify(questionBank),
    })
}

export function updateQuestionBank(
    questionBankId: number,
    questionBank: NewQuestionBank
): Promise<QuestionBank> {
    return request<QuestionBank>(
        `/api/question-banks/${questionBankId}/update`,
        {
            method: "POST",
            body: JSON.stringify(questionBank),
        }
    )
}

export function deleteQuestionBank(questionBankId: number): Promise<void> {
    return request<void>(`/api/question-banks/${questionBankId}`, {
        method: "DELETE",
    })
}

export function getQuestions(questionBankId: number): Promise<Question[]> {
    return request<Question[]>(
        `/api/question-banks/${questionBankId}/questions`
    )
}

export function deleteQuestion(questionId: number): Promise<void> {
    return request<void>(`/api/question-banks/questions/${questionId}`, {
        method: "DELETE",
    })
}

/**
 * The question as a multipart form. Images travel as file parts: a form
 * field is capped at 1 MiB, which a choice image in base64 would exceed.
 * A choice names its new image by position in `choiceImages`.
 */
function questionForm(
    question: NewQuestion | QuestionUpdate,
    image: File | undefined,
    choiceImages: File[]
): FormData {
    const formData = new FormData()
    formData.set("payload", JSON.stringify(question))
    if (image) formData.set("image", image)
    for (const choiceImage of choiceImages)
        formData.append("choice_images", choiceImage)
    return formData
}

export function createQuestion(
    questionBankId: number,
    question: NewQuestion,
    image?: File,
    choiceImages: File[] = []
): Promise<Question> {
    const formData = questionForm(question, image, choiceImages)
    return request<Question>(
        `/api/question-banks/${questionBankId}/questions`,
        {
            method: "POST",
            body: formData,
            timeoutMs: LARGE_REQUEST_TIMEOUT_MS,
        }
    )
}

export function updateQuestion(
    questionId: number,
    question: QuestionUpdate,
    image?: File,
    choiceImages: File[] = []
): Promise<UpdatedQuestion> {
    const formData = questionForm(question, image, choiceImages)
    return request<UpdatedQuestion>(
        `/api/question-banks/questions/${questionId}/update`,
        {
            method: "POST",
            body: formData,
            timeoutMs: LARGE_REQUEST_TIMEOUT_MS,
        }
    )
}

export function getQuestionImage(questionId: number): Promise<Blob> {
    return requestBlob(`/api/question-banks/questions/${questionId}/image`)
}

export function getChoiceImage(choiceId: number): Promise<Blob> {
    return requestBlob(`/api/question-banks/choices/${choiceId}/image`)
}

export function downloadQuestionBank(questionBankId: number): Promise<Blob> {
    return requestBlob(`/api/question-banks/${questionBankId}/export`)
}

export function downloadQuestionBatchExample(): Promise<Blob> {
    return requestBlob("/api/question-banks/example")
}

export async function importQuestionBatch(
    file: File
): Promise<QuestionBankImportResult> {
    return request<QuestionBankImportResult>("/api/question-banks/import", {
        method: "POST",
        body: await readJsonImportFile(file),
        timeoutMs: LARGE_REQUEST_TIMEOUT_MS,
    })
}
