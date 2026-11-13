import { getParticipantAnswers, gradeWrittenAnswer } from "@/api/quizzes"
import type {
    QuizAnswerReview,
    QuizParticipant,
    QuizSession,
} from "@/api/types"
import { useResource } from "@/hooks/use-resource"
import { apiErrorMessage } from "@/lib/errors"
import { formatScore } from "@/lib/grades"
import { useLocale } from "@/lib/locale"
import { useCallback, useState } from "react"
import { useTranslation } from "react-i18next"

function roundScore(score: number): number {
    return Math.round((score + Number.EPSILON) * 100) / 100
}

/**
 * The answers of the participant opened in a result, and the grading of its
 * written answers. Each grade saved is applied at once to the participant's
 * score through `onSessionGraded`, which receives how to update a session.
 */
export function useWrittenAnswerGrading(
    selectedResult: QuizSession | null,
    selectedParticipant: QuizParticipant | null,
    onSessionGraded: (update: (session: QuizSession) => QuizSession) => void
) {
    const { t } = useTranslation()
    const locale = useLocale()
    const selectedResultId = selectedResult?.id
    const selectedParticipantId = selectedParticipant?.id
    const answerList = useResource(
        useCallback(
            () =>
                selectedResultId === undefined ||
                selectedParticipantId === undefined
                    ? Promise.resolve([])
                    : getParticipantAnswers(
                          selectedResultId,
                          selectedParticipantId
                      ),
            [selectedParticipantId, selectedResultId]
        )
    )
    const answers = answerList.isLoading ? [] : (answerList.data ?? [])
    // Drafts only hold what the teacher typed; other answers show their score.
    const [scoreDrafts, setScoreDrafts] = useState<Record<number, string>>({})
    const [feedbackDrafts, setFeedbackDrafts] = useState<
        Record<number, string>
    >({})
    const [gradingAnswerId, setGradingAnswerId] = useState<number | null>(null)
    const [gradeError, setGradeError] = useState<string | null>(null)

    /** Forgets the drafts and the last error, for another participant. */
    function reset() {
        setScoreDrafts({})
        setFeedbackDrafts({})
        setGradeError(null)
    }

    async function grade(answer: QuizAnswerReview): Promise<void> {
        if (!selectedResult || selectedResult.grades_published_at !== null)
            return
        // Number("") is 0: an emptied field must not save a zero.
        const draft = (scoreDrafts[answer.id] ?? String(answer.score)).trim()
        const score = Number(draft)
        if (
            draft === "" ||
            !Number.isFinite(score) ||
            score < 0 ||
            score > answer.max_score
        ) {
            setGradeError(
                t("score-out-of-range", {
                    max: formatScore(answer.max_score, locale),
                })
            )
            return
        }
        const feedback = feedbackDrafts[answer.id] ?? answer.feedback ?? ""
        setGradingAnswerId(answer.id)
        setGradeError(null)
        try {
            const graded = await gradeWrittenAnswer(
                selectedResult.id,
                answer.id,
                score,
                feedback
            )
            const scoreDifference = graded.score - answer.score
            const pendingDifference = answer.is_graded ? 0 : -1
            answerList.setData((current) =>
                current?.map((item) => (item.id === graded.id ? graded : item))
            )
            onSessionGraded((session) =>
                session.id !== selectedResult.id
                    ? session
                    : {
                          ...session,
                          participants: session.participants.map(
                              (participant) =>
                                  participant.id === selectedParticipantId
                                      ? {
                                            ...participant,
                                            score: roundScore(
                                                participant.score +
                                                    scoreDifference
                                            ),
                                            pending_manual_grading_count:
                                                participant.pending_manual_grading_count +
                                                pendingDifference,
                                        }
                                      : participant
                          ),
                      }
            )
        } catch (caught) {
            setGradeError(apiErrorMessage(caught, t, t("grade-answer-error")))
        } finally {
            setGradingAnswerId(null)
        }
    }

    return {
        answers,
        isLoading: answerList.isLoading,
        error:
            gradeError ??
            (answerList.error
                ? apiErrorMessage(answerList.error, t, t("answers-load-error"))
                : null),
        scoreDrafts: Object.fromEntries(
            answers.map((answer) => [
                answer.id,
                scoreDrafts[answer.id] ?? String(answer.score),
            ])
        ),
        feedbackDrafts: Object.fromEntries(
            answers.map((answer) => [
                answer.id,
                feedbackDrafts[answer.id] ?? answer.feedback ?? "",
            ])
        ),
        gradingAnswerId,
        setScoreDraft: (answerId: number, score: string) =>
            setScoreDrafts((current) => ({ ...current, [answerId]: score })),
        setFeedbackDraft: (answerId: number, feedback: string) =>
            setFeedbackDrafts((current) => ({
                ...current,
                [answerId]: feedback,
            })),
        grade,
        reset,
        reload: answerList.reload,
    }
}
