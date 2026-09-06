/**
 * One illustrated scene: photo, story, question, four answers.
 *
 * Purely presentational. It does not know which answer is "right" because
 * there isn't one — every choice is accepted the same way.
 */
import { motion } from "framer-motion";
import type { SceneArt } from "./scenes";

export type SceneOption = { key: "A" | "B" | "C" | "D"; text: string };

export type SceneCardProps = {
  art: SceneArt;
  title: string;
  text: string;
  question: string;
  options: SceneOption[];
  picked?: SceneOption["key"];
  onPick: (key: SceneOption["key"]) => void;
};

export function SceneHero({ art, title }: { art: SceneArt; title?: string }) {
  return (
    <div className="onb-hero">
      <img src={art.image} alt="" loading="eager" decoding="async" />
      <div className="onb-hero-caption">{title ?? art.caption}</div>
    </div>
  );
}

export default function SceneCard({ art, title, text, question, options, picked, onPick }: SceneCardProps) {
  return (
    <motion.section
      className="onb-card"
      initial={{ opacity: 0, y: 18, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -14, scale: 0.985 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      aria-live="polite"
    >
      <SceneHero art={art} title={title} />
      <div className="onb-body">
        <p className="onb-story">{text}</p>
        <h1 className="onb-question">{question}</h1>
        <div className="onb-options" role="radiogroup" aria-label={question}>
          {options.map((option) => {
            const isPicked = picked === option.key;
            return (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={isPicked}
                className={isPicked ? "onb-option onb-option--picked" : "onb-option"}
                onClick={() => onPick(option.key)}
              >
                <span className={`onb-letter onb-letter--${art.accent}`}>{option.key}</span>
                <span>{option.text}</span>
              </button>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
