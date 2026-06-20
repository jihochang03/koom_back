/**
 * Agent Core — reusable agentic loop library.
 * Import runAgentLoop and AgentTool to build custom agents without duplicating boilerplate.
 */
import Anthropic from "@anthropic-ai/sdk";

let _client: Anthropic | null = null;
const getClient = () => {
  if (!_client) _client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  return _client;
};

// ── Public types ───────────────────────────────────────────────────────────────

export interface AgentTool {
  name: string;
  description: string;
  input_schema: object;
  execute: (input: Record<string, unknown>) => Promise<unknown>;
}

export interface AgentConfig {
  /** Claude model to use. Defaults to claude-sonnet-4-6. */
  model?: string;
  /** Max tool-call iterations. Defaults to 25. */
  maxIter?: number;
  systemPrompt: string;
  tools: AgentTool[];
  /** Called when Claude outputs a text block. */
  onText?: (text: string) => void;
  /** Called before each tool executes. */
  onToolCall?: (name: string, input: Record<string, unknown>) => void;
  /** Called after each tool returns. result is the first 300 chars. */
  onToolResult?: (name: string, result: string) => void;
  /** Called when the loop finishes naturally. */
  onDone?: () => void;
}

// ── Screenshot result type (recognised by the loop for vision content) ─────────

export interface ScreenshotResult {
  __screenshot: true;
  base64: string;
  url: string;
  label?: string;
}

export function isScreenshotResult(r: unknown): r is ScreenshotResult {
  return typeof r === "object" && r !== null && (r as ScreenshotResult).__screenshot === true;
}

// ── Core loop ──────────────────────────────────────────────────────────────────

export async function runAgentLoop(
  initialMessages: Anthropic.Messages.MessageParam[],
  config: AgentConfig
): Promise<Anthropic.Messages.MessageParam[]> {
  const { model = "claude-sonnet-4-6", maxIter = 25, systemPrompt, tools } = config;
  const { onText, onToolCall, onToolResult, onDone } = config;

  const messages: Anthropic.Messages.MessageParam[] = [...initialMessages];

  const toolMap = new Map<string, AgentTool>(tools.map(t => [t.name, t]));
  const toolDefs: Anthropic.Messages.Tool[] = tools.map(t => ({
    name: t.name,
    description: t.description,
    input_schema: t.input_schema as Anthropic.Messages.Tool["input_schema"],
  }));

  let iterations = 0;

  while (iterations++ < maxIter) {
    const response = await getClient().messages.create({
      model,
      max_tokens: 8_000,
      system: systemPrompt,
      tools: toolDefs,
      messages,
    });

    const assistantContent: Anthropic.Messages.ContentBlock[] = [];
    const toolUses: Anthropic.Messages.ToolUseBlock[] = [];

    for (const block of response.content) {
      assistantContent.push(block);
      if (block.type === "text" && block.text.trim()) onText?.(block.text.trim());
      if (block.type === "tool_use") toolUses.push(block);
    }

    messages.push({ role: "assistant", content: assistantContent });

    if (response.stop_reason === "end_turn" || toolUses.length === 0) break;

    const toolResults: Anthropic.Messages.ToolResultBlockParam[] = [];

    for (const tu of toolUses) {
      const input = tu.input as Record<string, unknown>;
      onToolCall?.(tu.name, input);

      const impl = toolMap.get(tu.name);
      if (!impl) {
        const msg = `Unknown tool: ${tu.name}`;
        onToolResult?.(tu.name, msg);
        toolResults.push({ type: "tool_result", tool_use_id: tu.id, content: msg });
        continue;
      }

      try {
        const result = await impl.execute(input);

        if (isScreenshotResult(result)) {
          const label = result.label ?? result.url;
          onToolResult?.(tu.name, `Screenshot: ${label}`);
          toolResults.push({
            type: "tool_result",
            tool_use_id: tu.id,
            content: [
              { type: "text", text: `Screenshot of: ${label}` },
              { type: "image", source: { type: "base64", media_type: "image/png", data: result.base64 } },
            ],
          });
        } else {
          const text = typeof result === "string" ? result : JSON.stringify(result);
          onToolResult?.(tu.name, text.slice(0, 300));
          toolResults.push({ type: "tool_result", tool_use_id: tu.id, content: text });
        }
      } catch (err) {
        const msg = `[error] ${err instanceof Error ? err.message : String(err)}`;
        onToolResult?.(tu.name, msg);
        toolResults.push({ type: "tool_result", tool_use_id: tu.id, content: msg, is_error: true });
      }
    }

    messages.push({ role: "user", content: toolResults });
  }

  onDone?.();
  return messages;
}
