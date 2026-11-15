import type { NewQuestion } from "@/api/types"

import type { EditableChoice } from "./question-form-types"

const ALLOWED_IMAGE_TYPES: ReadonlySet<string> = new Set([
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
])

/**
 * The choices as the API takes them, and their new images in the order the
 * choices name them (`image_file`).
 */
export function choicePayloads(choices: EditableChoice[]): {
    payloads: NewQuestion["choices"]
    images: File[]
} {
    const images: File[] = []
    const payloads = choices.map((choice) => {
        let imageFile: number | null = null
        if (choice.image) {
            if (!ALLOWED_IMAGE_TYPES.has(choice.image.type))
                throw new Error("Unsupported image type")
            imageFile = images.push(choice.image) - 1
        }
        return {
            id: choice.id,
            label: choice.label.trim(),
            is_correct: choice.is_correct,
            points: choice.points,
            image_file: imageFile,
            remove_image: choice.remove_image,
            code_language: choice.hasCode ? choice.codeLanguage : null,
            code_content: choice.hasCode ? choice.codeContent : null,
        }
    })
    return { payloads, images }
}
