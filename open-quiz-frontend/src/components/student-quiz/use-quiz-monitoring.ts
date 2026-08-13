import { reportStudentQuizViolation } from "@/api/quizzes"
import type { StudentQuizSession } from "@/api/types"
import { useCallback, useEffect, useRef, useState, type RefObject } from "react"

const MONITORING_GRACE_PERIOD_MS = 1500

type ViolationType =
    | "fullscreen_exit"
    | "pointer_exit"
    | "window_blur"
    | "page_hidden"
    | "copy_attempt"
    | "paste_attempt"
    | "context_menu"
    | "print_attempt"

export function useQuizMonitoring(
    session: StudentQuizSession | null,
    participantToken: string | null,
    isLeavingQuiz: RefObject<boolean>
) {
    const [isFullscreen, setIsFullscreen] = useState(
        Boolean(document.fullscreenElement)
    )
    const monitoringArmedAt = useRef<number | null>(null)
    const wasMonitoredFullscreen = useRef(false)
    const lastViolationAt = useRef<Partial<Record<ViolationType, number>>>({})
    const monitoredJoinCode =
        session?.status === "in_progress" && session.question
            ? session.join_code
            : undefined

    useEffect(() => {
        const fullscreenChanged = () => {
            setIsFullscreen(Boolean(document.fullscreenElement))
        }
        document.addEventListener("fullscreenchange", fullscreenChanged)
        return () => {
            document.removeEventListener("fullscreenchange", fullscreenChanged)
        }
    }, [])

    useEffect(() => {
        if (!monitoredJoinCode || !participantToken) {
            monitoringArmedAt.current = null
            wasMonitoredFullscreen.current = false
            return
        }

        const report = (eventType: ViolationType) => {
            if (isLeavingQuiz.current) return
            if (eventType !== "fullscreen_exit" && !document.fullscreenElement)
                return

            const now = Date.now()
            const armedAt = monitoringArmedAt.current
            if (
                armedAt === null ||
                now - armedAt < MONITORING_GRACE_PERIOD_MS ||
                now - (lastViolationAt.current[eventType] ?? 0) <
                    MONITORING_GRACE_PERIOD_MS
            )
                return

            lastViolationAt.current[eventType] = now
            void reportStudentQuizViolation(
                monitoredJoinCode,
                participantToken,
                eventType
            ).catch(() => {
                // Monitoring is best effort and must not interrupt the quiz.
            })
        }

        if (isFullscreen && !wasMonitoredFullscreen.current) {
            monitoringArmedAt.current = Date.now()
        } else if (!isFullscreen && wasMonitoredFullscreen.current) {
            report("fullscreen_exit")
        }
        wasMonitoredFullscreen.current = isFullscreen

        const pointerLeft = () => report("pointer_exit")
        const blurred = () => report("window_blur")
        const visibilityChanged = () => {
            if (document.hidden) report("page_hidden")
        }
        const copied = () => report("copy_attempt")
        const pasted = () => report("paste_attempt")
        const contextMenuOpened = () => report("context_menu")
        const printing = () => report("print_attempt")
        document.documentElement.addEventListener("mouseleave", pointerLeft)
        window.addEventListener("blur", blurred)
        document.addEventListener("visibilitychange", visibilityChanged)
        document.addEventListener("copy", copied)
        document.addEventListener("paste", pasted)
        document.addEventListener("contextmenu", contextMenuOpened)
        window.addEventListener("beforeprint", printing)
        return () => {
            document.documentElement.removeEventListener(
                "mouseleave",
                pointerLeft
            )
            window.removeEventListener("blur", blurred)
            document.removeEventListener("visibilitychange", visibilityChanged)
            document.removeEventListener("copy", copied)
            document.removeEventListener("paste", pasted)
            document.removeEventListener("contextmenu", contextMenuOpened)
            window.removeEventListener("beforeprint", printing)
        }
    }, [isFullscreen, isLeavingQuiz, monitoredJoinCode, participantToken])

    const enterFullscreen = useCallback(async () => {
        await document.documentElement.requestFullscreen()
        setIsFullscreen(true)
    }, [])

    return { isFullscreen, enterFullscreen }
}
