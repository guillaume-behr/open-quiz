import { useTranslation } from "react-i18next"

/**
 * The language the interface is shown in, for formatting numbers and dates:
 * the supported language i18next resolved, never a raw detected value such
 * as "en-US" or an unsupported "it".
 */
export function useLocale(): string {
    const { i18n } = useTranslation()
    return i18n.resolvedLanguage ?? "fr"
}

/** A duration in whole minutes, worded for the locale ("30 min"). */
export function formatMinutes(seconds: number, locale: string): string {
    return new Intl.NumberFormat(locale, {
        style: "unit",
        unit: "minute",
    }).format(Math.round(seconds / 60))
}

/** A percentage from 0 to 100, worded for the locale ("50 %" in French). */
export function formatPercent(value: number, locale: string): string {
    return new Intl.NumberFormat(locale, {
        style: "percent",
        maximumFractionDigits: 0,
    }).format(value / 100)
}
