import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"
import {
    createBrowserTranslator,
    translationLanguage,
    type BrowserTranslator,
} from "@/lib/browser-translator"
import { useCallback, useEffect, useRef, useState } from "react"
import type { i18n } from "i18next"
import { translateQuestion } from "./student-quiz-translation"

export function useQuizTranslation(
    session: StudentQuizSession | null,
    i18nInstance: i18n
) {
    const [enabled, setEnabled] = useState(false)
    const [translatedPair, setTranslatedPair] = useState<string | null>(null)
    const [translatedTitle, setTranslatedTitle] = useState<string | null>(null)
    const [translatedQuestion, setTranslatedQuestion] =
        useState<StudentQuizQuestion | null>(null)
    const [isTranslating, setIsTranslating] = useState(false)
    const [isDownloading, setIsDownloading] = useState(false)
    const [errorPair, setErrorPair] = useState<string | null>(null)
    const translatorRef = useRef<BrowserTranslator | null>(null)
    const translatorPairRef = useRef<string | null>(null)
    const operationVersionRef = useRef(0)

    const sourceLanguage = translationLanguage(session?.source_language)
    const targetLanguage = translationLanguage(i18nInstance.resolvedLanguage)
    const pair = `${sourceLanguage}:${targetLanguage}`
    const offered = session !== null && sourceLanguage !== targetLanguage
    const active = enabled && translatedPair === pair

    useEffect(
        () => () => {
            translatorRef.current?.destroy()
        },
        []
    )

    useEffect(() => {
        operationVersionRef.current += 1
        translatorRef.current?.destroy()
        translatorRef.current = null
        translatorPairRef.current = null
        const timeout = window.setTimeout(() => {
            setEnabled(false)
            setTranslatedPair(null)
            setTranslatedTitle(null)
            setTranslatedQuestion(null)
            setErrorPair(null)
            setIsTranslating(false)
            setIsDownloading(false)
        }, 0)
        return () => window.clearTimeout(timeout)
    }, [pair])

    useEffect(() => {
        const question = session?.question
        const translator = translatorRef.current
        if (!active || !translator || !question) return
        if (translatedQuestion?.id === question.id) return

        let current = true
        void translateQuestion(translator, question)
            .then((translated) => {
                if (current) setTranslatedQuestion(translated)
            })
            .catch(() => {
                if (current) setErrorPair(pair)
            })
        return () => {
            current = false
        }
    }, [active, pair, session?.question, translatedQuestion?.id])

    const toggle = useCallback(async () => {
        if (active) {
            operationVersionRef.current += 1
            setEnabled(false)
            setErrorPair(null)
            setIsTranslating(false)
            setIsDownloading(false)
            return
        }
        if (!session || !offered) return

        const operationVersion = ++operationVersionRef.current
        setErrorPair(null)
        setIsTranslating(true)
        try {
            let translator = translatorRef.current
            if (translator && translatorPairRef.current !== pair) {
                translator.destroy()
                translator = null
                translatorRef.current = null
                translatorPairRef.current = null
            }
            if (!translator) {
                translator = await createBrowserTranslator(
                    sourceLanguage,
                    targetLanguage,
                    () => {
                        if (operationVersion === operationVersionRef.current)
                            setIsDownloading(true)
                    }
                )
                if (operationVersion !== operationVersionRef.current) {
                    translator.destroy()
                    return
                }
                translatorRef.current = translator
                translatorPairRef.current = pair
            }

            const [title, question] = await Promise.all([
                translator.translate(session.quiz_title),
                session.question
                    ? translateQuestion(translator, session.question)
                    : Promise.resolve(null),
            ])
            if (operationVersion !== operationVersionRef.current) return
            setTranslatedTitle(title)
            setTranslatedQuestion(question)
            setTranslatedPair(pair)
            setEnabled(true)
        } catch {
            if (operationVersion === operationVersionRef.current)
                setErrorPair(pair)
        } finally {
            if (operationVersion === operationVersionRef.current) {
                setIsTranslating(false)
                setIsDownloading(false)
            }
        }
    }, [active, offered, pair, session, sourceLanguage, targetLanguage])

    const reset = useCallback(() => {
        operationVersionRef.current += 1
        translatorRef.current?.destroy()
        translatorRef.current = null
        translatorPairRef.current = null
        setEnabled(false)
        setTranslatedPair(null)
        setTranslatedTitle(null)
        setTranslatedQuestion(null)
        setErrorPair(null)
        setIsTranslating(false)
        setIsDownloading(false)
    }, [])

    const originalQuestion = session?.question ?? null
    const question =
        active && translatedQuestion?.id === originalQuestion?.id
            ? translatedQuestion
            : originalQuestion

    return {
        question,
        title:
            active && translatedTitle
                ? translatedTitle
                : (session?.quiz_title ?? ""),
        viewState: {
            offered,
            active,
            hasError: errorPair === pair,
            isTranslating,
            isDownloading,
        },
        toggle,
        reset,
    }
}
