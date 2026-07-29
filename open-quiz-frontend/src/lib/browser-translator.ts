type TranslationAvailability =
    "unavailable" | "downloadable" | "downloading" | "available"

type TranslationOptions = {
    sourceLanguage: string
    targetLanguage: string
}

type TranslationMonitor = {
    addEventListener(
        type: "downloadprogress",
        listener: (event: { loaded: number }) => void
    ): void
}

export type BrowserTranslator = {
    translate(text: string): Promise<string>
    destroy(): void
}

type TranslatorApi = {
    availability(options: TranslationOptions): Promise<TranslationAvailability>
    create(
        options: TranslationOptions & {
            monitor?: (monitor: TranslationMonitor) => void
        }
    ): Promise<BrowserTranslator>
}

function translatorApi(): TranslatorApi | undefined {
    return (
        globalThis as typeof globalThis & {
            Translator?: TranslatorApi
        }
    ).Translator
}

export function translationLanguage(language: string | undefined): string {
    const normalized = (language ?? "fr").replace("_", "-").toLowerCase()
    const base = normalized.split("-")[0]
    return base === "zh" ? "zh" : base
}

export async function createBrowserTranslator(
    sourceLanguage: string,
    targetLanguage: string,
    onDownloadProgress: (progress: number) => void
): Promise<BrowserTranslator> {
    const api = translatorApi()
    if (!api) throw new Error("translator_unavailable")

    const options = { sourceLanguage, targetLanguage }
    const availability = await api.availability(options)
    if (availability === "unavailable") {
        throw new Error("translator_unavailable")
    }

    return api.create({
        ...options,
        monitor(monitor) {
            monitor.addEventListener("downloadprogress", (event) => {
                onDownloadProgress(event.loaded)
            })
        },
    })
}
