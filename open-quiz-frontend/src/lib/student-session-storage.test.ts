// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import type { StudentAccount } from "@/api/types"
import {
    clearStoredStudentSession,
    clearStudentStorage,
    QUIZ_SESSION_STORAGE_KEY,
    readStoredStudentSession,
    rememberedStudentFor,
    rememberStudent,
    storeStudentSession,
} from "@/lib/student-session-storage"

afterEach(() => {
    vi.restoreAllMocks()
    sessionStorage.clear()
})

describe("student session storage", () => {
    it("stores, reads back and clears a session", () => {
        const stored = { joinCode: "ABC123", participantToken: "token" }
        storeStudentSession(QUIZ_SESSION_STORAGE_KEY, stored)
        expect(readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)).toEqual(
            stored
        )
        clearStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)
        expect(readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)).toBeNull()
    })

    it("ignores a stored value that is not a session", () => {
        for (const value of ["not json", '{"joinCode": 1}', "[]", "null"]) {
            sessionStorage.setItem(QUIZ_SESSION_STORAGE_KEY, value)
            expect(
                readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)
            ).toBeNull()
        }
    })

    it("keeps only the expected fields", () => {
        sessionStorage.setItem(
            QUIZ_SESSION_STORAGE_KEY,
            '{"joinCode": "ABC123", "participantToken": "t", "extra": true}'
        )
        expect(readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)).toEqual({
            joinCode: "ABC123",
            participantToken: "t",
        })
    })

    it("tolerates unavailable browser storage", () => {
        vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new Error("blocked")
        })
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
            throw new Error("blocked")
        })
        vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
            throw new Error("blocked")
        })
        expect(readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)).toBeNull()
        expect(() =>
            storeStudentSession(QUIZ_SESSION_STORAGE_KEY, {
                joinCode: "A",
                participantToken: "B",
            })
        ).not.toThrow()
        expect(() =>
            clearStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)
        ).not.toThrow()
    })

    it("keeps a session in memory when storage is blocked, until cleared", () => {
        for (const method of ["getItem", "setItem", "removeItem"] as const) {
            vi.spyOn(Storage.prototype, method).mockImplementation(() => {
                throw new Error("blocked")
            })
        }
        const stored = { joinCode: "ABC123", participantToken: "token" }
        storeStudentSession(QUIZ_SESSION_STORAGE_KEY, stored)
        expect(readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)).toEqual(
            stored
        )
        clearStudentStorage()
        expect(readStoredStudentSession(QUIZ_SESSION_STORAGE_KEY)).toBeNull()
    })

    it("remembers the signed-in student for their token only", () => {
        const student = { id: 7, display_name: "Alex" } as StudentAccount
        rememberStudent("token-a", student)
        expect(rememberedStudentFor("token-a")).toBe(student)
        expect(rememberedStudentFor("token-b")).toBeNull()
        expect(rememberedStudentFor(null)).toBeNull()
        clearStudentStorage()
        expect(rememberedStudentFor("token-a")).toBeNull()
    })
})
