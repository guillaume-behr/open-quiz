import { useEffect, useRef } from "react"
import { useLocation, useNavigationType } from "react-router"

import { shouldMoveFocus } from "./route-focus"

export function RouteFocusManager() {
    const location = useLocation()
    const navigationType = useNavigationType()
    const previousPathname = useRef(location.pathname)

    useEffect(() => {
        const moveFocus = shouldMoveFocus(
            previousPathname.current,
            location.pathname,
            navigationType
        )
        previousPathname.current = location.pathname
        if (!moveFocus) return
        const animationFrame = window.requestAnimationFrame(() => {
            document.getElementById("contenu")?.focus()
        })
        return () => window.cancelAnimationFrame(animationFrame)
    }, [location.pathname, navigationType])

    return null
}
