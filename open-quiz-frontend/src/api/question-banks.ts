import { request, requestBlob, requestPage } from "./client"
import type {
    NewQuestion,
    NewQuestionBank,
    Question,
    QuestionBank,
    QuestionBankImportResult,
    QuestionUpdate,
    Page,
} from "./types"
import { readJsonImportFile } from "@/lib/json-import"

export function getQuestionBanks(
    page = 1,
    search = "",
    gradeLevel = "",
    pageSize = 8
): Promise<Page<QuestionBank>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    return requestPage<QuestionBank>(`/api/question-banks?${params}`)
}

export async function getAllQuestionBanks(): Promise<QuestionBank[]> {
    const first = await getQuestionBanks(1, "", "", 100)
    const remaining = await Promise.all(
        Array.from({ length: first.totalPages - 1 }, (_, index) =>
            getQuestionBanks(index + 2, "", "", 100)
        )
    )
    return [first, ...remaining].flatMap((result) => result.items)
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

export function createQuestion(
    questionBankId: number,
    question: NewQuestion,
    image?: File
): Promise<Question> {
    const formData = new FormData()
    formData.set("payload", JSON.stringify(question))
    if (image) formData.set("image", image)
    return request<Question>(
        `/api/question-banks/${questionBankId}/questions`,
        {
            method: "POST",
            body: formData,
        }
    )
}

export function updateQuestion(
    questionId: number,
    question: QuestionUpdate,
    image?: File
): Promise<Question> {
    const formData = new FormData()
    formData.set("payload", JSON.stringify(question))
    if (image) formData.set("image", image)
    return request<Question>(
        `/api/question-banks/questions/${questionId}/update`,
        {
            method: "POST",
            body: formData,
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
    })
}
