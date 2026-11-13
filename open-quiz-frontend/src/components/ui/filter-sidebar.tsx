import { Button } from "@/components/ui/button"
import { FieldGroup } from "@/components/ui/field"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

/**
 * The filters beside a list, with a button to clear them once any is set.
 */
export function FilterSidebar({
    hasFilters,
    onClear,
    children,
}: {
    hasFilters: boolean
    onClear: () => void
    children: ReactNode
}) {
    const { t } = useTranslation()
    return (
        <aside className="h-fit rounded-xl border bg-background p-4">
            <h3 className="font-semibold">{t("filters")}</h3>
            <FieldGroup className="mt-4 gap-4">
                {children}
                {hasFilters && (
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => onClear()}
                    >
                        {t("clear-filters")}
                    </Button>
                )}
            </FieldGroup>
        </aside>
    )
}
