import { getStudentQuizImage } from "@/api/quizzes"
import { useObjectUrl } from "@/hooks/use-object-url"
import { useCallback } from "react"

type ProtectedQuizImageProps = {
    path: "questions" | "choices"
    id: number
    joinCode: string
    token: string
    alt: string
}

export function ProtectedQuizImage({
    path,
    id,
    joinCode,
    token,
    alt,
}: ProtectedQuizImageProps) {
    const loadImage = useCallback(
        () => getStudentQuizImage(path, id, joinCode, token),
        [id, joinCode, path, token]
    )
    const source = useObjectUrl(loadImage)

    return source ? (
        <img
            className="max-h-80 rounded-lg object-contain"
            src={source}
            alt={alt}
        />
    ) : null
}
