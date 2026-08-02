import type { CodeLanguage } from "@/api/types"

export type EditableChoice = {
    id?: number
    label: string
    is_correct: boolean
    has_image: boolean
    image?: File
    remove_image: boolean
    hasCode: boolean
    codeLanguage: CodeLanguage
    codeContent: string
}

export const selectClassName =
    "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
