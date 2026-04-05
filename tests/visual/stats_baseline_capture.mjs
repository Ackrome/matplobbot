import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium, devices } from "playwright";

const ROOT = process.cwd();
const WEB_ROOT = path.join(ROOT, "main_site_frontend");
const ARTIFACTS_DIR = path.join(ROOT, "tests", "visual", "artifacts");
const PORT = 4173;

const MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
};

const mockLeaderboard = [
    { user_id: 1, full_name: "Alice Student", username: "alice", actions_count: 122, last_action_time: "2026-04-05T09:21:00Z" },
    { user_id: 2, full_name: "Bob Student", username: "bob", actions_count: 98, last_action_time: "2026-04-05T08:40:00Z" },
    { user_id: 3, full_name: "Clara Student", username: "clara", actions_count: 66, last_action_time: "2026-04-04T18:32:00Z" },
];

const mockActivity = [
    { period_start: "2026-03-30T00:00:00Z", actions_count: 17 },
    { period_start: "2026-03-31T00:00:00Z", actions_count: 25 },
    { period_start: "2026-04-01T00:00:00Z", actions_count: 21 },
    { period_start: "2026-04-02T00:00:00Z", actions_count: 33 },
    { period_start: "2026-04-03T00:00:00Z", actions_count: 39 },
    { period_start: "2026-04-04T00:00:00Z", actions_count: 29 },
    { period_start: "2026-04-05T00:00:00Z", actions_count: 31 },
];

function resolvePath(urlPath) {
    const noQuery = urlPath.split("?")[0];
    if (noQuery === "/" || noQuery === "") return path.join(WEB_ROOT, "index.html");
    if (noQuery === "/stats") return path.join(WEB_ROOT, "stats.html");
    if (noQuery === "/schedule") return path.join(WEB_ROOT, "schedule.html");
    if (noQuery === "/login") return path.join(WEB_ROOT, "login.html");
    if (noQuery === "/register") return path.join(WEB_ROOT, "register.html");
    if (noQuery === "/studio") return path.join(WEB_ROOT, "studio.html");
    return path.join(WEB_ROOT, noQuery.replace(/^\//, ""));
}

async function createStaticServer() {
    const server = http.createServer(async (req, res) => {
        try {
            const filePath = resolvePath(req.url || "/");
            const data = await fs.readFile(filePath);
            const ext = path.extname(filePath).toLowerCase();
            res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream" });
            res.end(data);
        } catch {
            res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
            res.end("Not found");
        }
    });

    await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));
    return server;
}

async function attachApiMocks(page) {
    await page.route("**/api/auth/me", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ username: "ci-admin", role: "admin" }),
        });
    });

    await page.route("**/api/stats/leaderboard", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(mockLeaderboard),
        });
    });

    await page.route("**/api/stats/activity", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(mockActivity),
        });
    });

    await page.route("**/api/**", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ ok: true }),
        });
    });
}

async function captureDesktop(browser) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 980 } });
    await context.addInitScript(() => localStorage.setItem("jwt_token", "ci-fake-token"));
    const page = await context.newPage();
    await attachApiMocks(page);
    await page.goto(`http://127.0.0.1:${PORT}/stats.html`, { waitUntil: "networkidle" });
    await page.waitForSelector("#leaderboardBody tr");
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "stats-desktop.png"), fullPage: true });
    await context.close();
}

async function captureMobile(browser) {
    const context = await browser.newContext({ ...devices["iPhone 13"] });
    await context.addInitScript(() => localStorage.setItem("jwt_token", "ci-fake-token"));
    const page = await context.newPage();
    await attachApiMocks(page);
    await page.goto(`http://127.0.0.1:${PORT}/stats.html`, { waitUntil: "networkidle" });
    await page.waitForSelector("#leaderboardBody tr");
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "stats-mobile.png"), fullPage: true });
    await context.close();
}

async function main() {
    await fs.mkdir(ARTIFACTS_DIR, { recursive: true });
    const server = await createStaticServer();
    const browser = await chromium.launch();

    try {
        await captureDesktop(browser);
        await captureMobile(browser);
    } finally {
        await browser.close();
        await new Promise((resolve) => server.close(resolve));
    }
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
