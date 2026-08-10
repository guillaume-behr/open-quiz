import { CheckCircle2, XCircle } from "lucide-react"

export function Toast({
    message,
    variant = "success",
}: {
    message: string
    variant?: "success" | "error"
}) {
    const Icon = variant === "success" ? CheckCircle2 : XCircle
    return (
        <div
            className={`fixed top-4 left-1/2 z-[100] flex w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 items-center justify-center gap-3 rounded-xl border bg-background px-4 py-3 text-center text-sm shadow-xl ${variant === "error" ? "border-destructive/40 text-destructive" : "border-emerald-500/40 text-emerald-700 dark:text-emerald-300"}`}
            role={variant === "error" ? "alert" : "status"}
            aria-live={variant === "error" ? "assertive" : "polite"}
        >
            <Icon className="size-5 shrink-0" />
            {message}
        </div>
    )
}
