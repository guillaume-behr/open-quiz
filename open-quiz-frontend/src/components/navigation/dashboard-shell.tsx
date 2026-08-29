import { NavbarAction } from "@/components/navigation/navbar-action"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { LoaderCircle, LogOut, type LucideIcon } from "lucide-react"
import { Suspense, type ReactNode } from "react"

export type DashboardEntry<Section extends string> = {
    id: Section
    icon: LucideIcon
    label: string
    description: string
}

type DashboardShellProps<Section extends string> = {
    entries: DashboardEntry<Section>[]
    activeEntry: DashboardEntry<Section>
    welcome: string
    help: string
    menuLabel: string
    navigationLabel: string
    signOutLabel: string
    loadingLabel: string
    onSelect: (section: Section) => void
    onSignOut: () => void
    headerAction?: ReactNode
    showActiveEntryIcon?: boolean
    children: ReactNode
}

export function DashboardShell<Section extends string>({
    entries,
    activeEntry,
    welcome,
    help,
    menuLabel,
    navigationLabel,
    signOutLabel,
    loadingLabel,
    onSelect,
    onSignOut,
    headerAction,
    showActiveEntryIcon = true,
    children,
}: DashboardShellProps<Section>) {
    return (
        <div className="flex w-full flex-1 flex-col gap-4 overflow-y-auto px-4 py-2 sm:px-6 lg:px-10">
            <NavbarAction>
                <Button variant="outline" onClick={onSignOut}>
                    <LogOut />
                    {signOutLabel}
                </Button>
            </NavbarAction>
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-extrabold">{welcome}</h1>
                    <p className="mt-1 text-sm text-muted-foreground">{help}</p>
                </div>
            </div>

            <div className="grid min-h-0 min-w-0 flex-1 items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="h-fit min-w-0 rounded-2xl border bg-card p-3 shadow-sm">
                    <p className="px-3 py-2 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                        {menuLabel}
                    </p>
                    <nav
                        className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible"
                        aria-label={navigationLabel}
                    >
                        {entries.map((entry) => {
                            const Icon = entry.icon
                            const isActive = entry.id === activeEntry.id
                            return (
                                <button
                                    key={entry.id}
                                    type="button"
                                    onClick={() => onSelect(entry.id)}
                                    aria-current={isActive ? "page" : undefined}
                                    className={cn(
                                        "flex min-w-max items-center gap-3 rounded-xl px-3 py-3 text-start text-sm font-medium transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none lg:w-full lg:min-w-0",
                                        isActive
                                            ? "bg-primary text-primary-foreground shadow-sm"
                                            : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                    )}
                                >
                                    <Icon className="size-5 shrink-0" />
                                    <span>{entry.label}</span>
                                </button>
                            )
                        })}
                    </nav>
                </aside>

                <section
                    key={activeEntry.id}
                    className="min-h-72 min-w-0 animate-in overflow-hidden rounded-2xl border bg-card p-4 shadow-sm duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none sm:p-5 lg:min-h-full"
                    aria-labelledby={`${activeEntry.id}-title`}
                >
                    <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="flex min-w-0 items-start gap-3 sm:gap-4">
                            {showActiveEntryIcon && (
                                <div className="rounded-xl bg-primary/10 p-3 text-primary">
                                    <activeEntry.icon className="size-6" />
                                </div>
                            )}
                            <div className="min-w-0">
                                <h2
                                    id={`${activeEntry.id}-title`}
                                    className="text-2xl font-bold"
                                >
                                    {activeEntry.label}
                                </h2>
                                <p className="mt-1 text-sm text-muted-foreground">
                                    {activeEntry.description}
                                </p>
                            </div>
                        </div>
                        {headerAction}
                    </div>
                    <Suspense
                        fallback={
                            <div
                                className="flex min-h-64 items-center justify-center"
                                role="status"
                                aria-label={loadingLabel}
                            >
                                <LoaderCircle className="size-8 animate-spin text-primary motion-reduce:animate-none" />
                            </div>
                        }
                    >
                        {children}
                    </Suspense>
                </section>
            </div>
        </div>
    )
}
