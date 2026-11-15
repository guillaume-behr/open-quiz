import { getQuestionImage } from "@/api/question-banks"
import { useObjectUrl } from "@/hooks/use-object-url"
import { useCallback } from "react"

type QuestionImageProps = {
    questionId: number
    alt: string
}

export function QuestionImage({ questionId, alt }: QuestionImageProps) {
    const loadImage = useCallback(
        () => getQuestionImage(questionId),
        [questionId]
    )
    const imageUrl = useObjectUrl(loadImage)

    if (!imageUrl) return null

    return (
        <img
            src={imageUrl}
            alt={alt}
            className="mt-3 max-h-64 w-full rounded-lg border object-contain"
        />
    )
}
