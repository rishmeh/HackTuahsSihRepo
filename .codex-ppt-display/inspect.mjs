import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "/Users/aakash/HackTuahsSihRepo";
const source = path.join(workspace, "deck-output", "SIH2026-TableTot-Camera-Servo-Pi-FINAL-v2.pptx");
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const snapshot = await presentation.inspect({
  kind: "slide,textbox,shape,layout",
  search: "display|screen|Pi software|current build|camera and servo bridge|servo gestures|SYSTEM OUTPUTS",
  maxChars: 20000,
});
await fs.writeFile(path.join(workspace, ".codex-ppt-display", "inspect.ndjson"), snapshot.ndjson);
for (const number of [2, 3, 5, 6]) {
  const slide = presentation.slides.getItem(number - 1);
  const preview = await slide.export({format: "png", scale: 1.5});
  await fs.writeFile(path.join(workspace, ".codex-ppt-display", `slide-${number}-before.png`), new Uint8Array(await preview.arrayBuffer()));
}
