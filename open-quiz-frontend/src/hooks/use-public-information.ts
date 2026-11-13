import {
    getPublicInformation,
    type PublicInformation,
} from "@/api/public-information"
import { useEffect, useState } from "react"

/** The instance's public information, loaded once for the legal pages. */
export function usePublicInformation() {
    const [information, setInformation] = useState<PublicInformation | null>(
        null
    )
    const [loadFailed, setLoadFailed] = useState(false)

    useEffect(() => {
        let active = true
        getPublicInformation()
            .then((result) => {
                if (active) setInformation(result)
            })
            .catch(() => {
                if (active) setLoadFailed(true)
            })
        return () => {
            active = false
        }
    }, [])

    return { information, loadFailed }
}
