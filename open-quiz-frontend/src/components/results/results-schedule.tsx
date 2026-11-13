import type { QuizSession } from "@/api/types"
import {
    addDays,
    DAYS_PER_WEEK,
    resultStart,
} from "@/components/results/results-utils"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"

const HOUR_HEIGHT = 72
const LABEL_WIDTH = 64

type PositionedSession = {
    result: QuizSession
    start: Date
    end: Date
    lane: number
}

function endDate(result: QuizSession, start: Date): Date {
    const parsed = result.ends_at ? new Date(result.ends_at) : null
    return parsed && Number.isFinite(parsed.getTime()) && parsed > start
        ? parsed
        : new Date(start.getTime() + 30 * 60_000)
}

function positionSessions(results: QuizSession[]): PositionedSession[] {
    const laneEnds: number[] = []
    return results
        .map((result) => {
            const start = resultStart(result)
            return { result, start, end: endDate(result, start) }
        })
        .sort((left, right) => left.start.getTime() - right.start.getTime())
        .map(({ result, start, end }) => {
            let lane = laneEnds.findIndex(
                (laneEnd) => laneEnd <= start.getTime()
            )
            if (lane === -1) lane = laneEnds.length
            laneEnds[lane] = end.getTime()
            return { result, start, end, lane }
        })
}

/**
 * One week of results, Monday to Sunday. The caller loads the week's
 * results and says whether earlier or later weeks hold any.
 */
