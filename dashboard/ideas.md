# TableTot Design Direction

## Three initial directions

### Theme Name: Editorial Study Desk
Very Brief Intro: A warm, editorial productivity workspace that turns studying into a calm ritual. It pairs a paper-like cream canvas with navy structure, coral moments of encouragement, and mint breathing room.
Probability: 0.07

### Theme Name: Library Lantern
Very Brief Intro: A quiet digital library with dark wood tones, parchment surfaces, and focused amber light. The mood is reflective and mature, with progress treated like a collection of small wins.
Probability: 0.04

### Theme Name: Garden of Small Wins
Very Brief Intro: A fresh, botanical planning space where tasks, timers, and study streaks grow like a small garden. Soft greens and sky blues create an optimistic, lightly playful learning atmosphere.
Probability: 0.03

## Chosen approach: Editorial Study Desk

### Design Movement
Contemporary editorial design with hints of Swiss information design and tactile stationery. The interface should feel like a well-made study planner translated into a responsive digital workspace.

### Core Principles
1. Make the next action obvious: every view should answer what to do now, what is coming next, and how progress is moving.
2. Use warmth without childishness: companion illustrations and coral accents should encourage students while the grid, type, and data views stay credible for parents.
3. Let calm create focus: generous whitespace, quiet surfaces, and restrained motion should reduce cognitive noise rather than compete with the timer.
4. Treat progress as a narrative: streaks, completed tasks, and focus blocks should read as evidence of momentum, not as judgment.

### Color Philosophy
Warm cream is the default canvas because it recalls paper and lowers visual intensity. Deep navy anchors navigation, headings, and high-confidence actions. Coral is reserved for moments of energy—active timer states, encouraging nudges, and completion signals. Mint is a breathing color used for healthy, supportive states such as hydration, break reminders, and positive parent insights. The ownable signature color is **TableTot Coral #E9755B**.

### Layout Paradigm
Use a persistent left rail with a generous asymmetric workspace: a strong primary action column on the left, supporting insight cards stacked on the right, and a full-width timeline or task board below. The timer should feel like the visual anchor rather than one more card in a uniform grid.

### Signature Elements
1. A small coral sun-dot motif that appears beside active focus states and section labels.
2. Tactile, paper-like cream cards with soft navy shadows rather than hard borders.
3. A compact TableTot companion mark that acts as a reassuring guide across student and parent modes.

### Interaction Philosophy
Interactions should feel like turning a page or placing a checkmark. Buttons respond quickly with a slight press scale. Completing a task gives a restrained coral-to-mint transition. Navigation changes should be immediate, while occasional companion guidance can enter with a short upward drift.

### Animation
Use 160–240ms ease-out transitions for hover, focus, and selection. Use a gentle 900ms pulse around the active Pomodoro ring, but keep the timer numerals stable. Stagger dashboard sections by 40ms on first load. Respect reduced motion by disabling non-essential transforms and pulses.

### Typography System
Headlines use **DM Serif Display** for warmth and editorial personality. Body copy, labels, metrics, and controls use **Manrope** for clarity at small sizes. Use large serif numerals for the focus timer, compact uppercase Manrope labels for metadata, and sentence-case CTAs that sound like helpful prompts.

### Brand Essence
TableTot is a calm study companion for students and their families—helping learners build consistent focus while giving parents useful visibility without surveillance. Personality adjectives: **reassuring, observant, encouraging**.

### Brand Voice
Headlines should be concise, specific, and quietly optimistic. CTAs should describe the next action instead of using generic conversion language. Microcopy should feel like a coach who notices effort.

Example lines:
- “One focused block is enough to begin.”
- “You kept the promise you made to today.”

### Wordmark & Logo
The mark is a rounded study companion silhouette that combines an open-book base, a sun-dot eye, and a small upward page corner. The wordmark should be rendered in a custom-feeling serif treatment with a coral dot replacing the “o” counter when used in large brand moments; in the app header, use the symbol plus the name rather than a default typographic lockup.

### Signature Brand Color
**TableTot Coral — #E9755B**. It signals encouragement and active momentum without the urgency of red or the synthetic energy of neon.

## Style Decisions

- Dashboard surfaces follow a tactile planner grammar: cream paper cards, soft navy shadows, ruled dividers, tab-like labels, and printed-style hierarchy.
- The focus timer is the primary visual anchor on student pages: its serif numerals are the largest numeric element, and surrounding insights support it rather than compete with it.
- TableTot Coral #E9755B functions as the sun-dot and active-momentum signal for focus states, progress, and encouragement.
