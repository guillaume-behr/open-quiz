import { Eye, EyeOff } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"
import { Button } from "./button"
import { Input } from "./input"

export function PasswordInput({
    className,
    ...props
}: Omit<React.ComponentProps<"input">, "type">) {
    const { t } = useTranslation()
    const [visible, setVisible] = useState(false)

    return (
        <div className="relative">
            <Input
                {...props}
                type={visible ? "text" : "password"}
                className={cn("pe-10", className)}
            />
            <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="absolute end-1 top-1/2 size-8 -translate-y-1/2 active:not-aria-[haspopup]:-translate-y-1/2"
                aria-label={t(visible ? "hide-password" : "show-password")}
                aria-pressed={visible}
                onClick={() => setVisible((current) => !current)}
            >
                {visible ? (
                    <EyeOff className="size-4" />
                ) : (
                    <Eye className="size-4" />
                )}
            </Button>
        </div>
    )
}
