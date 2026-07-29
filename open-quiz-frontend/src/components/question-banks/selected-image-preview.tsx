import { useEffect, useRef } from "react"

export function SelectedImagePreview({
    image,
    alt,
    className,
}: {
    image: File
    alt: string
    className: string
}) {
    const imageElement = useRef<HTMLImageElement>(null)

    useEffect(() => {
        const nextImageUrl = URL.createObjectURL(image)
        const preview = imageElement.current
        if (preview) preview.src = nextImageUrl
        return () => {
            if (preview) preview.removeAttribute("src")
            URL.revokeObjectURL(nextImageUrl)
        }
    }, [image])

    return <img ref={imageElement} alt={alt} className={className} />
}
