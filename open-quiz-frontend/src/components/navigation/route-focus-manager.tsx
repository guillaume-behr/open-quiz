import { useEffect, useRef } from "react"
import { useLocation } from "react-router"

export function RouteFocusManager() {
    const location = useLocation()
    const previousLocationKey = useRef(location.key)

    useEffect(() => {
        if (previousLocationKey.current === location.key) return
        previousLocationKey.current = location.key
        const animationFrame = window.requestAnimationFrame(() => {
            document.getElementById("contenu")?.focus()
        })
        return () => window.cancelAnimationFrame(animationFrame)
    }, [location.key])

    return null
}
