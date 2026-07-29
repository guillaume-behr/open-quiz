import { useEffect, useState } from "react"

export function useObjectUrl(loadBlob: () => Promise<Blob>): string | null {
    const [loaded, setLoaded] = useState<{
        loader: typeof loadBlob
        objectUrl: string
    } | null>(null)

    useEffect(() => {
        let active = true
        let currentUrl: string | null = null

        void loadBlob()
            .then((blob) => {
                currentUrl = URL.createObjectURL(blob)
                if (active) {
                    setLoaded({
                        loader: loadBlob,
                        objectUrl: currentUrl,
                    })
                } else {
                    URL.revokeObjectURL(currentUrl)
                }
            })
            .catch(() => {
                if (active) setLoaded(null)
            })

        return () => {
            active = false
            if (currentUrl) URL.revokeObjectURL(currentUrl)
        }
    }, [loadBlob])

    return loaded?.loader === loadBlob ? loaded.objectUrl : null
}
