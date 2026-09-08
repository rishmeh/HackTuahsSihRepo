import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "/Users/aakash/HackTuahsSihRepo";
const buildDir = path.join(workspaceDir, ".codex-ppt-display");
const stagingDir = path.join(workspaceDir, ".codex-finalizer-display");
const sourcePath = path.join(workspaceDir, "deck-output", "SIH2026-TableTot-Camera-Servo-Pi-FINAL-v2.pptx");
const finalPath = path.join(workspaceDir, "deck-output", "SIH2026-TableTot-Camera-Display-Servos-FINAL.pptx");
const skillDir = "/Users/aakash/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations";
const pythonExecutable = "/Users/aakash/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";

const presentation = await PresentationFile.importPptx(await FileBlob.load(sourcePath));
const replacements = [
  ["sh/94n2hobe", "with a Raspberry Pi camera and two servos.", "with a Raspberry Pi camera, IPS face display and two servos."],
  ["sh/vy9on2hk", "plus expressive servo gestures", "plus an animated face and servo gestures"],
  ["sh/wry9wfi9", "Laptop dashboard and robot status", "Animated face on the Pi IPS display"],
  ["sh/wzux0ni9", "Laptop  compute, mic, speaker and screen", "Laptop  compute, microphone and speaker"],
  ["sh/wzux0ni9", "Raspberry Pi 5  camera and servo bridge", "Raspberry Pi 5  camera, display and servo bridge"],
  ["sh/wzux0ni9", "Pi software  camera capture and PWM only", "Pi software  camera, face renderer and PWM"],
  ["sh/wzux0ni9", "Current build  no PIR or Pi audio/display", "Current build  no PIR or Pi audio"],
  ["sh/i1cf2x0f", "Laptop screen  dashboard and robot status", "Pygame  face renderer on Raspberry Pi"],
  ["sh/1cvqxoza", "Laptop screen", "Pi IPS display"],
  ["sh/1cvqxoza", "dashboard + robot status", "animated face + status"],
  ["sh/epk7mtgz", "local UI", "face state"],
  ["sh/4n29gj2x", "robot state, camera and servo health", "robot state, camera, display and servo health"],
];

for (const [id, oldText, newText] of replacements) {
  const target = presentation.resolve(id);
  const before = target.text.toString();
  if (!before.includes(oldText)) throw new Error(`Missing expected text in ${id}: ${oldText}`);
  target.text.replace(oldText, newText);
}

for (const number of [2, 3, 5, 6]) {
  const slide = presentation.slides.getItem(number - 1);
  const preview = await slide.export({format: "png", scale: 1.5});
  await fs.writeFile(path.join(buildDir, `slide-${number}-after.png`), new Uint8Array(await preview.arrayBuffer()));
  const layout = await slide.export({format: "layout"});
  await fs.writeFile(path.join(buildDir, `slide-${number}-after.layout.json`), await layout.text());
}
const montage = await presentation.export({format: "webp", montage: true, scale: 1});
await fs.writeFile(path.join(buildDir, "montage-after.webp"), new Uint8Array(await montage.arrayBuffer()));

await fs.mkdir(stagingDir, {recursive: true});
const candidatePath = path.join(stagingDir, "candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const {finalizePresentation} = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const result = await finalizePresentation({
  explicitTotalSlideCount: 9,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  fontPolicy: {
    basis: "reference",
    families: ["Arial", "Calibri", "Garamond", "Oswald", "Times New Roman"],
    referencePath: sourcePath,
    referenceSha256: "17d38cfee0c1954d0f0d11ec7d87970800eaf77354d9eddc1143fe12a350ff86",
  },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "SIH2026-TableTot-Camera-Display-Servos-FINAL.validation.json"),
});
process.stdout.write(JSON.stringify(result, null, 2));
