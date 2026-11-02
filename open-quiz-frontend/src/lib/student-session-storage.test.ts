// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import {
    clearStoredStudentSession,
    QUIZ_SESSION_STORAGE_KEY,
    readStoredStudentSession,
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
})
