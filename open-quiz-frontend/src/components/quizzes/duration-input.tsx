import { Input } from "@/components/ui/input"
import { useState } from "react"

const MIN_DURATION_MINUTES = 1
const MAX_DURATION_MINUTES = 480

/**
 * The quiz duration in minutes. What the teacher types stays as typed, so
 * the field can be emptied and typed again; the form only receives whole
 * numbers within bounds, and leaving the field brings it back within them.
 * An empty or out-of-range field also blocks submission (required, min, max).
 */
export function DurationInput({
    value,
    onChange,
}: {
    value: number
    onChange: (minutes: number) => void
}) {
    const [draft, setDraft] = useState(String(value))
    const [shownValue, setShownValue] = useState(value)
    // A new value from the form (a reset, a quiz opened for editing).
    if (value !== shownValue) {
        setShownValue(value)
        setDraft(String(value))
    }

    function commit(minutes: number) {
        setShownValue(minutes)
        onChange(minutes)
    }

    return (
        <Input
            id="quiz-duration"
            type="number"
            min={MIN_DURATION_MINUTES}
            max={MAX_DURATION_MINUTES}
            step={1}
            value={draft}
            onChange={(event) => {
                const typed = event.target.value
                setDraft(typed)
                const minutes = Number(typed)
                if (
                    typed.trim() !== "" &&
                    Number.isInteger(minutes) &&
                    minutes >= MIN_DURATION_MINUTES &&
                    minutes <= MAX_DURATION_MINUTES
                )
                    commit(minutes)
            }}
            onBlur={() => {
                const minutes = Number(draft)
                const bounded =
                    draft.trim() === "" || !Number.isFinite(minutes)
                        ? value
                        : Math.min(
                              MAX_DURATION_MINUTES,
                              Math.max(
                                  MIN_DURATION_MINUTES,
                                  Math.round(minutes)
                              )
                          )
                setDraft(String(bounded))
                commit(bounded)
            }}
            required
        />
    )
}
