/**
 * Speak Mode starter templates.
 *
 * Each template pre-fills the "prepare" textarea with a realistic outline the user
 * then edits. The LLM turns whatever's in the box into staged, prioritized points —
 * so these are just fast on-ramps for the most common speaking situations.
 *
 * Keep this file in sync with chrome-extension/src/lib/speak-templates.ts.
 */

export interface SpeakTemplate {
  id: string;
  label: string;
  emoji: string;
  hint: string;
  body: string;
}

export const SPEAK_TEMPLATES: SpeakTemplate[] = [
  {
    id: "standup",
    label: "Team standup",
    emoji: "🧑‍💻",
    hint: "Daily / weekly sync",
    body: `Intro
- Quick hello, one-line focus for the week

Updates (must)
- What shipped since last time
- What I'm working on now
- Any blockers I need help with

Decisions needed
- Decision 1 we need to make today
- Owner + deadline for the top action item

Close
- Confirm next steps and who owns what`,
  },
  {
    id: "pitch",
    label: "Sales / pitch",
    emoji: "📈",
    hint: "Client or investor",
    body: `Open
- Who we are in one sentence
- The problem we solve (must)

The solution (must)
- What the product does
- The one metric that proves it works
- Why now / why us

Proof
- A customer result or case study
- Pricing and what's included

Close (must)
- The specific next step I'm asking for
- Timeline and follow-up`,
  },
  {
    id: "interview",
    label: "Interview",
    emoji: "🎙️",
    hint: "Screen or panel",
    body: `Intro
- Warm hello, thank them for their time

Questions to ask (must)
- Tell me about your experience with X
- Walk me through a hard problem you solved
- How do you handle disagreement on a team
- What are you looking for in your next role

Wrap
- Explain next steps in the process
- Ask if they have questions for me`,
  },
  {
    id: "one_on_one",
    label: "1:1 meeting",
    emoji: "🤝",
    hint: "Manager / report",
    body: `Check-in
- How are things going, honestly

Their agenda (must)
- What's on your mind this week
- Anything blocking you

My agenda
- Feedback: one thing going well, one thing to improve
- Priorities for the next two weeks (must)

Growth
- Progress on your development goal

Close
- Agree on action items and owners`,
  },
  {
    id: "demo",
    label: "Product demo",
    emoji: "🖥️",
    hint: "Walkthrough",
    body: `Set the stage
- Who this is for and the problem it solves (must)

The walkthrough (must)
- Feature 1: the core workflow
- Feature 2: the "wow" moment
- Feature 3: how it fits their tools

Handle it
- Answer the top objection up front
- Pricing / availability

Close (must)
- The next step (trial, pilot, follow-up call)`,
  },
  {
    id: "sermon",
    label: "Talk / sermon",
    emoji: "🎤",
    hint: "Message or keynote",
    body: `Opening
- Hook: a story or question that grabs attention

Main message (must)
- Core idea in one sentence
- Point 1 with a supporting example
- Point 2 with a supporting example
- Point 3 with a supporting example

Application (must)
- The one thing I want people to do this week

Close
- Restate the core idea
- Final thought to leave them with`,
  },
];
