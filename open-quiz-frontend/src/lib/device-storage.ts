// Keys this application writes in browser storage: every one it owns starts
// with this prefix, besides the language and theme preferences below.
export const STORAGE_KEY_PREFIX = "open-quiz-"
const PREFERENCE_KEYS = ["i18nextLng", "vite-ui-theme"]

function clearStorage(storage: Storage): void {
    const keys: string[] = []
    for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index)
        if (
            key !== null &&
            (key.startsWith(STORAGE_KEY_PREFIX) ||
                PREFERENCE_KEYS.includes(key))
        )
            keys.push(key)
    }
    for (const key of keys) storage.removeItem(key)
}

/**
 * Remove everything Open Quiz keeps in this browser's storage.
 *
 * Clearing by prefix rather than from a list keeps a key added later from
 * surviving "clear this device's data". Returns false when the browser
 * refused access to its storage.
 */
export function clearOpenQuizStorage(): boolean {
    try {
        clearStorage(localStorage)
        clearStorage(sessionStorage)
        return true
    } catch {
        return false
    }
}
