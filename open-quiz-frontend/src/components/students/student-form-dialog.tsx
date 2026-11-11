import { createStudentAccount, updateStudentAccount } from "@/api/students"
import { ApiError } from "@/api/client"
import { assignStudentAccount, unassignStudentAccount } from "@/api/classes"
import type { StudentAccount, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { formatClassName } from "@/lib/utils"
import { LoaderCircle, Pencil, UserRoundPlus } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"
import { USERNAME_PATTERN } from "@/lib/input-patterns"

/**
 * Creates a student account, or edits one, with its class. Mount it while
 * it is open, keyed by the student, so each opening starts from that student.
 */
export function StudentFormDialog({
    student,
    classes,
    onClose,
    onListsChanged,
}: {
    /** The account to edit, or null to create one. */
    student: StudentAccount | null
    classes: StudentClass[]
    onClose: () => void
    /** Accounts or classes changed: the lists behind the dialog reload. */
    onListsChanged: () => void
}) {
    const { t } = useTranslation()
    const [displayName, setDisplayName] = useState(student?.display_name ?? "")
    const [firstName, setFirstName] = useState("")
    const [lastName, setLastName] = useState("")
    const [identifier, setIdentifier] = useState(student?.identifier ?? "")
    const [password, setPassword] = useState("")
    const [selectedClassId, setSelectedClassId] = useState(
        student?.class_id == null ? "" : String(student.class_id)
    )
    // A created account whose class assignment failed is not created twice.
    const [pendingCreatedAccountId, setPendingCreatedAccountId] = useState<
        number | null
    >(null)
    const [isActive, setIsActive] = useState(student?.is_active ?? true)
    const [isBusy, setIsBusy] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setIsBusy(true)
        setFormError(null)
        let classAssignmentFailed = false
        try {
            if (student) {
                await updateStudentAccount(student.id, {
                    display_name: displayName.trim(),
                    identifier: identifier.trim(),
                    ...(password ? { password } : {}),
                    is_active: isActive,
                })
                const nextClassId = selectedClassId
                    ? Number(selectedClassId)
                    : null
                if (nextClassId !== student.class_id) {
                    try {
                        if (nextClassId !== null) {
                            await assignStudentAccount(nextClassId, student.id)
                        } else if (student.class_id !== null) {
                            await unassignStudentAccount(
                                student.class_id,
                                student.id
                            )
                        }
                    } catch (error) {
                        classAssignmentFailed = true
                        throw error
                    }
                }
            } else {
                let accountId = pendingCreatedAccountId
                if (accountId === null) {
                    const created = await createStudentAccount({
                        first_name: firstName.trim(),
                        last_name: lastName.trim(),
                    })
                    accountId = created.id
                    setPendingCreatedAccountId(accountId)
                }
                if (selectedClassId) {
                    try {
                        await assignStudentAccount(
                            Number(selectedClassId),
                            accountId
                        )
                    } catch (error) {
                        classAssignmentFailed = true
                        throw error
                    }
                }
            }
            onClose()
            onListsChanged()
        } catch (error) {
            if (classAssignmentFailed && !student) {
                onListsChanged()
            }
            setFormError(
                apiErrorMessage(
                    error,
                    t,
                    classAssignmentFailed
                        ? t("student-assignment-error")
                        : error instanceof ApiError && error.status === 409
                          ? t("student-account-duplicate")
                          : t("student-account-save-error")
                )
            )
        } finally {
            setIsBusy(false)
        }
    }

    return (
        <Dialog
            open
            onOpenChange={(open) => !open && !isBusy && onClose()}
            title={t(
                student ? "edit-student-account" : "create-student-account"
            )}
            description={t(
                student
                    ? "student-account-form-help"
                    : "student-id-generated-help"
            )}
            size="md"
        >
            <form onSubmit={submit}>
                <FieldGroup>
                    <div className="grid items-start gap-4 sm:grid-cols-2">
                        {student ? (
                            <>
                                <Field>
                                    <FieldLabel htmlFor="account-name">
                                        {t("student-name")}
                                    </FieldLabel>
                                    <Input
                                        id="account-name"
                                        value={displayName}
                                        onChange={(event) =>
                                            setDisplayName(event.target.value)
                                        }
                                        required
                                    />
                                </Field>
                                <Field>
                                    <FieldLabel htmlFor="account-id">
                                        {t("student-id")}
                                    </FieldLabel>
                                    <Input
                                        id="account-id"
                                        value={identifier}
                                        onChange={(event) =>
                                            setIdentifier(
                                                event.target.value.toLowerCase()
                                            )
                                        }
                                        pattern={USERNAME_PATTERN}
                                        autoComplete="off"
                                        required
                                    />
                                </Field>
                            </>
                        ) : (
                            <>
                                <Field>
                                    <FieldLabel htmlFor="account-first-name">
                                        {t("first-name")}
                                    </FieldLabel>
                                    <Input
                                        id="account-first-name"
                                        value={firstName}
                                        onChange={(event) =>
                                            setFirstName(event.target.value)
                                        }
                                        required
                                    />
                                </Field>
                                <Field>
                                    <FieldLabel htmlFor="account-last-name">
                                        {t("last-name")}
                                    </FieldLabel>
                                    <Input
                                        id="account-last-name"
                                        value={lastName}
                                        onChange={(event) =>
                                            setLastName(event.target.value)
                                        }
                                        required
                                    />
                                </Field>
                            </>
                        )}
                        <Field>
                            <FieldLabel htmlFor="account-class">
                                {t("student-class")}
                            </FieldLabel>
                            <select
                                id="account-class"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={selectedClassId}
                                onChange={(event) =>
                                    setSelectedClassId(event.target.value)
                                }
                                disabled={isBusy}
                            >
                                <option value="">{t("no-class")}</option>
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.id}
                                    >
                                        {formatClassName(
                                            studentClass.grade_level,
                                            studentClass.name
                                        )}
                                    </option>
                                ))}
                            </select>
                            {student && (
                                <p className="text-xs text-muted-foreground">
                                    {t("student-class-help")}
                                </p>
                            )}
                        </Field>
                        {student && (
                            <Field>
                                <FieldLabel htmlFor="account-password">
                                    {t("new-password-optional")}
                                </FieldLabel>
                                <PasswordInput
                                    id="account-password"
                                    value={password}
                                    onChange={(event) =>
                                        setPassword(event.target.value)
                                    }
                                    minLength={8}
                                    autoComplete="new-password"
                                />
                            </Field>
                        )}
                    </div>
                    {student && (
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                className="accent-primary"
                                checked={isActive}
                                onChange={(event) =>
                                    setIsActive(event.target.checked)
                                }
                            />
                            {t("student-account-active")}
                        </label>
                    )}
                    {formError && <FieldError>{formError}</FieldError>}
                    <div className="flex justify-end gap-2 border-t pt-4">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={onClose}
                            disabled={isBusy}
                        >
                            {t("cancel")}
                        </Button>
                        <Button type="submit" disabled={isBusy}>
                            {isBusy ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : student ? (
                                <Pencil />
                            ) : (
                                <UserRoundPlus />
                            )}
                            {t("save-student")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}
