# Todoist Alerts for Home Assistant

A custom Home Assistant integration that creates and manages Todoist tasks from HA automations — with deduplication, lifecycle tracking, and snooze support.

## Why

HA automations that create Todoist tasks have no dedup — calling the same action twice creates duplicate tasks. This integration solves that by tracking tasks by name and managing their full lifecycle.

## How It Works

Two automations per alert:

1. **Activate** — fires when condition is met, calls `ha_todoist_alerts.create_alert`
2. **Resolve** — fires when condition clears, calls `ha_todoist_alerts.resolve_alert`

The integration handles: dedup (one task per name), task creation/completion, external completion detection, and snooze.

```yaml
# Activate — safe to call multiple times, only one task created
- action: ha_todoist_alerts.create_alert
  data:
    name: "Washing machine done"
    content: "Collect the washing"
    priority: 2

# Resolve — closes the task in Todoist
- action: ha_todoist_alerts.resolve_alert
  data:
    name: "Washing machine done"
```

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `mcfitz2/ha-todoist-alerts` as type **Integration**
3. Install "Todoist Alerts"
4. Restart Home Assistant

### Manual

Copy `custom_components/ha_todoist_alerts/` into your HA `config/custom_components/` directory and restart.

## Setup

1. Settings → Devices & Services → Add Integration → **Todoist Alerts**
2. Enter your Todoist API token ([get it here](https://app.todoist.com/app/settings/integrations/developer))
3. Optionally set a default project ID

## Services

### `ha_todoist_alerts.create_alert`

Creates a Todoist task for the given alert name. **Idempotent** — calling multiple times with the same name creates only one open task.

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | ✓ | — | Unique alert name (dedup key) |
| `content` | ✓ | — | Todoist task title |
| `description` | | — | Task notes |
| `project_id` | | configured default | Todoist project ID |
| `priority` | | `1` | 1=normal, 2=medium, 3=high, 4=urgent |
| `labels` | | `[]` | List of label names |
| `due_string` | | — | Natural language due date, e.g. `"today"` |
| `recreate_delay_minutes` | | `30` | If task is completed externally, recreate after this many minutes. Set to `0` to disable. |

### `ha_todoist_alerts.resolve_alert`

Closes the Todoist task and removes the alert entity. Call this when the underlying condition has cleared.

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✓ | Alert name to resolve |

### `ha_todoist_alerts.snooze_alert`

Closes the Todoist task and suppresses recreation for a duration. After snooze expires the alert goes inactive — a new `create_alert` call is needed to reactivate.

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | ✓ | — | Alert name to snooze |
| `duration_minutes` | | `60` | How long to suppress |

## Sensor Entity

Each active alert creates a `sensor` entity with states:

| State | Meaning |
|-------|---------|
| `active` | Open task exists in Todoist |
| `snoozed` | Task closed, recreation suppressed |
| `inactive` | No task, not snoozed |

**Attributes:** `task_id`, `task_url`, `last_created`, `snooze_until`, `recreate_at`

## External Task Completion

If a task is completed directly in Todoist (without calling `resolve_alert`), the coordinator detects this within 5 minutes and schedules task recreation after `recreate_delay_minutes`. Set `recreate_delay_minutes: 0` to treat external completion as a permanent resolve.
