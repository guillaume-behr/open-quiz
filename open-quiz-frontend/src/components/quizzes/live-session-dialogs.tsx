import { ActiveQuizSessionDialog } from "@/components/quizzes/active-quiz-session-dialog"
import { SessionActionDialog } from "@/components/quizzes/quiz-secondary-dialogs"
import type { LiveQuizSessions } from "@/components/quizzes/use-live-quiz-sessions"

/** The supervision dialog of the open session, and its confirmations. */
export function LiveSessionDialogs({ live }: { live: LiveQuizSessions }) {
    return (
        <>
            <ActiveQuizSessionDialog
                session={live.activeSession}
                error={live.activeSessionError}
                isStarting={live.isStarting}
                action={live.sessionAction}
                onClose={live.closeSession}
                onStart={() => void live.handleStart()}
                onPause={() => void live.handleSessionAction("pause")}
                onResume={() => void live.handleSessionAction("resume")}
                onConfirmCancel={() => live.askToConfirm("cancel")}
                onConfirmDelete={() => live.askToConfirm("delete")}
            />

            <SessionActionDialog
                actionToConfirm={live.sessionActionToConfirm}
                currentAction={live.sessionAction}
                error={live.activeSessionError}
                onClose={() => live.setSessionActionToConfirm(null)}
                onConfirm={(action) =>
                    action === "delete"
                        ? void live.handleDeleteSession()
                        : void live.handleSessionAction("cancel")
                }
            />
        </>
    )
}
