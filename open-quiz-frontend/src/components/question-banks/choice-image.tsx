import { getChoiceImage } from "@/api/question-banks"
import { useObjectUrl } from "@/hooks/use-object-url"
import { useCallback } from "react"

type ChoiceImageProps = {
    choiceId: number
    alt: string
}

export function ChoiceImage({ choiceId, alt }: ChoiceImageProps) {
    const loadImage = useCallback(() => getChoiceImage(choiceId), [choiceId])
    const imageUrl = useObjectUrl(loadImage)

    if (!imageUrl) return null

    return (
        <img
            src={imageUrl}
            alt={alt}
            className="mt-2 max-h-48 w-full rounded-md border bg-background object-contain"
        />
    )
}
