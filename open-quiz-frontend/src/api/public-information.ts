import { request } from "./client"

export type PublicInformation = {
    host: {
        name: string
        address: string
        phone: string
    }
    privacy: {
        controller_name: string
        controller_contact: string
        dpo_contact: string
        legal_basis: string
        recipients: string
        teacher_data_retention: string
        student_data_retention: string
        security_log_retention: string
        quiz_result_retention_days: number
        training_result_retention_days: number
        problem_report_retention_days: number
    }
    cookies: {
        authentication_max_age_days: number
    }
    accessibility: {
        contact: string
        scheme_url: string
        action_plan_url: string
    }
}

export function getPublicInformation(): Promise<PublicInformation> {
    return request<PublicInformation>("/api/public-information")
}
