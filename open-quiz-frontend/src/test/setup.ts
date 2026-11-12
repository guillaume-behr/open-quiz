// Testing Library's DOM matchers (toBeInTheDocument, toHaveTextContent…).
import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach, vi } from "vitest"

// Testing Library unmounts on its own only with vitest's globals enabled.
afterEach(cleanup)

// Translations echo their key, followed by their options when there are
// any: tests assert which message is shown without depending on its wording.
// A test file can still mock react-i18next itself.
export function translate(key: string, options?: object): string {
    return options && Object.keys(options).length > 0
        ? `${key} ${JSON.stringify(options)}`
        : key
}

vi.mock("react-i18next", () => ({
    useTranslation: () => ({
        t: translate,
        i18n: { language: "en", dir: () => "ltr" },
    }),
    initReactI18next: { type: "3rdParty", init: () => undefined },
}))
