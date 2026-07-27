import { getQuestionImage } from "@/api/api"
import { useEffect, useState } from "react"

type QuestionImageProps = {
    questionId: number
    alt: string
}

export function QuestionImage({ questionId, alt }: QuestionImageProps) {
    const [imageUrl, setImageUrl] = useState<string | null>(null)

    useEffect(() => {
        let isActive = true
        let objectUrl: string | null = null

        getQuestionImage(questionId)
            .then((blob) => {
                if (!isActive) return
                objectUrl = URL.createObjectURL(blob)
                setImageUrl(objectUrl)
            })
            .catch(() => {
                if (isActive) setImageUrl(null)
            })

        return () => {
            isActive = false
            if (objectUrl) URL.revokeObjectURL(objectUrl)
        }
    }, [questionId])

    if (!imageUrl) return null

    return (
        <img
            src={imageUrl}
            alt={alt}
            className="mt-3 max-h-64 w-full rounded-lg border object-contain"
        />
    )
}
