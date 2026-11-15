import type { QuestionBank } from "@/api/types"
import { CollapsibleFilters } from "@/components/ui/collapsible-filters"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import { useState } from "react"
import { useTranslation } from "react-i18next"

const BANK_PAGE_SIZE = 6

/** The question banks of a grade level to draw a quiz from, searchable and paged. */
export function QuestionBankPicker({
    banks,
    gradeLevel,
    selectedIds,
    onSelectedIdsChange,
}: {
    banks: QuestionBank[]
    gradeLevel: string
    selectedIds: number[]
    onSelectedIdsChange: (ids: number[]) => void
}) {
    const { t } = useTranslation()
    const [search, setSearch] = useState("")
    const [page, setPage] = useState(1)

    const trimmedSearch = search.trim().toLowerCase()
    const filtered = banks.filter(
        (bank) =>
            bank.grade_level === gradeLevel &&
            (trimmedSearch === "" ||
                bank.chapter.toLowerCase().includes(trimmedSearch))
    )
    const totalPages = Math.max(1, Math.ceil(filtered.length / BANK_PAGE_SIZE))
    const safePage = Math.min(page, totalPages)
    const visible = filtered.slice(
        (safePage - 1) * BANK_PAGE_SIZE,
        safePage * BANK_PAGE_SIZE
    )

    function toggle(bankId: number) {
        onSelectedIdsChange(
            selectedIds.includes(bankId)
                ? selectedIds.filter((id) => id !== bankId)
                : [...selectedIds, bankId]
        )
    }

    return (
        <Field>
            <FieldLabel htmlFor="quiz-bank-search">
                {t("quiz-question-banks")}
            </FieldLabel>
            <CollapsibleFilters activeCount={Number(Boolean(trimmedSearch))}>
                <Input
                    id="quiz-bank-search"
                    className="max-w-md"
                    value={search}
                    placeholder={t("search-question-bank")}
                    aria-label={t("search-question-bank")}
                    onChange={(event) => {
                        setSearch(event.target.value)
                        setPage(1)
                    }}
                />
            </CollapsibleFilters>
            {filtered.length === 0 ? (
                <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                    {t("quiz-needs-question-bank")}
                </p>
            ) : (
                <>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        {visible.map((bank) => {
                            const selected = selectedIds.includes(bank.id)
                            return (
                                <label
                                    key={bank.id}
                                    className={`flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 ${
                                        selected
                                            ? "border-primary bg-primary/5"
                                            : ""
                                    }`}
                                >
                                    <input
                                        type="checkbox"
                                        className="mt-1 accent-primary"
                                        checked={selected}
                                        onChange={() => toggle(bank.id)}
                                    />
                                    <span className="min-w-0">
                                        <span className="block font-medium">
                                            {bank.chapter}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                            {t("question-count", {
                                                count: bank.question_count,
                                            })}
                                        </span>
                                    </span>
                                </label>
                            )
                        })}
                    </div>
                    <Pagination
                        currentPage={safePage}
                        totalPages={totalPages}
                        onPageChange={setPage}
                    />
                </>
            )}
        </Field>
    )
}
