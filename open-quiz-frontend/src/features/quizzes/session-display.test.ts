// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import type { MakeupSession, QuizSession } from "@/api/types"

import {
    isSessionDisplayKey,
    publishSessionDisplay,
    readSessionDisplay,
    sessionDisplayKey,
    sessionDisplayPath,
    sessionDisplayPayload,
    subscribeSessionDisplay,
    type SessionDisplayPayload,
} from "./session-display"

const quizSession = {
    id: 3,
    quiz_id: 9,
    class_name: "Tle 1",
    join_code: "ABC123",
    status: "in_progress",
    ends_at: "2026-01-01T10:00:00Z",
    server_now: "2026-01-01T09:00:00Z",
    participant_count: 2,
    participants: [{ has_finished: true }, { has_finished: false }],
} as unknown as QuizSession
const makeupSession = {
    id: 4,
    class_name: "Tle 2",
    join_code: "XYZ789",
    status: "waiting",
    participant_count: 0,
} as unknown as MakeupSession

function payload(overrides: Partial<SessionDisplayPayload> = {}) {
    return { ...sessionDisplayPayload(quizSession, "Quiz"), ...overrides }
}

describe("session display", () => {
    afterEach(() => localStorage.clear())

    it("names sessions and recognizes their keys", () => {
        expect(sessionDisplayKey(quizSession)).toBe("quiz-3")
        expect(sessionDisplayKey(makeupSession)).toBe("makeup-4")
        expect(sessionDisplayPath("quiz-3")).toBe(
            "/teacher/session-display/quiz-3"
        )
        expect(isSessionDisplayKey("makeup-12")).toBe(true)
        expect(isSessionDisplayKey("other-1")).toBe(false)
        expect(isSessionDisplayKey(undefined)).toBe(false)
    })

    it("summarizes a quiz or a make-up session", () => {
        expect(payload()).toMatchObject({
            sessionKey: "quiz-3",
            className: "Tle 1",
            endsAt: "2026-01-01T10:00:00Z",
            serverNow: "2026-01-01T09:00:00Z",
            participantCount: 2,
            finishedCount: 1,
        })
        expect(sessionDisplayPayload(makeupSession, "M")).toMatchObject({
            sessionKey: "makeup-4",
            endsAt: null,
            serverNow: null,
            finishedCount: 0,
        })
    })

    it("stores the last value, ignoring stale or malformed ones", () => {
        publishSessionDisplay(payload())
        expect(readSessionDisplay("quiz-3")?.title).toBe("Quiz")
        expect(readSessionDisplay("quiz-4")).toBeNull()

        const key = "open-quiz-session-display:quiz-3"
        localStorage.setItem(key, "{not json")
        expect(readSessionDisplay("quiz-3")).toBeNull()
        localStorage.setItem(
            key,
            JSON.stringify(payload({ sessionKey: "bad" }))
        )
        expect(readSessionDisplay("quiz-3")).toBeNull()
        localStorage.setItem(key, JSON.stringify(payload({ updatedAt: 0 })))
        expect(readSessionDisplay("quiz-3")).toBeNull()
    })

    it("survives browsers without storage or broadcast channels", () => {
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
            throw new Error("full")
        })
        vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new Error("blocked")
        })
        vi.stubGlobal("BroadcastChannel", undefined)
        expect(() => publishSessionDisplay(payload())).not.toThrow()
        expect(readSessionDisplay("quiz-3")).toBeNull()
        const unsubscribe = subscribeSessionDisplay("quiz-3", () => undefined)
        expect(() => unsubscribe()).not.toThrow()
    })

    it("delivers broadcasts and storage events for its own session", () => {
        const listeners: ((event: MessageEvent) => void)[] = []
        class FakeChannel {
            addEventListener(
                _: string,
                listener: (event: MessageEvent) => void
            ) {
                listeners.push(listener)
            }
            removeEventListener = vi.fn()
            postMessage(data: unknown) {
                for (const listener of listeners)
                    listener({ data } as MessageEvent)
            }
            close = vi.fn()
        }
        vi.stubGlobal("BroadcastChannel", FakeChannel)
        const received: string[] = []
        const unsubscribe = subscribeSessionDisplay("quiz-3", (value) =>
            received.push(value.title)
        )
        publishSessionDisplay(payload({ title: "broadcast" }))
        publishSessionDisplay(payload({ sessionKey: "quiz-4", title: "other" }))

        const key = "open-quiz-session-display:quiz-3"
        window.dispatchEvent(
            new StorageEvent("storage", {
                key,
                newValue: JSON.stringify(payload({ title: "stored" })),
            })
        )
        window.dispatchEvent(
            new StorageEvent("storage", { key, newValue: null })
        )
        window.dispatchEvent(
            new StorageEvent("storage", { key: "unrelated", newValue: "{}" })
        )
        expect(received).toEqual(["broadcast", "stored"])
        unsubscribe()
        window.dispatchEvent(
            new StorageEvent("storage", {
                key,
                newValue: JSON.stringify(payload({ title: "late" })),
            })
        )
        expect(received).toEqual(["broadcast", "stored"])
    })
})
