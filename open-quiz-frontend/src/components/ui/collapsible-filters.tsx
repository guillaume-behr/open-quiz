import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible"
import { ChevronDown, SlidersHorizontal } from "lucide-react"
import type { ReactNode } from "react"
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

    return (
        <CollapsiblePrimitive.Root
            className={cn(
                "overflow-hidden rounded-xl border border-border/90 bg-muted/55 shadow-inner",
                className
            )}
            defaultOpen={defaultOpen}
        >
            <CollapsiblePrimitive.Trigger className="group flex w-full items-center gap-2 px-4 py-3 text-start font-semibold transition-colors select-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-inset">
                <SlidersHorizontal className="size-4 text-primary" />
                <span>{t("filters")}</span>
                {activeCount > 0 && (
                    <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-bold text-primary-foreground">
                        {activeCount}
                    </span>
                )}
                <ChevronDown className="ms-auto size-4 text-muted-foreground transition-transform duration-200 ease-out group-data-panel-open:rotate-180 motion-reduce:transition-none" />
            </CollapsiblePrimitive.Trigger>
            <CollapsiblePrimitive.Panel className="h-[var(--collapsible-panel-height)] overflow-hidden opacity-100 transition-[height,opacity] duration-200 ease-out data-ending-style:h-0 data-ending-style:opacity-0 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-none [&[hidden]:not([hidden='until-found'])]:hidden">
                <div className="border-t border-border/80 bg-background/35 p-4">
                    {children}
                </div>
            </CollapsiblePrimitive.Panel>
        </CollapsiblePrimitive.Root>
    )
}
