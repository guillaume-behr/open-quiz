import { useTranslation } from "react-i18next"

import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function JoinQuizForm() {
    const { t } = useTranslation()

    return (
        <form className="flex w-full max-w-fit min-w-sm flex-col gap-5 rounded-2xl border bg-secondary px-10 py-15 shadow-lg">
            <div className="flex flex-col gap-2">
                <p className="text-center text-4xl font-extrabold">
                    {t("join-quiz-title")}
                </p>
                <p className="text-center font-light">
                    {t("join-quiz-instructions")}
                </p>
            </div>

            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="student-id">
                        {t("student-id")}
                    </FieldLabel>
                    <Input
                        className="py-6"
                        id="student-id"
                        name="studentId"
                        autoComplete="username"
                        placeholder="Ex : marting5"
                        spellCheck={false}
                        required
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="quiz-id">{t("quiz-id")}</FieldLabel>
                    <Input
                        className="py-6"
                        id="quiz-id"
                        name="quizId"
                        autoComplete="off"
                        placeholder="Ex : X45D9"
                        spellCheck={false}
                        required
                    />
                </Field>

                <Button className="text-md py-7 shadow" type="submit">
                    {t("join-quiz-button")}
                </Button>
            </FieldGroup>
        </form>
    )
}
