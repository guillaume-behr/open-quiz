import { LoaderCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

export function PageLoader() {
    const { t } = useTranslation()

    return (
        <div
            className="flex flex-1 items-center justify-center"
            role="status"
            aria-label={t("page-loading")}
        >
            <LoaderCircle
                className="size-9 animate-spin text-primary motion-reduce:animate-none"
                aria-hidden="true"
            />
        </div>
    )
}
