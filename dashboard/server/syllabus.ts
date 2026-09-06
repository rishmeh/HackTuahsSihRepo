import { PDFParse } from "pdf-parse";
import { invokeLLM } from "./_core/llm";
import { storagePut } from "./storage";
import { normalizeExtractedAssignments, type ExtractedAssignment } from "../shared/syllabus";

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_TEXT_CHARS = 120_000;

function cleanFileName(fileName: string) {
  return fileName.replace(/[^a-z0-9._-]/gi, "-").slice(0, 120) || "syllabus";
}

export async function extractSyllabusText(buffer: Buffer, mimeType: string) {
  if (mimeType === "application/pdf" || mimeType.endsWith("/pdf")) {
    const parser = new PDFParse({ data: buffer });
    try {
      const result = await parser.getText();
      return result.text.trim().slice(0, MAX_TEXT_CHARS);
    } finally {
      await parser.destroy();
    }
  }

  return buffer.toString("utf8").trim().slice(0, MAX_TEXT_CHARS);
}

export async function extractAssignmentsFromSyllabus(input: {
  fileName: string;
  mimeType: string;
  fileBase64: string;
}): Promise<{ assignments: ExtractedAssignment[]; sourceUrl: string; sourceFileName: string }> {
  const buffer = Buffer.from(input.fileBase64, "base64");
  if (!buffer.length) throw new Error("The uploaded syllabus is empty.");
  if (buffer.length > MAX_FILE_BYTES) throw new Error("Please upload a syllabus smaller than 5 MB.");

  const sourceFileName = cleanFileName(input.fileName);
  const stored = await storagePut(
    `tabletot/syllabi/${Date.now()}-${sourceFileName}`,
    buffer,
    input.mimeType || "application/octet-stream",
  );
  const text = await extractSyllabusText(buffer, input.mimeType || "text/plain");
  if (text.length < 20) throw new Error("I could not find enough readable text in that file.");

  const response = await invokeLLM({
    model: "gpt-5-mini",
    messages: [
      {
        role: "system",
        content:
          "You extract actionable student assignments from syllabi. Return only assignments that a student can act on. Never invent a due date; use Date not specified when the syllabus is ambiguous. Keep titles short, preserve subject names, infer priority only from explicit urgency or due-date signals, and set confidence from 0 to 1 based on evidence in the text.",
      },
      {
        role: "user",
        content: `Extract assignments from this syllabus text. Focus on homework, projects, readings, exams, labs, presentations, and practice tasks.\n\nSOURCE FILE: ${sourceFileName}\n\nSYLLABUS TEXT:\n${text}`,
      },
    ],
    reasoning: { effort: "low" },
    response_format: {
      type: "json_schema",
      json_schema: {
        name: "syllabus_assignments",
        strict: true,
        schema: {
          type: "object",
          properties: {
            assignments: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  title: { type: "string" },
                  subject: { type: "string" },
                  dueDate: { type: "string" },
                  priority: { type: "string", enum: ["high", "medium", "low"] },
                  confidence: { type: "number" },
                },
                required: ["title", "subject", "dueDate", "priority", "confidence"],
                additionalProperties: false,
              },
            },
          },
          required: ["assignments"],
          additionalProperties: false,
        },
      },
    },
  });

  const content = response.choices[0]?.message?.content;
  if (typeof content !== "string") throw new Error("The AI response did not contain assignment data.");
  const parsed = JSON.parse(content) as { assignments?: unknown };
  return {
    assignments: normalizeExtractedAssignments(parsed.assignments),
    sourceUrl: stored.url,
    sourceFileName,
  };
}
