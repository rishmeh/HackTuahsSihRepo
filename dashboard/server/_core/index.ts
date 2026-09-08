import "dotenv/config";
import express from "express";
import { createServer } from "http";
import net from "net";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { registerOAuthRoutes } from "./oauth";
import { registerStorageProxy } from "./storageProxy";
import { appRouter } from "../routers";
import { createContext } from "./context";
import { serveStatic, setupVite } from "./vite";

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);
  // Configure body parser with larger size limit for file uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));
  registerStorageProxy(app);
  registerOAuthRoutes(app);
  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );

  // ── Plain REST routes (used by ML voice agent) ────────────────────────────
  // These bypass tRPC auth to allow the local Python process to persist data.
  app.get("/api/quizzes", async (req, res) => {
    try {
      const { getDb } = await import("../db.js");
      const { quizzes } = await import("../../drizzle/schema.js");
      const { eq, desc } = await import("drizzle-orm");
      const db = await getDb();
      const profileId = parseInt(String(req.query.profileId ?? "0"), 10);
      const rows = await db.select().from(quizzes).where(eq(quizzes.ownerProfileId, profileId)).orderBy(desc(quizzes.createdAt));
      res.json(rows);
    } catch (err) { res.status(500).json({ error: String(err) }); }
  });

  app.post("/api/quizzes", async (req, res) => {
    try {
      const { getDb } = await import("../db.js");
      const { quizzes } = await import("../../drizzle/schema.js");
      const db = await getDb();
      const { ownerProfileId = 0, topic, questions = "[]", totalQuestions = 0 } = req.body as Record<string, unknown>;
      const [row] = await db.insert(quizzes).values({ ownerProfileId: Number(ownerProfileId), topic: String(topic), questions: String(questions), totalQuestions: Number(totalQuestions) }).returning();
      res.json(row);
    } catch (err) { res.status(500).json({ error: String(err) }); }
  });

  app.get("/api/flashcards", async (req, res) => {
    try {
      const { getDb } = await import("../db.js");
      const { flashcardDecks } = await import("../../drizzle/schema.js");
      const { eq, desc } = await import("drizzle-orm");
      const db = await getDb();
      const profileId = parseInt(String(req.query.profileId ?? "0"), 10);
      const rows = await db.select().from(flashcardDecks).where(eq(flashcardDecks.ownerProfileId, profileId)).orderBy(desc(flashcardDecks.createdAt));
      res.json(rows);
    } catch (err) { res.status(500).json({ error: String(err) }); }
  });

  app.post("/api/flashcards", async (req, res) => {
    try {
      const { getDb } = await import("../db.js");
      const { flashcardDecks } = await import("../../drizzle/schema.js");
      const db = await getDb();
      const { ownerProfileId = 0, topic, cards = "[]", totalCards = 0 } = req.body as Record<string, unknown>;
      const [row] = await db.insert(flashcardDecks).values({ ownerProfileId: Number(ownerProfileId), topic: String(topic), cards: String(cards), totalCards: Number(totalCards) }).returning();
      res.json(row);
    } catch (err) { res.status(500).json({ error: String(err) }); }
  });
  // ─────────────────────────────────────────────────────────────────────────

  // development mode uses Vite, production mode uses static files
  if (process.env.NODE_ENV === "development") {
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  const preferredPort = parseInt(process.env.PORT || "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using port ${port} instead`);
  }

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });
}

startServer().catch(console.error);
