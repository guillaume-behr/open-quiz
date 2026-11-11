import type { InitOptions } from "i18next"

export const availableLanguages = [
    { code: "fr", label: "Français" },
    { code: "en", label: "English" },
    { code: "de", label: "Deutsch" },
    { code: "es", label: "Español" },
    { code: "pt", label: "Português" },
    { code: "uk", label: "Українська" },
    { code: "ar", label: "العربية" },
    { code: "zh-CN", label: "简体中文" },
] as const

export const i18nOptions: InitOptions = {
    fallbackLng: "fr",
    supportedLngs: availableLanguages.map(({ code }) => code),
    debug: false,
    // React escapes every rendered string, and no translation is rendered as
    // HTML: escaping here too would show "L'eau" as "L&#39;eau".
    interpolation: { escapeValue: false },
    detection: {
        order: ["localStorage", "navigator", "htmlTag"],
        caches: ["localStorage"],
        lookupLocalStorage: "i18nextLng",
    },
}
