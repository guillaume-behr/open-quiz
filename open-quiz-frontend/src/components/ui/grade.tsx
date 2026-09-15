import { GRADE_SCALE, formatScore, gradeOnScale } from "@/lib/grades"
import { cn } from "@/lib/utils"
import { Tooltip } from "@base-ui/react/tooltip"
import { useTranslation } from "react-i18next"

type GradeProps = {
    score: number
    maximumScore: number
    /**
     * Wraps the grade in a sentence, for the places that label it. It receives
     * the grade and the scale apart so that the separator between them stays
     * in the translation, where a locale can move it.
     */
    format?: (grade: string, scale: string) => string
    className?: string
    /**
     * A button may not contain a focusable descendant, so a grade sitting
     * inside one opens its tooltip on hover alone.
     */
    focusable?: boolean
}

/**
 * A grade written on the shared scale, with the points behind it in a tooltip.
 * A paper worth no points keeps its raw total: there is nothing to rebase, and
 * a grade of zero out of the scale would read as a mark the student was given.
 */
export function Grade({
    score,
    maximumScore,
    format,
    className,
    focusable = true,
}: GradeProps) {
    const { t, i18n } = useTranslation()
    const locale = i18n.language
    const grade = gradeOnScale(score, maximumScore)
    const [value, scale] =
        grade === null
            ? [
                  formatScore(score, locale),
                  `${formatScore(maximumScore, locale)} ${t("points-short")}`,
              ]
            : [formatScore(grade, locale), formatScore(GRADE_SCALE, locale)]
    const text = format ? format(value, scale) : `${value} / ${scale}`

    if (grade === null) return <span className={className}>{text}</span>

    return (
        <Tooltip.Root>
            <Tooltip.Trigger
                delay={150}
                render={<span />}
                tabIndex={focusable ? 0 : undefined}
                className={cn(
                    "cursor-help rounded-sm underline decoration-dotted decoration-from-font underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                    className
                )}
            >
                {text}
            </Tooltip.Trigger>
            <Tooltip.Portal>
                <Tooltip.Positioner sideOffset={8} className="z-60">
                    <Tooltip.Popup
                        role="tooltip"
                        className="max-w-64 rounded-lg border bg-popover px-3 py-2 text-xs font-medium text-popover-foreground shadow-md transition-[transform,opacity] duration-100 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 motion-reduce:transition-none"
                    >
                        {t("grade-points-detail", {
                            score: formatScore(score, locale),
                            maximum: formatScore(maximumScore, locale),
                        })}
                    </Tooltip.Popup>
                </Tooltip.Positioner>
            </Tooltip.Portal>
        </Tooltip.Root>
    )
}
