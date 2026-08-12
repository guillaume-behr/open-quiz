import { ChevronDown, SlidersHorizontal } from "lucide-react"
import type { ReactNode } from "react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"

export function CollapsibleFilters({
    children,
    activeCount = 0,
    defaultOpen = false,
    className,
}: {
    children: ReactNode
    activeCount?: number
    defaultOpen?: boolean
    className?: string
}) {
    const { t } = useTranslation()
    const [isOpen, setIsOpen] = useState(defaultOpen)

    return (
        <details
            className={cn(
                "group overflow-hidden rounded-xl border border-border/90 bg-muted/55 shadow-inner",
                className
            )}
            open={isOpen}
            onToggle={(event) => setIsOpen(event.currentTarget.open)}
        >
            <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 font-semibold transition-colors select-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-inset [&::-webkit-details-marker]:hidden">
                <SlidersHorizontal className="size-4 text-primary" />
                <span>{t("filters")}</span>
                {activeCount > 0 && (
                    <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-bold text-primary-foreground">
                        {activeCount}
                    </span>
                )}
                <ChevronDown className="ms-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <div className="border-t border-border/80 bg-background/35 p-4">
                {children}
            </div>
        </details>
    )
}
