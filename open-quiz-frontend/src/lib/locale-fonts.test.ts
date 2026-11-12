import { describe, expect, it, vi } from "vitest"

const imported = vi.hoisted(() => ({ arabic: 0, chinese: 0 }))
vi.mock("@fontsource-variable/noto-sans-arabic", () => {
    imported.arabic += 1
    return {}
})
vi.mock("@fontsource-variable/noto-sans-sc", () => {
    imported.chinese += 1
    return {}
})

import { loadLocaleFonts } from "./locale-fonts"

describe("loadLocaleFonts", () => {
    it("loads no extra font for languages written in the Latin or Cyrillic script", async () => {
        for (const language of ["fr", "en", "de", "es", "pt", "uk", undefined])
            await loadLocaleFonts(language)

        expect(imported).toEqual({ arabic: 0, chinese: 0 })
    })

    it("loads the Arabic and Chinese fonts once, when their language is chosen", async () => {
        await loadLocaleFonts("zh-CN")
        await loadLocaleFonts("zh-CN")
        expect(imported).toEqual({ arabic: 0, chinese: 1 })

        await loadLocaleFonts("ar")
        await loadLocaleFonts("AR")
        expect(imported).toEqual({ arabic: 1, chinese: 1 })
    })
})
