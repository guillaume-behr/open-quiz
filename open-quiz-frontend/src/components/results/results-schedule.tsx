import type { QuizSession } from "@/api/types"
import { cn } from "@/lib/utils"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"

const HOUR_HEIGHT = 72
const LABEL_WIDTH = 72

type PositionedSession = {
    result: QuizSession
    start: Date
    end: Date
    lane: number
}

function localDateKey(date: Date): string {
    return [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0"),
    ].join("-")
}

function endDate(result: QuizSession, start: Date): Date {
    const parsed = result.ends_at ? new Date(result.ends_at) : null
    return parsed && Number.isFinite(parsed.getTime()) && parsed > start
        ? parsed
        : new Date(start.getTime() + 30 * 60_000)
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
    const dateFormatter = useMemo(
        () => new Intl.DateTimeFormat(locale, { dateStyle: "full" }),
        [locale]
    )
    const timeFormatter = useMemo(
        () =>
            new Intl.DateTimeFormat(locale, {
                hour: "2-digit",
                minute: "2-digit",
            }),
        [locale]
    )
    const days = useMemo(() => {
        const grouped = new Map<string, QuizSession[]>()
        for (const result of results) {
            const start = new Date(result.started_at ?? result.created_at)
            const key = localDateKey(start)
            grouped.set(key, [...(grouped.get(key) ?? []), result])
        }
        return [...grouped.entries()].sort(([left], [right]) =>
            left.localeCompare(right)
        )
    }, [results])

    return (
        <div className="grid gap-6">
            {days.map(([dateKey, dayResults]) => (
                <ScheduleDay
                    key={dateKey}
                    results={dayResults}
                    dateFormatter={dateFormatter}
                    timeFormatter={timeFormatter}
                    onSelect={onSelect}
                    correctionLabel={t("view-results")}
                />
            ))}
        </div>
    )
}

function ScheduleDay({
    results,
    dateFormatter,
    timeFormatter,
    correctionLabel,
    onSelect,
}: {
    results: QuizSession[]
    dateFormatter: Intl.DateTimeFormat
    timeFormatter: Intl.DateTimeFormat
    correctionLabel: string
    onSelect: (result: QuizSession) => void
}) {
    const starts = results.map(
        (result) => new Date(result.started_at ?? result.created_at)
    )
    const dayOrigin = new Date(starts[0])
    dayOrigin.setHours(0, 0, 0, 0)
    const dayStartHour = Math.min(...starts.map((date) => date.getHours()))
    const dayEndHour = Math.max(
        dayStartHour + 1,
        ...results.map((result, index) => {
            const end = endDate(result, starts[index])
            return Math.ceil(
                (end.getTime() - dayOrigin.getTime()) / (60 * 60_000)
            )
        })
    )
    const laneEnds: number[] = []
    const positioned: PositionedSession[] = results
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
    const laneCount = Math.max(1, laneEnds.length)
    const hours = Array.from(
        { length: dayEndHour - dayStartHour + 1 },
        (_, index) => dayStartHour + index
    )
    const timelineHeight = (dayEndHour - dayStartHour) * HOUR_HEIGHT

    return (
        <section className="overflow-hidden rounded-2xl border bg-background shadow-sm">
            <h3 className="border-b bg-muted/40 px-4 py-3 font-bold capitalize">
                {dateFormatter.format(starts[0])}
            </h3>
            <div className="overflow-x-auto p-4">
                <div
                    className="relative min-w-xl"
                    style={{ height: `${timelineHeight}px` }}
                >
                    {hours.map((hour, index) => (
                        <div
                            key={hour}
                            className={cn(
                                "absolute right-0 left-0 border-t",
                                index === hours.length - 1 && "border-b"
                            )}
                            style={{ top: `${index * HOUR_HEIGHT}px` }}
                        >
                            <span className="absolute -top-2.5 left-0 w-14 bg-background text-right text-xs text-muted-foreground tabular-nums">
                                {timeFormatter.format(
                                    new Date(
                                        dayOrigin.getTime() + hour * 60 * 60_000
                                    )
                                )}
                            </span>
                        </div>
                    ))}
                    {positioned.map(({ result, start, end, lane }) => {
                        const startMinutes =
                            (start.getHours() - dayStartHour) * 60 +
                            start.getMinutes()
                        const durationMinutes = Math.max(
                            30,
                            (end.getTime() - start.getTime()) / 60_000
                        )
                        return (
                            <button
                                key={result.id}
                                type="button"
                                className="absolute overflow-hidden rounded-lg border border-primary/30 bg-primary/10 p-1 text-left shadow-sm transition-colors hover:bg-primary/15 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                                style={{
                                    top: `${(startMinutes / 60) * HOUR_HEIGHT + 2}px`,
                                    height: `${Math.max(40, (durationMinutes / 60) * HOUR_HEIGHT - 4)}px`,
                                    left: `calc(${LABEL_WIDTH}px + (100% - ${LABEL_WIDTH}px) * ${lane} / ${laneCount})`,
                                    width: `calc((100% - ${LABEL_WIDTH}px) / ${laneCount} - 4px)`,
                                }}
                                aria-label={`${correctionLabel} — ${result.quiz_title}`}
                                onClick={() => onSelect(result)}
                            >
                                <span className="block truncate text-xs leading-4 font-bold">
                                    {result.quiz_title}
                                </span>
                                <span className="block truncate text-[11px] leading-3 text-muted-foreground">
                                    {timeFormatter.format(start)}–
                                    {timeFormatter.format(end)} ·{" "}
                                    {result.class_name}
                                </span>
                            </button>
                        )
                    })}
                </div>
            </div>
        </section>
    )
}
