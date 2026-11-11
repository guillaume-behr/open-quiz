// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/api/client"
import type { MakeupSession, QuizSession } from "@/api/types"
import type { connectLiveUpdates } from "@/lib/live-updates"

type AnyOptions = Parameters<typeof connectLiveUpdates<unknown>>[0]
const streams = vi.hoisted(() => [] as { options: unknown; closed: boolean }[])
const api = vi.hoisted(() => ({
    startQuizSession: vi.fn(),
    pauseQuizSession: vi.fn(),
    resumeQuizSession: vi.fn(),
    cancelQuizSession: vi.fn(),
    deleteQuizSession: vi.fn(),
    controlMakeupSession: vi.fn(),
}))

vi.mock("@/lib/live-updates", () => ({
    connectLiveUpdates: (options: unknown) => {
        const stream = { options, closed: false }
        streams.push(stream)
        return () => {
            stream.closed = true
        }
    },
}))
vi.mock("@/api/quizzes", () => api)
vi.mock("react-i18next", () => ({
    useTranslation: () => ({ t: (key: string) => key }),
}))

import {
    type LiveMakeupSessions,
    type LiveQuizSessions,
    useLiveMakeupSessions,
    useLiveQuizSessions,
} from "./use-live-quiz-sessions"

// React warns unless the environment says it supports act().
;(
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null

function mount<T>(useHook: () => T): { current: T } {
    const result = {} as { current: T }
    function Probe() {
        result.current = useHook()
        return null
    }
    root = createRoot(document.createElement("div"))
    act(() => root?.render(createElement(Probe)))
    return result
}

function openStream(path: string): AnyOptions {
    const stream = streams.find(
        (item) => !item.closed && (item.options as AnyOptions).path === path
    )
    if (!stream) throw new Error(`No open stream on ${path}`)
    return stream.options as AnyOptions
}

const classSession = (status: QuizSession["status"]) =>
    ({ id: 5, status, participant_count: 1 }) as QuizSession
const makeupSession = (status: MakeupSession["status"]) =>
    ({ id: 9, status, participant_count: 1 }) as MakeupSession

const CLASS_LIST = "/api/quizzes/live/teacher/sessions"
const MAKEUP_LIST = "/api/quizzes/live/teacher/makeup-sessions"

beforeEach(() => {
    streams.length = 0
    Object.values(api).forEach((mock) => mock.mockReset())
})

afterEach(() => {
    act(() => root?.unmount())
    root = null
})

describe("useLiveQuizSessions", () => {
    it("lists active sessions and follows the open one on its own stream", () => {
        const live = mount<LiveQuizSessions>(useLiveQuizSessions)
        act(() =>
            openStream(CLASS_LIST).onData([
                classSession("waiting"),
                { ...classSession("finished"), id: 6 },
            ])
        )
        expect(live.current.sessions.map((item) => item.id)).toEqual([5])

        act(() => live.current.openSession(live.current.sessions[0]))
        const own = openStream(`${CLASS_LIST}/5`)
        act(() => own.onData(classSession("paused")))
        expect(live.current.activeSession?.status).toBe("paused")
        act(() => own.onConnectionChange?.("reconnecting"))
        expect(live.current.activeSessionReconnecting).toBe(true)
        act(() => own.onDeleted?.())
        expect(live.current.activeSession).toBeNull()
        expect(live.current.sessions).toEqual([])
    })

    it("marks the action running and keeps the session updated", async () => {
        let resolve: (session: QuizSession) => void = () => {}
        api.pauseQuizSession.mockReturnValue(
            new Promise((done) => {
                resolve = done
            })
        )
        const live = mount<LiveQuizSessions>(useLiveQuizSessions)
        act(() => live.current.openSession(classSession("in_progress")))
        let running: Promise<void> = Promise.resolve()
        act(() => {
            running = live.current.runAction("pause")
        })
        expect(live.current.sessionAction).toBe("pause")
        await act(async () => {
            resolve(classSession("paused"))
            await running
        })
        expect(live.current.sessionAction).toBeNull()
        expect(live.current.activeSession?.status).toBe("paused")
    })

    it("confirms, then cancels and closes the session", async () => {
        api.cancelQuizSession.mockResolvedValue(undefined)
        const live = mount<LiveQuizSessions>(useLiveQuizSessions)
        act(() => live.current.openSession(classSession("waiting")))
        act(() => live.current.askToConfirm("cancel"))
        expect(live.current.sessionActionToConfirm).toBe("cancel")
        await act(() => live.current.runAction("cancel"))
        expect(api.cancelQuizSession).toHaveBeenCalledWith(5)
        expect(live.current.sessionActionToConfirm).toBeNull()
        expect(live.current.activeSession).toBeNull()
    })

    it("explains a refused cancellation and a failed deletion", async () => {
        api.cancelQuizSession.mockRejectedValue(new ApiError("conflict", 409))
        api.deleteQuizSession.mockRejectedValue(new Error("network"))
        api.startQuizSession.mockRejectedValue(new Error("network"))
        const live = mount<LiveQuizSessions>(useLiveQuizSessions)
        act(() => live.current.openSession(classSession("waiting")))
        await act(() => live.current.runAction("cancel"))
        expect(live.current.activeSessionError).toBe(
            "quiz-cancel-with-answers-error"
        )
        await act(() => live.current.runAction("start"))
        expect(live.current.activeSessionError).toBe("quiz-start-error")
        await act(() => live.current.runAction("delete"))
        expect(live.current.activeSessionError).toBe(
            "quiz-session-delete-error"
        )
        expect(live.current.activeSession?.id).toBe(5)
    })
})

describe("useLiveMakeupSessions", () => {
    it("follows the list stream and closes a session that left it", () => {
        const live = mount<LiveMakeupSessions>(useLiveMakeupSessions)
        const list = openStream(MAKEUP_LIST)
        act(() => list.onData([makeupSession("in_progress")]))
        act(() => live.current.openSession(live.current.sessions[0]))
        expect(streams).toHaveLength(1)
        act(() => list.onConnectionChange?.("reconnecting"))
        expect(live.current.activeSessionReconnecting).toBe(true)
        act(() => list.onData([makeupSession("finished")]))
        expect(live.current.activeSession).toBeNull()
        expect(live.current.sessions).toEqual([])
    })

    it("finishes through the make-up control and closes the dialog", async () => {
        api.controlMakeupSession.mockResolvedValue(makeupSession("finished"))
        const live = mount<LiveMakeupSessions>(useLiveMakeupSessions)
        act(() =>
            live.current.showLaunchedSession(makeupSession("in_progress"))
        )
        expect(live.current.sessions).toHaveLength(1)
        await act(() => live.current.runAction("finish"))
        expect(api.controlMakeupSession).toHaveBeenCalledWith(9, "finish")
        expect(live.current.activeSession).toBeNull()
        expect(live.current.sessions).toEqual([])
    })

    it("keeps the dialog open with the error of a failed action", async () => {
        api.controlMakeupSession.mockRejectedValue(
            new ApiError("conflict", 409)
        )
        const live = mount<LiveMakeupSessions>(useLiveMakeupSessions)
        act(() => live.current.openSession(makeupSession("waiting")))
        await act(() => live.current.runAction("cancel"))
        expect(live.current.activeSessionError).toBe(
            "makeup-cancel-with-answers-error"
        )
        await act(() => live.current.runAction("pause"))
        expect(live.current.activeSessionError).toBe("makeup-action-error")
        await act(() => live.current.runAction("delete"))
        expect(live.current.activeSessionError).toBe("makeup-action-error")
        expect(live.current.activeSession?.id).toBe(9)
        expect(live.current.sessionAction).toBeNull()
    })
})
