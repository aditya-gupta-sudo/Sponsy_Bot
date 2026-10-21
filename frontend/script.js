/*
 * Event creation and editing now use the single shared form on /events.
 * Its submission, reset, and edit-population logic lives in events.js so the
 * same controls and payload are used for both POST (create) and PUT (update).
 * Home no longer loads this legacy form-only script because Home no longer
 * contains the event form. This file is retained for compatibility with any
 * existing local reference while avoiding duplicate submit handlers.
 */
