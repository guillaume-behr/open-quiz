import type { Question, QuestionBank } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { LoaderCircle, Upload } from "lucide-react"
import type { FormEvent, RefObject } from "react"
import { useTranslation } from "react-i18next"
import { QuestionForm } from "./question-form"

export function ImportQuestionBankDialog({
    open,
    file,
    inputRef,
    isBusy,
    error,
    onFileChange,
    onClose,
    onSubmit,
}: {
    open: boolean
    file: File | null
    inputRef: RefObject<HTMLInputElement | null>
    isBusy: boolean
    error: string | null
    onFileChange: (file: File | null) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen) onClose()
            }}
            title={t("import-json-title")}
            description={t("import-json-help")}
            size="sm"
        >
            <form onSubmit={onSubmit}>
                <FieldGroup className="gap-4">
                    <Field>
                        <FieldLabel htmlFor="import-json-file">
                            {t("json-file")}
                        </FieldLabel>
                        <Input
                            ref={inputRef}
                            id="import-json-file"
                            type="file"
                            accept="application/json,.json"
                            onChange={(event) =>
                                onFileChange(event.target.files?.[0] ?? null)
                            }
                            required
                        />
                    </Field>
                    {error && <FieldError>{error}</FieldError>}
                    <div className="flex justify-end gap-2 border-t pt-4">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={onClose}
                        >
                            {t("cancel")}
                        </Button>
                        <Button type="submit" disabled={isBusy || !file}>
                            {isBusy ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : (
                                <Upload />
                            )}
                            {t(isBusy ? "importing-json" : "import-json")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

export function DeleteEntityDialog({
    open,
    kind,
    title,
    isBusy,
    error,
    onClose,
    onConfirm,
}: {
    open: boolean
    kind: "bank" | "question"
    title: string
    isBusy: boolean
    error: string | null
    onClose: () => void
    onConfirm: () => void
}) {
    const { t } = useTranslation()
    const titleKey =
        kind === "bank" ? "delete-question-bank" : "delete-question"
    const helpKey =
        kind === "bank" ? "delete-question-bank-help" : "delete-question-help"
    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(titleKey)}
            description={t(helpKey, { title })}
            size="sm"
        >
            <div className="space-y-4">
                {error && <FieldError>{error}</FieldError>}
                <div className="flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        disabled={isBusy}
                        onClick={onClose}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={isBusy}
                        onClick={onConfirm}
                    >
                        {isBusy && (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        )}
                        {t(titleKey)}
                    </Button>
                </div>
            </div>
        </Dialog>
    )
}

export function QuestionFormDialog({
    bank,
    question,
    open,
    onClose,
    onSaved,
}: {
    bank: QuestionBank
    question: Question | null
    open: boolean
    onClose: () => void
    onSaved: (question: Question) => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen) onClose()
            }}
            title={t(question ? "edit-question" : "add-question")}
            description={`${bank.grade_level} — ${bank.chapter}`}
            size="xl"
        >
            <QuestionForm
                key={question?.id ?? "new"}
                questionBankId={bank.id}
                question={question ?? undefined}
                onCancel={onClose}
                onSaved={onSaved}
            />
        </Dialog>
    )
}
