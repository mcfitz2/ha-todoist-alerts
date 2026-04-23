"""Constants for the Todoist Alerts integration."""

DOMAIN = "ha_todoist_alerts"

CONF_API_TOKEN = "api_token"
CONF_DEFAULT_PROJECT_ID = "default_project_id"

TODOIST_API_BASE = "https://api.todoist.com/rest/v2"

ALERT_STATE_ACTIVE = "active"
ALERT_STATE_INACTIVE = "inactive"
ALERT_STATE_SNOOZED = "snoozed"

ATTR_TASK_ID = "task_id"
ATTR_TASK_URL = "task_url"
ATTR_LAST_CREATED = "last_created"
ATTR_SNOOZE_UNTIL = "snooze_until"
ATTR_RECREATE_AT = "recreate_at"

STORAGE_KEY = f"{DOMAIN}.storage"
STORAGE_VERSION = 1

POLL_INTERVAL_SECONDS = 300  # 5 minutes

SERVICE_CREATE_ALERT = "create_alert"
SERVICE_RESOLVE_ALERT = "resolve_alert"
SERVICE_SNOOZE_ALERT = "snooze_alert"
