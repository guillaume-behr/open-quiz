import { createHash } from "node:crypto"
import { createServer } from "node:http"

const HOST = "127.0.0.1"
const PORT = 4180
const WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

const server = createServer((request, response) => {
    if (request.url === "/healthz") {
        response.writeHead(200)
        response.end()
        return
    }
    if (request.url === "/api/network-smoke/health") {
        response.writeHead(200, { "Content-Type": "application/json" })
        response.end(JSON.stringify({ status: "proxied" }))
        return
    }
    response.writeHead(404)
    response.end()
})

server.on("upgrade", (request, socket) => {
    const key = request.headers["sec-websocket-key"]
    if (typeof key !== "string") {
        socket.destroy()
        return
    }
    const accept = createHash("sha1")
        .update(key + WEBSOCKET_GUID)
        .digest("base64")
    socket.write(
        [
            "HTTP/1.1 101 Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            `Sec-WebSocket-Accept: ${accept}`,
            "",
            "",
        ].join("\r\n")
    )
    if (request.url !== "/api/network-smoke/live") return
    socket.once("data", () => {
        const payload = Buffer.from(
            JSON.stringify({ type: "network_smoke", data: "proxied" })
        )
        socket.write(
            Buffer.concat([Buffer.from([0x81, payload.length]), payload])
        )
    })
})

server.listen(PORT, HOST)
