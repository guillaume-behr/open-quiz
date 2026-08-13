import { expect, test } from "@playwright/test"

test("Vite proxies HTTP and WebSocket traffic to the API upstream", async ({
    page,
}) => {
    await page.goto("/")

    const health = await page.evaluate(async () => {
        const response = await fetch("/api/network-smoke/health")
        return response.json() as Promise<{ status: string }>
    })
    expect(health).toEqual({ status: "proxied" })

    const message = await page.evaluate(
        () =>
            new Promise<string>((resolve, reject) => {
                const socket = new WebSocket(
                    `${location.origin.replace(/^http/, "ws")}/api/network-smoke/live`
                )
                socket.addEventListener("open", () => {
                    socket.send(JSON.stringify({ token: "network-smoke" }))
                })
                socket.addEventListener("message", (event) => {
                    const payload = JSON.parse(String(event.data)) as {
                        data: string
                    }
                    socket.close()
                    resolve(payload.data)
                })
                socket.addEventListener("error", () =>
                    reject(new Error("WebSocket proxy failed"))
                )
            })
    )
    expect(message).toBe("proxied")
})
