# Life Agent — A Personal AI System for Turning Intentions Into Action

## 01 — Why I built it

Knowing what you should do and actually doing it are two very different problems. 

I found myself perfectly capable of creating ambitious to-do lists and detailed project plans in Notion, but consistently executing them—day after day—was a completely different challenge. 

I didn't need another generic "productivity app" or a basic to-do list. I needed a system that actively worked with me to close the gap between my intentions and my behaviors.

## 02 — Research

To understand this gap, I started reading literature on human behavior and learning. The concepts that stood out were:

- **Neuroplasticity & Learning:** Our brains adapt through repeated experience and consistent behavior patterns over time.
- **Habit Formation:** Behavior change is often driven by cues, routines, and rewards rather than pure willpower.
- **Self-monitoring:** Actively tracking behavior significantly increases the likelihood of changing it.
- **Implementation Intentions:** Specifically linking a situation or cue to an intended response drastically improves execution rates.

## 03 — Engineering hypothesis

This research led to a central engineering hypothesis:

> **Can an AI system turn behavioral observations into an adaptive feedback loop?**

What happens if a personal productivity system is designed around behavioral feedback, cues, and self-monitoring rather than just static task management?

## 04 — Architecture

Life Agent is designed as a closed-loop system:

```text
                    ┌───────────────┐
                    │   Scheduler   │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │   AI Agent    │
                    │               │
                    │ Observe       │
                    │ Reason        │
                    │ Plan          │
                    └───────┬───────┘
                            ↓
                 ┌─────────────────────┐
                 │   Action Layer      │
                 ├─────────────────────┤
                 │ Notion              │
                 │ Email               │
                 │ Notifications       │
                 └──────────┬──────────┘
                            ↓
                    ┌───────────────┐
                    │ Event Store   │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Metrics       │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Dashboard     │
                    └───────────────┘
```

## 05 — Event model

The core of Life Agent isn't the LLM—it's the event model underneath it. Every interaction is normalized into structured data representing the lifecycle of an intention:

```text
planned → started → completed
                 ↘ partial
                 ↘ forgot
                 ↘ never_started
```

By tracking tasks through these states, the system can understand what was planned, what was actually done, where friction occurred, and how to adapt future plans.

## 06 — AI loop

The system executes a continuous loop:

1. **Observe:** Reads calendar data, Notion databases, and past execution metrics.
2. **Reason:** The LLM analyzes the current state and determines optimal next steps.
3. **Plan:** Generates structured tasks and implementation intentions.
4. **Prompt:** Sends timely cues via push notifications and email.
5. **Capture:** Records task starts, completions, and inbound replies.
6. **Measure:** Calculates execution metrics (completion rates, delays).
7. **Adapt:** Feeds metrics back into the next observation phase.

## 07 — Technical implementation

The system is built entirely in Python, utilizing:
- **LLMs:** Used for reasoning, planning, and natural language processing.
- **SQLite / JSONL:** An append-only event store and normalized event model.
- **Notion API:** For human-facing planning and tracking.
- **Gmail SMTP/IMAP:** For bidirectional email communication.
- **ntfy:** For instant push notifications.
- **GitHub Actions:** For scheduling and continuous execution.
- **GitHub Pages:** For serving the static metrics dashboard.

## 08 — Dashboard

A lightweight metrics pipeline transforms the SQLite event store into static JSON data, which is then visualized via a vanilla HTML/JS/CSS dashboard on GitHub Pages. This provides a beautiful, zero-infrastructure way to visualize execution trends and behavioral feedback.

## 09 — Privacy + limitations

**This repository contains only the architecture, source code, and synthetic demonstration data.** 

All personal data (calendar events, task history, private notes) is strictly excluded. The system handles sensitive personal information in private deployments only. See [Privacy Threat Model](docs/privacy.md) for details.

*Limitation:* This is an ongoing personal engineering experiment, not a claim of scientific behavior change. The goal is to measure and observe personal execution over time.

## 10 — Research references

- Neural plasticity and behavior: [PubMed 26875778](https://pubmed.ncbi.nlm.nih.gov/26875778/)
- Digital Behavior Change Interventions: [PubMed 38787601](https://pubmed.ncbi.nlm.nih.gov/38787601/)
- Implementation Intentions: [PubMed 16536643](https://pubmed.ncbi.nlm.nih.gov/16536643/)
