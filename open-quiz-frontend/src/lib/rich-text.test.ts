import { describe, expect, it } from "vitest"

import {
    hasRichTextFormatting,
    parseRichText,
    richTextToPlainText,
    toggleRichTextMarker,
} from "@/lib/rich-text"

describe("parseRichText", () => {
    it("keeps plain text and line breaks as typed", () => {
        expect(parseRichText("Ligne 1\nLigne 2")).toEqual([
            { type: "text", text: "Ligne 1\nLigne 2" },
        ])
    })

    it("reads bold, italic and inline code", () => {
        expect(parseRichText("Un **mot** en *italique* et `x = 1`")).toEqual([
            { type: "text", text: "Un " },
            { type: "bold", children: [{ type: "text", text: "mot" }] },
            { type: "text", text: " en " },
            { type: "italic", children: [{ type: "text", text: "italique" }] },
            { type: "text", text: " et " },
            { type: "code", text: "x = 1" },
        ])
    })

    it("nests italic in bold and bold in italic", () => {
        expect(parseRichText("**a *b* c**")).toEqual([
            {
                type: "bold",
                children: [
                    { type: "text", text: "a " },
                    { type: "italic", children: [{ type: "text", text: "b" }] },
                    { type: "text", text: " c" },
                ],
            },
        ])
        expect(parseRichText("*a **b** c*")).toEqual([
            {
                type: "italic",
                children: [
                    { type: "text", text: "a " },
                    { type: "bold", children: [{ type: "text", text: "b" }] },
                    { type: "text", text: " c" },
                ],
            },
        ])
        expect(parseRichText("***mot***")).toEqual([
            {
                type: "bold",
                children: [
                    {
                        type: "italic",
                        children: [{ type: "text", text: "mot" }],
                    },
                ],
            },
        ])
    })

    it("shares a closing star run between nested emphases", () => {
        expect(parseRichText("*a **b***")).toEqual([
            {
                type: "italic",
                children: [
                    { type: "text", text: "a " },
                    { type: "bold", children: [{ type: "text", text: "b" }] },
                ],
            },
        ])
        expect(parseRichText("**a *b***")).toEqual([
            {
                type: "bold",
                children: [
                    { type: "text", text: "a " },
                    { type: "italic", children: [{ type: "text", text: "b" }] },
                ],
            },
        ])
    })

    it("leaves lone or spaced markers untouched", () => {
        expect(richTextToPlainText("2 * 3 * 4")).toBe("2 * 3 * 4")
        expect(parseRichText("2 * 3 * 4")).toEqual([
            { type: "text", text: "2 * 3 * 4" },
        ])
        expect(parseRichText("**pas fermé")).toEqual([
            { type: "text", text: "**pas fermé" },
        ])
        expect(parseRichText("a `` b")).toEqual([
            { type: "text", text: "a `` b" },
        ])
    })

    it("does not read markers inside inline code", () => {
        expect(parseRichText("`**x**`")).toEqual([
            { type: "code", text: "**x**" },
        ])
    })

    it("shows escaped markers literally", () => {
        expect(parseRichText("\\*pas italique\\*")).toEqual([
            { type: "text", text: "*pas italique*" },
        ])
    })

    it("never produces HTML", () => {
        expect(richTextToPlainText("<b>x</b> **<i>y</i>**")).toBe(
            "<b>x</b> <i>y</i>"
        )
    })
})

describe("hasRichTextFormatting", () => {
    it("tells formatted prompts from plain ones", () => {
        expect(hasRichTextFormatting("Simple question ?")).toBe(false)
        expect(hasRichTextFormatting("Une **vraie** question")).toBe(true)
    })
})

describe("toggleRichTextMarker", () => {
    it("wraps the selection and keeps it selected", () => {
        expect(
            toggleRichTextMarker(
                { value: "un mot ici", selectionStart: 3, selectionEnd: 6 },
                "**"
            )
        ).toEqual({
            value: "un **mot** ici",
            selectionStart: 5,
            selectionEnd: 8,
        })
    })

    it("leaves edge spaces outside the markers", () => {
        expect(
            toggleRichTextMarker(
                { value: "un mot ici", selectionStart: 2, selectionEnd: 7 },
                "*"
            ).value
        ).toBe("un *mot* ici")
    })

    it("removes markers around or inside the selection", () => {
        expect(
            toggleRichTextMarker(
                { value: "un **mot** ici", selectionStart: 5, selectionEnd: 8 },
                "**"
            )
        ).toEqual({ value: "un mot ici", selectionStart: 3, selectionEnd: 6 })
        expect(
            toggleRichTextMarker(
                {
                    value: "un **mot** ici",
                    selectionStart: 3,
                    selectionEnd: 10,
                },
                "**"
            )
        ).toEqual({ value: "un mot ici", selectionStart: 3, selectionEnd: 6 })
    })

    it("tells italic from bold when toggling", () => {
        expect(
            toggleRichTextMarker(
                { value: "**mot**", selectionStart: 2, selectionEnd: 5 },
                "*"
            ).value
        ).toBe("***mot***")
        expect(
            toggleRichTextMarker(
                { value: "***mot***", selectionStart: 3, selectionEnd: 6 },
                "*"
            ).value
        ).toBe("**mot**")
        expect(
            toggleRichTextMarker(
                { value: "***mot***", selectionStart: 3, selectionEnd: 6 },
                "**"
            ).value
        ).toBe("*mot*")
    })

    it("inserts an empty pair at the caret", () => {
        expect(
            toggleRichTextMarker(
                { value: "ab", selectionStart: 1, selectionEnd: 1 },
                "**"
            )
        ).toEqual({ value: "a****b", selectionStart: 3, selectionEnd: 3 })
    })
})
