import type { CodeLanguage } from "@/api/types"

export type EditableChoice = {
    id?: number
    label: string
    is_correct: boolean
    points: number
    has_image: boolean
    image?: File
    remove_image: boolean
    hasCode: boolean
    codeLanguage: CodeLanguage
    codeContent: string
}
