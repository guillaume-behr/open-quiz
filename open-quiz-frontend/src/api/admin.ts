import { request, requestPage } from "./client"
import type { NewUser, Page, User } from "./types"

export function getUsers(page = 1): Promise<Page<User>> {
    return requestPage<User>(`/api/admin/users?page=${page}&page_size=8`)
}

export function createUser(user: NewUser): Promise<User> {
    return request<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(user),
    })
}

export function updateUserStatus(
    userId: number,
    isActive: boolean
): Promise<User> {
    return request<User>(`/api/admin/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ is_active: isActive }),
    })
}

export function resetUserCredentials(
    userId: number,
    password: string,
    resetTwoFactor = true
): Promise<User> {
    return request<User>(`/api/admin/users/${userId}/credentials`, {
        method: "POST",
        body: JSON.stringify({
            password,
            reset_two_factor: resetTwoFactor,
        }),
    })
}

export function deleteUser(userId: number): Promise<void> {
    return request<void>(`/api/admin/users/${userId}`, { method: "DELETE" })
}
