// The Arabic and Chinese fonts declare about a hundred @font-face rules: their
// stylesheets are loaded only once one of those languages is chosen, rather
// than parsed by every visitor in the main stylesheet. The font files
// themselves still download by unicode-range, as before.
const fontLoaders: Partial<Record<string, () => Promise<unknown>>> = {
    ar: () => import("@fontsource-variable/noto-sans-arabic"),
    zh: () => import("@fontsource-variable/noto-sans-sc"),
}

const requested = new Map<string, Promise<void>>()

/** Loads the stylesheet of the font a language needs, once. */
export function loadLocaleFonts(language: string | undefined): Promise<void> {
    const script = language?.split("-")[0]?.toLowerCase()
    const load = script === undefined ? undefined : fontLoaders[script]
    if (script === undefined || load === undefined) return Promise.resolve()
    const pending = requested.get(script)
    if (pending) return pending
    const loading = load().then(
        () => undefined,
        () => {
            // A failed chunk (offline, new deployment) leaves the system
            // font in place; the next change of language tries again.
            requested.delete(script)
        }
    )
    requested.set(script, loading)
    return loading
}
