import { reportStudentQuizViolation } from "@/api/quizzes"
import type { StudentQuizSession } from "@/api/types"
import { useCallback, useEffect, useRef, useState, type RefObject } from "react"

const MONITORING_GRACE_PERIOD_MS = 1500

type ViolationType =
    "fullscreen_exit" | "pointer_exit" | "window_blur" | "page_hidden"

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
    const lastViolationAt = useRef(0)
    const monitoredJoinCode =
        session?.status === "in_progress" ? session.join_code : undefined

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
                now - lastViolationAt.current < MONITORING_GRACE_PERIOD_MS
            )
                return

            lastViolationAt.current = now
            void reportStudentQuizViolation(
                monitoredJoinCode,
                participantToken,
                eventType
            )
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
        document.documentElement.addEventListener("mouseleave", pointerLeft)
        window.addEventListener("blur", blurred)
        document.addEventListener("visibilitychange", visibilityChanged)
        return () => {
            document.documentElement.removeEventListener(
                "mouseleave",
                pointerLeft
            )
            window.removeEventListener("blur", blurred)
            document.removeEventListener("visibilitychange", visibilityChanged)
        }
    }, [isFullscreen, isLeavingQuiz, monitoredJoinCode, participantToken])

    const enterFullscreen = useCallback(async () => {
        await document.documentElement.requestFullscreen()
        setIsFullscreen(true)
    }, [])

    return { isFullscreen, enterFullscreen }
}
