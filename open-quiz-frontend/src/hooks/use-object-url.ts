import { useEffect, useState } from "react"

export function useObjectUrl(loadBlob: () => Promise<Blob>): string | null {
    const [objectUrl, setObjectUrl] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        let currentUrl: string | null = null

        void loadBlob()
            .then((blob) => {
                currentUrl = URL.createObjectURL(blob)
                if (active) {
                    setObjectUrl(currentUrl)
                } else {
                    URL.revokeObjectURL(currentUrl)
                }
            })
            .catch(() => {
                if (active) setObjectUrl(null)
            })

        return () => {
            active = false
            if (currentUrl) URL.revokeObjectURL(currentUrl)
        }
    }, [loadBlob])

    return objectUrl
}
