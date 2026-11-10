import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
    crossedAnnouncement,
    secondsLeft,
    serverClockAnchor,
} from "@/lib/server-clock"

describe("server clock", () => {
    beforeEach(() => {
        vi.useFakeTimers({ toFake: ["Date", "performance"] })
        vi.setSystemTime(new Date("2026-11-10T10:00:00Z"))
    })
    afterEach(() => {
        vi.useRealTimers()
    })

    it("counts down on the server's clock when the client's is off", () => {
        // The server is 3 minutes ahead of this computer.
        const anchor = serverClockAnchor("2026-11-10T10:03:00Z")
        const endsAt = "2026-11-10T10:13:00Z"
        expect(secondsLeft(endsAt, anchor)).toBe(600)
        vi.advanceTimersByTime(60_000)
        expect(secondsLeft(endsAt, anchor)).toBe(540)
        // Without a server time, the client clock would say 13 minutes.
        expect(secondsLeft(endsAt, null)).toBe(720)
    })

    it("ignores a change of the computer's clock during the exam", () => {
        const anchor = serverClockAnchor("2026-11-10T10:00:00Z")
        const endsAt = "2026-11-10T10:10:00Z"
        vi.advanceTimersByTime(30_000)
        // Someone sets the computer's clock an hour ahead.
        vi.setSystemTime(new Date("2026-11-10T11:00:30Z"))
        expect(secondsLeft(endsAt, anchor)).toBe(570)
    })

    it("falls back to the client clock for a missing or bad timestamp", () => {
        expect(serverClockAnchor(null)).toBeNull()
        expect(serverClockAnchor("not a date")).toBeNull()
        expect(secondsLeft("2026-11-10T09:00:00Z", null)).toBe(0)
    })

    it("announces each threshold once, only when crossing it", () => {
        const announced: number[] = []
        let previous: number | null = null
        for (let seconds = 11 * 60; seconds >= 0; seconds -= 1) {
            const crossed = crossedAnnouncement(previous, seconds)
            if (crossed !== undefined) announced.push(crossed)
            previous = seconds
        }
        expect(announced).toEqual([10, 5, 1])
        // Opening the page with 4 minutes left announces nothing yet.
        expect(crossedAnnouncement(null, 240)).toBeUndefined()
    })
})
