import type { StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { UserMinus, UserPlus } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

/** A class's students in its edit form: assign, create or remove them. */
export function ClassStudentsSection({
    studentClass,
    isBusy,
    onOpenAssignment,
    onCreateStudent,
    onUnassign,
}: {
    studentClass: StudentClass
    isBusy: boolean
    onOpenAssignment: () => void
    /** Creates the account in this class; resolves to whether it worked. */
    onCreateStudent: (firstName: string, lastName: string) => Promise<boolean>
    onUnassign: (accountId: number) => void
}) {
    const { t } = useTranslation()
    const [newStudentFirstName, setNewStudentFirstName] = useState("")
    const [newStudentLastName, setNewStudentLastName] = useState("")

    async function createStudent() {
        const firstName = newStudentFirstName.trim()
        const lastName = newStudentLastName.trim()
        if (!firstName || !lastName) return
        if (await onCreateStudent(firstName, lastName)) {
            setNewStudentFirstName("")
            setNewStudentLastName("")
        }
    }

    return (
        <section className="space-y-4 border-t pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="font-semibold">{t("manage-students")}</h3>
                    <p className="text-xs text-muted-foreground">
                        {t("student-count", {
                            count: studentClass.student_count,
                        })}
                    </p>
                </div>
                <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={onOpenAssignment}
                    disabled={isBusy}
                >
                    <UserPlus />
                    {t("assign-student")}
                </Button>
            </div>
            <div className="grid gap-2 rounded-lg border bg-muted/20 p-3 sm:grid-cols-[1fr_1fr_auto]">
                <Input
                    value={newStudentFirstName}
                    onChange={(event) =>
                        setNewStudentFirstName(event.target.value)
                    }
                    placeholder={t("first-name")}
                    aria-label={t("first-name")}
                />
                <Input
                    value={newStudentLastName}
                    onChange={(event) =>
                        setNewStudentLastName(event.target.value)
                    }
                    placeholder={t("last-name")}
                    aria-label={t("last-name")}
                />
                <Button
                    type="button"
                    size="sm"
                    onClick={() => void createStudent()}
                    disabled={
                        isBusy ||
                        !newStudentFirstName.trim() ||
                        !newStudentLastName.trim()
                    }
                >
                    <UserPlus />
                    {t("create-student-account")}
                </Button>
            </div>
            {studentClass.students.length === 0 ? (
                <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                    {t("no-student")}
                </p>
            ) : (
                <ul className="max-h-56 divide-y overflow-auto rounded-lg border bg-background">
                    {studentClass.students.map((student) => (
                        <li
                            key={student.id}
                            className="flex items-center justify-between gap-3 px-4 py-3"
                        >
                            <div>
                                <p className="font-medium">
                                    {student.display_name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {student.identifier}
                                </p>
                            </div>
                            {student.account_id !== null && (
                                <Button
                                    type="button"
                                    size="icon-sm"
                                    variant="ghost"
                                    disabled={isBusy}
                                    onClick={() =>
                                        onUnassign(student.account_id!)
                                    }
                                    aria-label={t("unassign-student")}
                                >
                                    <UserMinus />
                                </Button>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </section>
    )
}
