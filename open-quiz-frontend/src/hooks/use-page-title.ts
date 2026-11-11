import { useEffect } from "react"
import { useTranslation } from "react-i18next"

/**
 * Names the browser tab after the page ("Open Quiz | <title>", worded per
 * language) while it is shown, and restores the previous title after.
 */
export function usePageTitle(title: string): void {
    const { t } = useTranslation()
    useEffect(() => {
        const previousTitle = document.title
        document.title = t("legal-page-browser-title", { title })
        return () => {
            document.title = previousTitle
        }
    }, [t, title])
}
