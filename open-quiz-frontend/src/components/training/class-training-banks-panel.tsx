import { getAllStudentClasses } from "@/api/classes"
import { getAllQuestionBanks } from "@/api/question-banks"
import {
    getClassTrainingQuestionBanks,
    updateClassTrainingQuestionBanks,
} from "@/api/quizzes"
import type { QuestionBank, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import {
    CheckCircle2,
    LibraryBig,
    LoaderCircle,
    Save,
    School,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

export function ClassTrainingBanksPanel() {
    const { t } = useTranslation()
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [banks, setBanks] = useState<QuestionBank[]>([])
    const [selectedClassId, setSelectedClassId] = useState("")
    const [selectedBankIds, setSelectedBankIds] = useState<number[]>([])
    const [savedBankIds, setSavedBankIds] = useState<number[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [isClassLoading, setIsClassLoading] = useState(false)
    const [isSaving, setIsSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [saved, setSaved] = useState(false)

    useEffect(() => {
        let active = true
        Promise.all([getAllStudentClasses(), getAllQuestionBanks()])
            .then(([loadedClasses, loadedBanks]) => {
                if (!active) return
                setClasses(loadedClasses)
                setBanks(loadedBanks)
                setIsClassLoading(loadedClasses.length > 0)
                setSelectedClassId(
                    loadedClasses[0] ? String(loadedClasses[0].id) : ""
                )
            })
            .catch(() => active && setError(t("training-settings-load-error")))
            .finally(() => active && setIsLoading(false))
        return () => {
            active = false
        }
    }, [t])

    useEffect(() => {
        if (!selectedClassId) return
        let active = true
        getClassTrainingQuestionBanks(Number(selectedClassId))
            .then((assignedBanks) => {
                if (!active) return
                const ids = assignedBanks.map((bank) => bank.id)
                setSelectedBankIds(ids)
                setSavedBankIds(ids)
            })
            .catch(() => active && setError(t("training-settings-load-error")))
            .finally(() => active && setIsClassLoading(false))
        return () => {
            active = false
        }
    }, [selectedClassId, t])

    const hasChanges = useMemo(
        () =>
            [...selectedBankIds].sort((a, b) => a - b).join(",") !==
            [...savedBankIds].sort((a, b) => a - b).join(","),
        [savedBankIds, selectedBankIds]
    )
    const selectedClass = classes.find(
        (studentClass) => String(studentClass.id) === selectedClassId
    )
    const eligibleBanks = selectedClass
        ? banks.filter((bank) => bank.grade_level === selectedClass.grade_level)
        : []

    async function save() {
        if (!selectedClassId) return
        setIsSaving(true)
        setError(null)
        setSaved(false)
        try {
            const assigned = await updateClassTrainingQuestionBanks(
                Number(selectedClassId),
                selectedBankIds
            )
            const ids = assigned.map((bank) => bank.id)
            setSelectedBankIds(ids)
            setSavedBankIds(ids)
            setSaved(true)
        } catch {
            setError(t("training-settings-save-error"))
        } finally {
            setIsSaving(false)
        }
    }

    if (isLoading) {
        return (
            <div
                className="flex min-h-48 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle className="size-8 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )
    }

    return (
        <div className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
            <aside className="h-fit rounded-xl border bg-background p-4">
                <h3 className="flex items-center gap-2 font-semibold">
                    <School className="size-4 text-primary" />
                    {t("training-class-selection")}
                </h3>
                <FieldGroup className="mt-4 gap-4">
                    <Field>
                        <FieldLabel htmlFor="training-class">
                            {t("class-name")}
                        </FieldLabel>
                        <select
                            id="training-class"
                            className={NATIVE_SELECT_CLASS_NAME}
                            value={selectedClassId}
                            disabled={isSaving}
                            onChange={(event) => {
                                setIsClassLoading(true)
                                setError(null)
                                setSaved(false)
                                setSelectedClassId(event.target.value)
                            }}
                        >
                            {classes.length === 0 && (
                                <option value="">{t("no-class")}</option>
                            )}
                            {classes.map((studentClass) => (
                                <option
                                    key={studentClass.id}
                                    value={studentClass.id}
                                >
                                    {studentClass.name} ·{" "}
                                    {studentClass.grade_level}
                                </option>
                            ))}
                        </select>
                    </Field>
                    <p className="text-xs text-muted-foreground">
                        {t("training-class-selection-help")}
                    </p>
                </FieldGroup>
            </aside>

            <section className="min-w-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <h3 className="font-semibold">
                            {t("training-available-banks")}
                        </h3>
                        <p className="mt-1 text-sm text-muted-foreground">
                            {t("training-available-banks-help")}
                        </p>
                    </div>
                    <Button
                        type="button"
                        onClick={() => void save()}
                        disabled={
                            !selectedClassId ||
                            !hasChanges ||
                            isSaving ||
                            isClassLoading
                        }
                    >
                        {isSaving ? (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <Save />
                        )}
                        {t("save-training-banks")}
                    </Button>
                </div>

                {error && (
                    <p
                        role="alert"
                        className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
                    >
                        {error}
                    </p>
                )}
                {saved && (
                    <p
                        className="mt-4 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300"
                        role="status"
                    >
                        <CheckCircle2 className="size-4" />
                        {t("training-settings-saved")}
                    </p>
                )}

                {classes.length === 0 ? (
                    <EmptyState
                        title={t("no-class")}
                        help={t("training-needs-class")}
                    />
                ) : isClassLoading ? (
                    <div
                        className="flex min-h-40 items-center justify-center"
                        role="status"
                        aria-label={t("page-loading")}
                    >
                        <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
                    </div>
                ) : eligibleBanks.length === 0 ? (
                    <EmptyState
                        title={t("no-question-bank")}
                        help={t("training-needs-grade-level-bank", {
                            gradeLevel: selectedClass?.grade_level,
                        })}
                    />
                ) : (
                    <div
                        key={eligibleBanks.map((bank) => bank.id).join(",")}
                        className="mt-4 grid animate-in gap-3 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none lg:grid-cols-2"
                    >
                        {eligibleBanks.map((bank) => {
                            const selected = selectedBankIds.includes(bank.id)
                            return (
                                <label
                                    key={bank.id}
                                    className={`flex cursor-pointer gap-3 rounded-xl border bg-background p-4 transition focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 ${
                                        selected
                                            ? "border-primary bg-primary/5"
                                            : "hover:border-primary/50"
                                    }`}
                                >
                                    <input
                                        type="checkbox"
                                        className="mt-1 accent-primary"
                                        checked={selected}
                                        onChange={() =>
                                            setSelectedBankIds((current) =>
                                                selected
                                                    ? current.filter(
                                                          (id) => id !== bank.id
                                                      )
                                                    : [...current, bank.id]
                                            )
                                        }
                                    />
                                    <span className="min-w-0">
                                        <span className="block font-medium break-words">
                                            {bank.chapter}
                                        </span>
                                        <span className="mt-1 block text-xs text-muted-foreground">
                                            {bank.grade_level} ·{" "}
                                            {t("question-count", {
                                                count: bank.question_count,
                                            })}
                                        </span>
                                    </span>
                                </label>
                            )
                        })}
                    </div>
                )}
            </section>
        </div>
    )
}

function EmptyState({ title, help }: { title: string; help: string }) {
    return (
        <div className="mt-4 flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
            <LibraryBig className="mb-2 size-8" />
            <p className="font-medium">{title}</p>
            <p className="mt-1 text-sm">{help}</p>
        </div>
    )
}
