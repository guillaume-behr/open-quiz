import { createInstance } from "i18next"
import { describe, expect, it } from "vitest"

import { i18nOptions } from "./i18n-options"

describe("i18nOptions", () => {
    it("leaves interpolated user text for React to escape, once", async () => {
        const i18n = createInstance()
        await i18n.init({
            ...i18nOptions,
            lng: "fr",
            resources: {
                fr: { translation: { welcome: "Bienvenue, {{name}}" } },
            },
        })
        expect(i18n.t("welcome", { name: "D'Artagnan & <b>Q/A</b>" })).toBe(
            "Bienvenue, D'Artagnan & <b>Q/A</b>"
        )
    })
})
