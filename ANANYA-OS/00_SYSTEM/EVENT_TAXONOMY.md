# Event Taxonomy

This document maps event data in the system to the Ananya OS taxonomy.

## Focus Events

Focus events (recorded by `pomodoro_app`) track focused work sessions.

| Event Type | Taxonomy Mapping | Rationale |
| :--- | :--- | :--- |
| `focus_started` | `EXECUTION:SESSION_STARTED` | Marking the beginning of a focus period. |
| `focus_completed` | `EXECUTION:SESSION_COMPLETED` | Successfully finishing a focus period. |
| `focus_abandoned` | `EXECUTION:SESSION_ABANDONED` | Ending a focus period prematurely. |
