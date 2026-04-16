/**
 * Mirror Logger Extension
 *
 * Integra o pi com o sistema de memória do Espelho (memoria).
 *
 * Eventos tratados:
 * - session_start        → unmute + fecha órfãs + extrai pendentes
 * - before_agent_start   → persiste session id + loga prompt do usuário
 * - agent_end            → loga resposta do assistente (todas as mensagens do turno)
 * - session_shutdown     → fecha conversa + backup do banco
 *
 * Toda lógica pesada fica no CLI Python. Esta extensão é um dispatcher fino.
 * Falhas são engolidas para nunca travar o pi — mas logadas em ~/.espelho/mirror-logger.log.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const ESPELHO_DIR = join(homedir(), ".espelho");
const CURRENT_SESSION_FILE = join(ESPELHO_DIR, "current_session");
const LOG_FILE = join(ESPELHO_DIR, "mirror-logger.log");

// Limite de tamanho de conteúdo para argumentos CLI (~50KB, seguro para macOS ARG_MAX)
const MAX_CONTENT_SIZE = 50_000;

export default function (pi: ExtensionAPI) {
	// --- Helpers ---

	function log(level: string, msg: string): void {
		try {
			const ts = new Date().toISOString();
			mkdirSync(ESPELHO_DIR, { recursive: true });
			appendFileSync(LOG_FILE, `${ts} [${level}] ${msg}\n`);
		} catch {
			// Logging failure must never break anything
		}
	}

	async function runPy(args: string[]): Promise<string> {
		try {
			const result = await pi.exec("uv", ["run", "python3", ...args], {
				timeout: 30_000,
			});
			const stderr = (result?.stderr ?? "").trim();
			if (stderr) {
				log("WARN", `stderr from [${args.slice(0, 3).join(" ")}]: ${stderr.slice(0, 500)}`);
			}
			return (result?.stdout ?? "").trim();
		} catch (err: unknown) {
			const message = err instanceof Error ? err.message : String(err);
			log("ERROR", `runPy failed [${args.slice(0, 3).join(" ")}]: ${message.slice(0, 500)}`);
			return "";
		}
	}

	function writeCurrentSession(sessionId: string): void {
		try {
			mkdirSync(ESPELHO_DIR, { recursive: true });
			writeFileSync(CURRENT_SESSION_FILE, sessionId);
		} catch {
			// ignore
		}
	}

	/** Extrai texto legível de um array de content blocks ou string. */
	function extractText(content: unknown): string {
		if (typeof content === "string") return content;
		if (!Array.isArray(content)) return "";
		return content
			.filter((b: Record<string, unknown>) => b && b.type === "text" && typeof b.text === "string")
			.map((b: Record<string, unknown>) => b.text as string)
			.join("\n");
	}

	/** Trunca conteúdo para caber em args CLI. */
	function truncate(text: string): string {
		if (text.length <= MAX_CONTENT_SIZE) return text;
		return text.slice(0, MAX_CONTENT_SIZE) + "\n[… truncado]";
	}

	// --- 1. session_start → unmute + fecha órfãs + extrai pendentes ---

	pi.on("session_start", async (_event, ctx) => {
		log("INFO", "session_start fired");
		const summary = await runPy(["-m", "memoria.conversation_logger", "session-start"]);
		log("INFO", `session-start result: ${summary || "(empty)"}`);
		if (ctx.hasUI) {
			if (summary) {
				ctx.ui.notify(summary, "info");
			}
			ctx.ui.setStatus("mirror", summary || "Memória pronta");
		}
	});

	// --- 2. before_agent_start → persiste session + loga prompt do usuário ---

	pi.on("before_agent_start", async (event, ctx) => {
		const sessionId = ctx.sessionManager.getSessionFile() ?? null;
		if (!sessionId) return;

		writeCurrentSession(sessionId);

		const prompt = event.prompt ?? "";
		if (!prompt || prompt.startsWith("/")) return;

		log("INFO", `log-user: ${prompt.slice(0, 80)}...`);
		await runPy([
			"-m",
			"memoria.conversation_logger",
			"log-user",
			sessionId,
			truncate(prompt),
			"--interface",
			"pi",
		]);
	});

	// --- 3. agent_end → loga resposta do assistente ---
	//
	// agent_end dispara uma vez por prompt do usuário, com TODAS as mensagens
	// do ciclo (assistente + tool calls + tool results). Extraímos apenas o
	// texto do assistente e logamos como uma única mensagem consolidada.

	pi.on("agent_end", async (event, ctx) => {
		const sessionId = ctx.sessionManager.getSessionFile() ?? null;
		if (!sessionId) return;

		const messages = (event as Record<string, unknown>).messages;
		if (!Array.isArray(messages) || messages.length === 0) return;

		const assistantTexts: string[] = [];
		for (const msg of messages) {
			if (
				msg &&
				typeof msg === "object" &&
				"role" in msg &&
				(msg as Record<string, unknown>).role === "assistant"
			) {
				const text = extractText((msg as Record<string, unknown>).content);
				if (text.trim()) {
					assistantTexts.push(text);
				}
			}
		}

		if (assistantTexts.length === 0) return;

		log("INFO", `log-assistant: ${assistantTexts.length} block(s), ${assistantTexts.join("").length} chars`);

		// Consolida todas as mensagens de assistente do turno em uma única entrada
		const combined = assistantTexts.join("\n\n---\n\n");
		const content = truncate(combined);

		await runPy([
			"-m",
			"memoria.conversation_logger",
			"log-assistant",
			sessionId,
			content,
			"--interface",
			"pi",
		]);
	});

	// --- 4. session_shutdown → fecha conversa + backup ---
	//
	// Usa extract=False porque extração chama LLM e pode demorar 30s+.
	// A extração acontece no session_start da próxima sessão via extract_pending.

	pi.on("session_shutdown", async (_event, ctx) => {
		const sessionId = ctx.sessionManager.getSessionFile() ?? null;

		if (sessionId) {
			const escaped = sessionId.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
			await runPy([
				"-c",
				`from memoria.conversation_logger import end_session; end_session('${escaped}', extract=False)`,
			]);
			log("INFO", `session closed: ${sessionId}`);
		}

		await runPy(["-m", "memoria.backup", "--silent"]);
	});
}
