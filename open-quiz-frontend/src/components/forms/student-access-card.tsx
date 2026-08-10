import type { LucideIcon } from "lucide-react"

export const STUDENT_ACCESS_CARD_CLASS_NAME =
    "flex w-full max-w-md flex-col gap-6 rounded-3xl border bg-background px-6 py-8 shadow-lg sm:px-8 sm:py-10"

export function StudentAccessHeader({
    icon: Icon,
    title,
    description,
    headingLevel = 1,
}: {
    icon: LucideIcon
    title: string
    description: string
    headingLevel?: 1 | 3
}) {
    const Heading = headingLevel === 1 ? "h1" : "h3"
    return (
        <div className="flex flex-col items-center gap-3 text-center">
            <div className="rounded-2xl bg-primary/10 p-3 text-primary">
                <Icon className="size-7" aria-hidden="true" />
            </div>
            <div>
                <Heading className="text-2xl font-extrabold">{title}</Heading>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {description}
                </p>
            </div>
        </div>
    )
}
