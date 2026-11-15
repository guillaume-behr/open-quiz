import {
    EXAM_DRAFT_KEY_PREFIX,
    readStudentItem,
    removeStudentItem,
    removeStudentItems,
    studentItemKeys,
    writeStudentItem,
} from "@/lib/student-session-storage"

/** What a student entered on a question and has not submitted yet. */
export type AnswerDraft = {
    selectedChoiceIds: string[]
    writtenAnswer: string
}

function scopePrefix(joinCode: string): string {
    return `${EXAM_DRAFT_KEY_PREFIX}${joinCode}:`
}

export function draftKey(joinCode: string, questionId: number): string {
    return `${scopePrefix(joinCode)}${questionId}`
}

function parseDraft(value: string | null): AnswerDraft | undefined {
    if (value === null) return undefined
    try {
        const draft = JSON.parse(value) as Partial<AnswerDraft> | null
        return draft &&
            Array.isArray(draft.selectedChoiceIds) &&
            draft.selectedChoiceIds.every((id) => typeof id === "string") &&
            typeof draft.writtenAnswer === "string"
            ? {
                  selectedChoiceIds: draft.selectedChoiceIds,
                  writtenAnswer: draft.writtenAnswer,
              }
            : undefined
    } catch {
        return undefined
    }
}

/** Every draft stored for an exam, by question id. */
export function readDrafts(joinCode: string): Map<number, AnswerDraft> {
    const drafts = new Map<number, AnswerDraft>()
    const prefix = scopePrefix(joinCode)
    for (const key of studentItemKeys(prefix)) {
        const questionId = Number(key.slice(prefix.length))
        const draft = parseDraft(readStudentItem(key))
        if (Number.isInteger(questionId) && draft) drafts.set(questionId, draft)
    }
    return drafts
}

export function writeDraft(
    joinCode: string,
    questionId: number,
    draft: AnswerDraft
): void {
    writeStudentItem(draftKey(joinCode, questionId), JSON.stringify(draft))
}

export function removeDraft(joinCode: string, questionId: number): void {
    removeStudentItem(draftKey(joinCode, questionId))
}

export function removeDrafts(joinCode: string): void {
    removeStudentItems(studentItemKeys(scopePrefix(joinCode)))
}
