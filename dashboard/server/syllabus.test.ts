import { describe, expect, it } from "vitest";
import { normalizeExtractedAssignments } from "../shared/syllabus";

describe("normalizeExtractedAssignments", () => {
  it("keeps actionable assignments and applies safe defaults", () => {
    const result = normalizeExtractedAssignments([
      {
        title: "  Finish lab report  ",
        subject: " Biology ",
        dueDate: "Friday",
        priority: "high",
        confidence: 1.4,
      },
      { title: "", subject: "Math" },
      { title: "Read chapter 4", priority: "unexpected", confidence: -2 },
    ]);

    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({
      title: "Finish lab report",
      subject: "Biology",
      priority: "high",
      confidence: 1,
    });
    expect(result[1]).toMatchObject({
      title: "Read chapter 4",
      subject: "General",
      dueDate: "Date not specified",
      priority: "medium",
      confidence: 0,
    });
    expect(result[0]?.id).toMatch(/^syllabus-/);
  });

  it("returns an empty list for malformed model output", () => {
    expect(normalizeExtractedAssignments(null)).toEqual([]);
    expect(normalizeExtractedAssignments({ assignments: [] })).toEqual([]);
  });
});
