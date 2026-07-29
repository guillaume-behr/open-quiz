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
            setEnabled(false)
            setErrorPair(null)
            return
        }
        if (!session || !offered) return

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
                    () => setIsDownloading(true)
                )
                translatorRef.current = translator
                translatorPairRef.current = pair
            }

            const [title, question] = await Promise.all([
                translator.translate(session.quiz_title),
                session.question
                    ? translateQuestion(translator, session.question)
                    : Promise.resolve(null),
            ])
            setTranslatedTitle(title)
            setTranslatedQuestion(question)
            setTranslatedPair(pair)
            setEnabled(true)
        } catch {
            setErrorPair(pair)
        } finally {
            setIsTranslating(false)
            setIsDownloading(false)
        }
    }, [active, offered, pair, session, sourceLanguage, targetLanguage])

    const reset = useCallback(() => {
        translatorRef.current?.destroy()
        translatorRef.current = null
        translatorPairRef.current = null
        setEnabled(false)
        setTranslatedPair(null)
        setTranslatedTitle(null)
        setTranslatedQuestion(null)
        setErrorPair(null)
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
