import type { MakeupSession, QuizSession } from "@/api/types"
import { ActiveQuizSessionDialog } from "@/components/quizzes/active-quiz-session-dialog"
import { SessionActionDialog } from "@/components/quizzes/quiz-secondary-dialogs"
import type { LiveSessions } from "@/components/quizzes/use-live-sessions"

type LiveSessionDialogsProps =
    | { kind: "class"; live: LiveSessions<QuizSession> }
    | { kind: "makeup"; live: LiveSessions<MakeupSession> }

/**
 * The supervision dialog of the open session, and its confirmations. A
 * make-up session can be finished early but not deleted.
 */
export function LiveSessionDialogs({ kind, live }: LiveSessionDialogsProps) {
    return (
        <>
            <ActiveQuizSessionDialog
                session={live.activeSession}
                error={live.activeSessionError}
                reconnecting={live.activeSessionReconnecting}
                action={live.sessionAction}
                onClose={live.closeSession}
                onStart={() => void live.runAction("start")}
                onPause={() => void live.runAction("pause")}
                onResume={() => void live.runAction("resume")}
                onFinish={
                    kind === "makeup"
                        ? () => live.askToConfirm("finish")
                        : undefined
                }
                onConfirmCancel={() => live.askToConfirm("cancel")}
                onConfirmDelete={
                    kind === "class"
                        ? () => live.askToConfirm("delete")
                        : undefined
                }
            />

            <SessionActionDialog
                kind={kind}
                actionToConfirm={live.sessionActionToConfirm}
                currentAction={live.sessionAction}
                error={live.activeSessionError}
                onClose={() => live.setSessionActionToConfirm(null)}
                onConfirm={(action) => void live.runAction(action)}
            />
        </>
    )
}
