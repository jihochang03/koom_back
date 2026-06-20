import fs from "fs";
import path from "path";
import { glob } from "glob";
import type { AgentTool } from "../../core/agent-core";

const PROJECT_DIR = path.resolve(__dirname, "../../../");

export const readFileTool: AgentTool = {
  name: "read_file",
  description: "Read an existing file in this project (e.g. src/modules/shopping/apis/list-items.ts) to understand code patterns.",
  input_schema: {
    type: "object" as const,
    properties: { file_path: { type: "string" } },
    required: ["file_path"],
  },
  execute: async ({ file_path }: Record<string, unknown>): Promise<string> => {
    const full = path.resolve(PROJECT_DIR, file_path as string);
    if (!fs.existsSync(full)) return `[read_file] Not found: ${file_path}`;
    const content = fs.readFileSync(full, "utf-8");
    const lines = content.split("\n");
    return lines.length > 300
      ? lines.slice(0, 300).join("\n") + `\n... (${lines.length} lines total)`
      : content;
  },
};

export const listFilesTool: AgentTool = {
  name: "list_files",
  description: "List project files matching a glob (e.g. 'src/modules/shopping/apis/*.ts').",
  input_schema: {
    type: "object" as const,
    properties: { pattern: { type: "string" } },
    required: ["pattern"],
  },
  execute: async ({ pattern }: Record<string, unknown>): Promise<string> => {
    const files = await glob(pattern as string, { cwd: PROJECT_DIR, nodir: true });
    return files.length === 0 ? "[list_files] No files found" : files.join("\n");
  },
};

export const writeFileTool: AgentTool = {
  name: "write_file",
  description: "Write the generated handler code to a file.",
  input_schema: {
    type: "object" as const,
    properties: {
      file_path: { type: "string" },
      content: { type: "string" },
    },
    required: ["file_path", "content"],
  },
  execute: async ({ file_path, content }: Record<string, unknown>): Promise<string> => {
    const full = path.resolve(PROJECT_DIR, file_path as string);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, content as string, "utf-8");
    return `[write_file] Written: ${file_path} (${(content as string).split("\n").length} lines)`;
  },
};

export const PROJECT_ROOT = PROJECT_DIR;
export const allFileTools: AgentTool[] = [readFileTool, listFilesTool, writeFileTool];
