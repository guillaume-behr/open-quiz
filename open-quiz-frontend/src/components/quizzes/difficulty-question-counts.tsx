import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { useTranslation } from "react-i18next"
import {
    type Difficulty,
    type DifficultyCounts,
    difficultyKeys,
} from "./quiz-form-state"

/** How many questions of each difficulty a quiz draws, within what the banks hold. */
export function DifficultyQuestionCounts({
    counts,
    available,
    hasSelectedBanks,
    onChange,
}: {
    counts: DifficultyCounts
    available: DifficultyCounts
    hasSelectedBanks: boolean
    onChange: (values: DifficultyCounts) => void
}) {
    const { t } = useTranslation()
    const total = counts.easy + counts.medium + counts.hard
    const maximumFor = (difficulty: Difficulty) =>
        Math.min(available[difficulty], 200 - total + counts[difficulty])

    return (
        <Field>
            <FieldLabel>{t("quiz-difficulty-counts")}</FieldLabel>
            <p className="text-xs text-muted-foreground">
                {t("quiz-difficulty-count-help")}
            </p>
            <div className="mt-2 grid gap-3 sm:grid-cols-3">
                {difficultyKeys.map((difficulty) => (
                    <div key={difficulty}>
                        <FieldLabel htmlFor={`quiz-${difficulty}`}>
                            {t(`difficulty-${difficulty}`)}
                        </FieldLabel>
                        <Input
                            id={`quiz-${difficulty}`}
                            type="number"
                            min={0}
                            max={maximumFor(difficulty)}
                            value={counts[difficulty]}
                            disabled={!hasSelectedBanks}
                            onChange={(event) =>
                                onChange({
                                    ...counts,
                                    [difficulty]: Math.min(
                                        maximumFor(difficulty),
                                        Math.max(0, Number(event.target.value))
                                    ),
                                })
                            }
                            required
                        />
                        <p className="mt-1 text-xs text-muted-foreground">
                            {t("difficulty-available", {
                                count: available[difficulty],
                            })}
                        </p>
                    </div>
                ))}
            </div>
            <p className="mt-3 text-sm font-semibold text-primary">
                {t("quiz-total-questions", { count: total })}
            </p>
            {hasSelectedBanks && total === 0 && (
                <FieldError>{t("quiz-needs-question")}</FieldError>
            )}
        </Field>
    )
}
