import type { QuizSession } from "@/api/types"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

const HOUR_HEIGHT = 72
const LABEL_WIDTH = 64
const DAYS_PER_WEEK = 7

type PositionedSession = {
    result: QuizSession
    start: Date
    end: Date
    lane: number
}

function startOfWeek(date: Date): Date {
    const start = new Date(date)
    const mondayOffset = (start.getDay() + 6) % DAYS_PER_WEEK
    start.setDate(start.getDate() - mondayOffset)
    start.setHours(0, 0, 0, 0)
    return start
}

function addDays(date: Date, amount: number): Date {
    const next = new Date(date)
    next.setDate(next.getDate() + amount)
    return next
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
            const start = new Date(result.started_at ?? result.created_at)
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

export function ResultsSchedule({
    results,
    locale,
    onSelect,
}: {
    results: QuizSession[]
    locale: string
    onSelect: (result: QuizSession) => void
}) {
    const { t } = useTranslation()
    const latestResultDate = useMemo(() => {
        const timestamps = results.map((result) =>
            new Date(result.started_at ?? result.created_at).getTime()
        )
        return new Date(Math.max(...timestamps))
    }, [results])
    const [weekOffset, setWeekOffset] = useState(0)
    const weekStart = useMemo(
        () =>
            addDays(startOfWeek(latestResultDate), weekOffset * DAYS_PER_WEEK),
        [latestResultDate, weekOffset]
    )
    const earliestWeekStart = useMemo(() => {
        const timestamps = results.map((result) =>
            startOfWeek(
                new Date(result.started_at ?? result.created_at)
            ).getTime()
        )
        return new Date(Math.min(...timestamps))
    }, [results])
    const earliestWeekOffset = Math.round(
        (earliestWeekStart.getTime() -
            startOfWeek(latestResultDate).getTime()) /
            (DAYS_PER_WEEK * 24 * 60 * 60_000)
    )
    const weekEnd = addDays(weekStart, DAYS_PER_WEEK)
    const days = Array.from({ length: DAYS_PER_WEEK }, (_, index) =>
        addDays(weekStart, index)
    )
    const weekResults = results.filter((result) => {
        const start = new Date(result.started_at ?? result.created_at)
        return start >= weekStart && start < weekEnd
    })
    const resultsByDay = days.map((day) =>
        positionSessions(
            weekResults.filter((result) => {
                const start = new Date(result.started_at ?? result.created_at)
                return (
                    start.getFullYear() === day.getFullYear() &&
                    start.getMonth() === day.getMonth() &&
                    start.getDate() === day.getDate()
                )
            })
        )
    )
    const allStarts = weekResults.map(
        (result) => new Date(result.started_at ?? result.created_at)
    )
    const dayStartHour =
        allStarts.length > 0
            ? Math.min(...allStarts.map((date) => date.getHours()))
            : 8
    const dayEndHour =
        allStarts.length > 0
            ? Math.max(
                  dayStartHour + 1,
                  ...weekResults.map((result, index) => {
                      const end = endDate(result, allStarts[index])
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
    const dayFormatter = new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
    })
    const rangeFormatter = new Intl.DateTimeFormat(locale, {
        day: "numeric",
        month: "long",
        year: "numeric",
    })
    const timeFormatter = new Intl.DateTimeFormat(locale, {
        hour: "2-digit",
        minute: "2-digit",
    })

    return (
        <section className="overflow-hidden rounded-2xl border bg-background shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/40 px-4 py-3">
                <Button
                    type="button"
                    size="icon-sm"
                    variant="outline"
                    aria-label={t("results-previous-week")}
                    disabled={weekOffset <= earliestWeekOffset}
                    onClick={() => setWeekOffset((offset) => offset - 1)}
                >
                    <ChevronLeft />
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
                    disabled={weekOffset >= 0}
                    onClick={() => setWeekOffset((offset) => offset + 1)}
                >
                    <ChevronRight />
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
                                className="border-l px-2 py-2 text-center text-sm font-semibold capitalize"
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
                                <span className="absolute -top-2.5 left-0 w-14 bg-background text-right text-xs text-muted-foreground tabular-nums">
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
                                    key={days[dayIndex].toISOString()}
                                    className="relative border-l"
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
                                                    className="absolute z-20 overflow-hidden rounded-lg border border-primary/30 bg-primary/10 p-1 text-left shadow-sm transition-colors hover:bg-primary/15 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
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
