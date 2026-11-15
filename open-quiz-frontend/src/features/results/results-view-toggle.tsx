import { Button } from "@/components/ui/button"
import { CalendarRange, LayoutGrid } from "lucide-react"
import { useTranslation } from "react-i18next"

type ResultsView = "cards" | "schedule"

/** Switches the results between their cards and their weekly schedule. */
export function ResultsViewToggle({
    value,
    onChange,
}: {
    value: ResultsView
    onChange: (view: ResultsView) => void
}) {
    const { t } = useTranslation()
    return (
        <div className="flex gap-1" role="group" aria-label={t("results-view")}>
            <Button
                type="button"
                size="sm"
                variant={value === "cards" ? "default" : "outline"}
                aria-pressed={value === "cards"}
                onClick={() => onChange("cards")}
            >
                <LayoutGrid />
                {t("results-card-view")}
            </Button>
            <Button
                type="button"
                size="sm"
                variant={value === "schedule" ? "default" : "outline"}
                aria-pressed={value === "schedule"}
                onClick={() => onChange("schedule")}
            >
                <CalendarRange />
                {t("results-schedule-view")}
            </Button>
        </div>
    )
}
