import { useCallback, useEffect, useMemo, useRef } from "react"

import {
    type AnswerDraft,
    readDrafts,
    removeDraft,
    removeDrafts,
    writeDraft,
} from "./answer-drafts"

export const DRAFT_SAVE_DELAY_MS = 500

export type AnswerDrafts = {
    getDraft: (questionId: number) => AnswerDraft | undefined
    setDraft: (questionId: number, draft: AnswerDraft) => void
    clearDraft: (questionId: number) => void
    clearAll: () => void
}

/**
 * Unsubmitted answers of an exam, kept across a reload of the tab.
 *
 * Drafts are held in memory and copied to sessionStorage (never
 * localStorage: they must not outlive the browser session on a shared
 * computer) at most every 500 ms, and at once when the page is hidden or
 * left. Logging out or clearing the device's data removes them.
 */
export function useAnswerDrafts(joinCode: string | null): AnswerDrafts {
    const draftsRef = useRef(new Map<number, AnswerDraft>())
    const pendingRef = useRef(new Set<number>())
    const timerRef = useRef<number | null>(null)
    const loadedCodeRef = useRef<string | null>(null)

    const flush = useCallback(() => {
        if (timerRef.current !== null) {
            window.clearTimeout(timerRef.current)
            timerRef.current = null
        }
        const code = loadedCodeRef.current
        if (!code) return
        for (const questionId of pendingRef.current) {
            const draft = draftsRef.current.get(questionId)
            if (draft) writeDraft(code, questionId, draft)
        }
        pendingRef.current.clear()
    }, [])

    useEffect(() => {
        const flushWhenHidden = () => {
            if (document.visibilityState === "hidden") flush()
        }
        window.addEventListener("pagehide", flush)
        document.addEventListener("visibilitychange", flushWhenHidden)
        return () => {
            flush()
            window.removeEventListener("pagehide", flush)
            document.removeEventListener("visibilitychange", flushWhenHidden)
        }
    }, [flush])

    return useMemo(() => {
        // Drafts are read from storage the first time this exam needs them.
        const drafts = () => {
            if (joinCode !== loadedCodeRef.current) {
                flush()
                loadedCodeRef.current = joinCode
                draftsRef.current = joinCode
                    ? readDrafts(joinCode)
                    : new Map<number, AnswerDraft>()
            }
            return draftsRef.current
        }
        return {
            getDraft: (questionId) => drafts().get(questionId),
            setDraft: (questionId, draft) => {
                drafts().set(questionId, draft)
                pendingRef.current.add(questionId)
                if (timerRef.current === null)
                    timerRef.current = window.setTimeout(
                        flush,
                        DRAFT_SAVE_DELAY_MS
                    )
            },
            clearDraft: (questionId) => {
                drafts().delete(questionId)
                pendingRef.current.delete(questionId)
                const code = loadedCodeRef.current
                if (code) removeDraft(code, questionId)
            },
            clearAll: () => {
                drafts().clear()
                pendingRef.current.clear()
                const code = loadedCodeRef.current
                if (code) removeDrafts(code)
            },
        } satisfies AnswerDrafts
    }, [flush, joinCode])
}
