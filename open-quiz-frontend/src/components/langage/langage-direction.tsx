import { useEffect } from "react"
import { useTranslation } from "react-i18next"

export function LanguageDirection() {
    const { i18n } = useTranslation()

    const language = i18n.resolvedLanguage ?? i18n.language

    useEffect(() => {
        document.documentElement.lang = language
        document.documentElement.dir = i18n.dir(language)
    }, [language, i18n])

    return null
}
