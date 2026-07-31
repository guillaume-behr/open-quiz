import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"

type PaginationProps = {
    currentPage: number
    totalPages: number
    onPageChange: (page: number) => void
}

export function Pagination({
    currentPage,
    totalPages,
    onPageChange,
}: PaginationProps) {
    const { t } = useTranslation()

    if (totalPages <= 1) return null

    return (
        <nav
            className="mt-5 flex items-center justify-center gap-3"
            aria-label={t("pagination")}
        >
            <Button
                type="button"
                size="icon"
                variant="outline"
                disabled={currentPage === 1}
                aria-label={t("previous-page")}
                onClick={() => onPageChange(currentPage - 1)}
            >
                <ChevronLeft aria-hidden="true" />
            </Button>
            <p className="min-w-28 text-center text-sm text-muted-foreground">
                {t("pagination-status", {
                    current: currentPage,
                    total: totalPages,
                })}
            </p>
            <Button
                type="button"
                size="icon"
                variant="outline"
                disabled={currentPage === totalPages}
                aria-label={t("next-page")}
                onClick={() => onPageChange(currentPage + 1)}
            >
                <ChevronRight aria-hidden="true" />
            </Button>
        </nav>
    )
}