export function ResultsSchedule({
    weekStart,
    results,
    hasEarlier,
    hasLater,
    locale,
    onWeekChange,
    onSelect,
}: {
    weekStart: Date
    results: QuizSession[]
    hasEarlier: boolean
    hasLater: boolean
    locale: string
    onWeekChange: (weekStart: Date) => void
    onSelect: (result: QuizSession) => void
}) {
    const { t } = useTranslation()
    const weekEnd = addDays(weekStart, DAYS_PER_WEEK)
    const days = Array.from({ length: DAYS_PER_WEEK }, (_, index) =>
        addDays(weekStart, index)
    )
    const weekResults = results.filter((result) => {
        const start = resultStart(result)
        return start >= weekStart && start < weekEnd
    })
    const resultsByDay = days.map((day) =>
        positionSessions(
            weekResults.filter((result) => {
                const start = resultStart(result)
                return (
                    start.getFullYear() === day.getFullYear() &&
                    start.getMonth() === day.getMonth() &&
                    start.getDate() === day.getDate()
                )
            })
        )
    )
    const allStarts = weekResults.map((result) => resultStart(result))
    const dayStartHour =
        allStarts.length > 0
            ? Math.min(...allStarts.map((date) => date.getHours()))
            : 8
    const dayEndHour =
        allStarts.length > 0
            ? Math.max(
                  dayStartHour + 1,
                  ...weekResults.map((result) => {
                      const end = endDate(result, resultStart(result))
                      return Math.min(
                          24,
                          end.getHours() + (end.getMinutes() > 0 ? 1 : 0)
                      )
                  })
              )
            : 18
    const hours = Array.from(
        { length: dayEndHour - dayStartHour + 1 },
        (_, index) => dayStartHour + index
    )
    const timelineHeight = (dayEndHour - dayStartHour) * HOUR_HEIGHT
    const { dayFormatter, rangeFormatter, timeFormatter } = useMemo(
        () => ({
            dayFormatter: new Intl.DateTimeFormat(locale, {
                weekday: "short",
                day: "numeric",
                month: "short",
            }),
            rangeFormatter: new Intl.DateTimeFormat(locale, {
                day: "numeric",
                month: "long",
                year: "numeric",
            }),
            timeFormatter: new Intl.DateTimeFormat(locale, {
                hour: "2-digit",
                minute: "2-digit",
            }),
        }),
        [locale]
    )

    return (
        <section className="overflow-hidden rounded-2xl border bg-background shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/40 px-4 py-3">
                <Button
                    type="button"
                    size="icon-sm"
                    variant="outline"
                    aria-label={t("results-previous-week")}
                    disabled={!hasEarlier}
                    onClick={() =>
                        onWeekChange(addDays(weekStart, -DAYS_PER_WEEK))
                    }
                >
                    <ChevronLeft className="rtl:rotate-180" />
                </Button>
                <h3 className="font-bold capitalize">
                    {rangeFormatter.format(weekStart)} –{" "}
                    {rangeFormatter.format(addDays(weekEnd, -1))}
                </h3>
                <Button
                    type="button"
                    size="icon-sm"
                    variant="outline"
                    aria-label={t("results-next-week")}
                    disabled={!hasLater}
                    onClick={() =>
                        onWeekChange(addDays(weekStart, DAYS_PER_WEEK))
                    }
                >
                    <ChevronRight className="rtl:rotate-180" />
                </Button>
            </div>
            <div className="overflow-x-auto">
                <div
                    key={weekStart.toISOString()}
                    className="min-w-5xl animate-in duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
                >
                    <div
                        className="grid border-b bg-muted/20"
                        style={{
                            gridTemplateColumns: `${LABEL_WIDTH}px repeat(${DAYS_PER_WEEK}, minmax(128px, 1fr))`,
                        }}
                    >
                        <div />
                        {days.map((day) => (
                            <div
                                key={day.toISOString()}
                                className="border-s px-2 py-2 text-center text-sm font-semibold capitalize"
                            >
                                {dayFormatter.format(day)}
                            </div>
                        ))}
                    </div>
                    <div
                        className="relative grid"
                        style={{
                            height: `${timelineHeight}px`,
                            gridTemplateColumns: `${LABEL_WIDTH}px repeat(${DAYS_PER_WEEK}, minmax(128px, 1fr))`,
                        }}
                    >
                        {hours.map((hour, index) => (
                            <div
                                key={hour}
                                className={cn(
                                    "pointer-events-none absolute right-0 left-0 z-10 border-t",
                                    index === hours.length - 1 && "border-b"
                                )}
                                style={{ top: `${index * HOUR_HEIGHT}px` }}
                            >
                                <span className="absolute start-0 -top-2.5 w-14 bg-background text-end text-xs text-muted-foreground tabular-nums">
                                    {timeFormatter.format(
                                        new Date(
                                            weekStart.getFullYear(),
                                            weekStart.getMonth(),
                                            weekStart.getDate(),
                                            hour
                                        )
                                    )}
                                </span>
                            </div>
                        ))}
                        <div />
                        {resultsByDay.map((positioned, dayIndex) => {
                            const laneCount = Math.max(
                                1,
                                ...positioned.map(({ lane }) => lane + 1)
                            )
                            return (
                                <div
                                    key={
                                        days[dayIndex]?.toISOString() ??
                                        dayIndex
                                    }
                                    className="relative border-s"
                                >
                                    {positioned.map(
                                        ({ result, start, end, lane }) => {
                                            const startMinutes =
                                                (start.getHours() -
                                                    dayStartHour) *
                                                    60 +
                                                start.getMinutes()
                                            const durationMinutes = Math.max(
                                                30,
                                                (end.getTime() -
                                                    start.getTime()) /
                                                    60_000
                                            )
                                            return (
                                                <button
                                                    key={result.id}
                                                    type="button"
                                                    className="absolute z-20 overflow-hidden rounded-lg border border-primary/30 bg-primary/10 p-1 text-start shadow-sm transition-colors hover:bg-primary/15 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                                                    style={{
                                                        top: `${(startMinutes / 60) * HOUR_HEIGHT + 2}px`,
                                                        height: `${Math.max(40, (durationMinutes / 60) * HOUR_HEIGHT - 4)}px`,
                                                        left: `calc(${(lane / laneCount) * 100}% + 2px)`,
                                                        width: `calc(${100 / laneCount}% - 4px)`,
                                                    }}
                                                    aria-label={`${t("view-results")} — ${result.quiz_title}`}
                                                    onClick={() =>
                                                        onSelect(result)
                                                    }
                                                >
                                                    <span className="block truncate text-xs leading-4 font-bold">
                                                        {result.quiz_title}
                                                    </span>
                                                    <span className="block truncate text-[11px] leading-3 text-muted-foreground">
                                                        {timeFormatter.format(
                                                            start
                                                        )}
                                                        –
                                                        {timeFormatter.format(
                                                            end
                                                        )}{" "}
                                                        · {result.class_name}
                                                    </span>
                                                </button>
                                            )
                                        }
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </div>
            </div>
        </section>
    )
}
