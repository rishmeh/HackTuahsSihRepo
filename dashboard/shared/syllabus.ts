export const syllabusPriorities = ["high", "medium", "low"] as const;

export type SyllabusPriority = (typeof syllabusPriorities)[number];

export type ExtractedAssignment = {
  id: string;
  title: string;
  subject: string;
  dueDate: string;
  priority: SyllabusPriority;
  confidence: number;
};

type RawAssignment = {
  title?: unknown;
  subject?: unknown;
  dueDate?: unknown;
  priority?: unknown;
  confidence?: unknown;
};

export function normalizeExtractedAssignments(raw: unknown): ExtractedAssignment[] {
  if (!Array.isArray(raw)) return [];

  return raw
    .map((item, index) => {
      const assignment = (item && typeof item === "object" ? item : {}) as RawAssignment;
      const title = typeof assignment.title === "string" ? assignment.title.trim() : "";
      if (!title) return null;

      const priority = syllabusPriorities.includes(assignment.priority as SyllabusPriority)
        ? (assignment.priority as SyllabusPriority)
        : "medium";
      const confidenceNumber = Number(assignment.confidence);
      const confidence = Number.isFinite(confidenceNumber)
        ? Math.min(1, Math.max(0, confidenceNumber))
        : 0.65;

      return {
        id: `syllabus-${Date.now()}-${index}`,
        title: title.slice(0, 160),
        subject:
          typeof assignment.subject === "string" && assignment.subject.trim()
            ? assignment.subject.trim().slice(0, 80)
            : "General",
        dueDate:
          typeof assignment.dueDate === "string" && assignment.dueDate.trim()
            ? assignment.dueDate.trim().slice(0, 80)
            : "Date not specified",
        priority,
        confidence,
      } satisfies ExtractedAssignment;
    })
    .filter((item): item is ExtractedAssignment => Boolean(item));
}
