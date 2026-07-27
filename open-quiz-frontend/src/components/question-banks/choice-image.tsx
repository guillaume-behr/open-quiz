import { getChoiceImage } from "@/api/api"
import { useEffect, useState } from "react"

type ChoiceImageProps = {
    choiceId: number
    alt: string
}

export function ChoiceImage({ choiceId, alt }: ChoiceImageProps) {
    const [imageUrl, setImageUrl] = useState<string | null>(null)

    useEffect(() => {
        let isActive = true
        let objectUrl: string | null = null

        getChoiceImage(choiceId)
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
    }, [choiceId])

    if (!imageUrl) return null

    return (
        <img
            src={imageUrl}
            alt={alt}
            className="mt-2 max-h-48 w-full rounded-md border bg-background object-contain"
        />
    )
}
