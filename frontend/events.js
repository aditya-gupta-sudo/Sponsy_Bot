
const API_URL = "/api/events";

const tableBody = document.getElementById("eventsTableBody");
const eventsMessage = document.getElementById("eventsMessage");

const totalEventsElement = document.getElementById("totalEvents");
const pastEventsElement = document.getElementById("pastEventsCount");
const upcomingEventsElement = document.getElementById("upcomingEventsCount");

const filterButtons = document.querySelectorAll(".event-tab");
const eventSearchInput = document.getElementById("eventSearch");
const eventTypeFilter = document.getElementById("eventTypeFilter");
const eventSortSelect = document.getElementById("eventSort");

const eventForm = document.getElementById("eventForm");
const eventResult = document.getElementById("eventResult");
const eventFormTitle = document.getElementById("eventFormTitle");
const eventFormDescription = document.getElementById("eventFormDescription");
const eventFormTag = document.getElementById("eventFormTag");
const eventFormSubmit = document.getElementById("eventFormSubmit");
const cancelEditButton = document.getElementById("cancelEditButton");

const reviewSection = document.getElementById("sponsorReviewSection");
const reviewTitle = document.getElementById("sponsorReviewTitle");
const reviewMessage = document.getElementById("sponsorReviewMessage");
const candidatesContainer = document.getElementById("sponsorCandidates");
const runDiscoveryButton = document.getElementById("runDiscoveryButton");

let allEvents = [];
let currentFilter = "all";
let editingEvent = null;
const sponsorCountByEvent = new Map();
const progressByEvent = new Map();
let sponsorCountsLoading = false;
let activeSponsorEvent = null;

function getTodayString() {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function formatDate(value) {
    if (!value) return "Not specified";

    const parts = String(value).slice(0, 10).split("-");

    if (parts.length !== 3 || parts.some(part => !part)) {
        return "Invalid date";
    }

    const [year, month, day] = parts.map(Number);
    const date = new Date(year, month - 1, day);

    if (
        date.getFullYear() !== year ||
        date.getMonth() !== month - 1 ||
        date.getDate() !== day
    ) {
        return "Invalid date";
    }

    return date.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
    });
}

function isPastEvent(event) {
    return String(event.event_date).slice(0, 10) < getTodayString();
}

function updateStatistics() {
    const pastCount = allEvents.filter(isPastEvent).length;

    totalEventsElement.textContent = allEvents.length;
    pastEventsElement.textContent = pastCount;
    upcomingEventsElement.textContent = allEvents.length - pastCount;
}

function addCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value ?? "—";
    row.appendChild(cell);
    return cell;
}

function createButton(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
}

function eventSearchText(event) {
    return [
        event.event_name,
        event.college,
        event.city,
        event.state,
        event.event_type,
        event.event_date,
        event.expected_participants,
        event.event_id
    ].filter(value => value !== null && value !== undefined)
        .join(" ")
        .toLocaleLowerCase();
}

function compareEventDates(a, b) {
    const dateA = String(a.event_date || "9999-12-31").slice(0, 10);
    const dateB = String(b.event_date || "9999-12-31").slice(0, 10);
    return dateA.localeCompare(dateB);
}

function sortEvents(events) {
    const sortBy = eventSortSelect?.value || "upcoming-first";
    const sorted = [...events];

    sorted.sort((a, b) => {
        if (sortBy === "date-asc") return compareEventDates(a, b);
        if (sortBy === "date-desc") return compareEventDates(b, a);
        if (sortBy === "participants-desc") {
            return Number(b.expected_participants || 0) - Number(a.expected_participants || 0)
                || compareEventDates(a, b);
        }
        if (sortBy === "name-asc") {
            return String(a.event_name || "").localeCompare(String(b.event_name || ""));
        }
        if (sortBy === "newest") {
            return Number(b.event_id || 0) - Number(a.event_id || 0);
        }
        if (sortBy === "sponsors-desc") {
            const countA = sponsorCountByEvent.get(String(a.event_id));
            const countB = sponsorCountByEvent.get(String(b.event_id));
            // Keep events whose counts have not loaded yet at the bottom.
            const scoreA = Number.isFinite(countA) ? countA : -1;
            const scoreB = Number.isFinite(countB) ? countB : -1;
            return scoreB - scoreA || compareEventDates(a, b);
        }

        // Default: future/today events first, earliest future date first;
        // past events follow with the most recent past date first.
        const pastA = isPastEvent(a);
        const pastB = isPastEvent(b);
        if (pastA !== pastB) return pastA ? 1 : -1;
        return pastA ? compareEventDates(b, a) : compareEventDates(a, b);
    });

    return sorted;
}

function renderProgressCell(cell, event) {
    const progress = progressByEvent.get(String(event.event_id)) || {};
    const steps = [
        { key: "details_complete", label: "Details", done: Boolean(Number(progress.details_complete)) },
        { key: "sponsor_count", label: "Sponsors", done: Number(progress.sponsor_count || 0) > 0 },
        { key: "selected_sponsor_count", label: "Selected", done: Number(progress.selected_sponsor_count || 0) > 0 },
        { key: "contact_count", label: "Contacts", done: Number(progress.contact_count || 0) > 0 },
        { key: "email_count", label: "Draft", done: Number(progress.email_count || 0) > 0 },
        { key: "sent_email_count", label: "Sent", done: Number(progress.sent_email_count || 0) > 0 }
    ];
    const nextIndex = steps.findIndex(step => !step.done);
    const wrapper = document.createElement("div");
    wrapper.className = "event-workflow-progress";
    wrapper.setAttribute("aria-label", "Event workflow progress");
    for (let index = 0; index < steps.length; index += 1) {
        const step = steps[index];
        const item = document.createElement("span");
        item.className = "workflow-step" + (step.done ? " is-complete" : index === nextIndex ? " is-next" : " is-pending");
        item.title = step.done ? `${step.label}: completed` : index === nextIndex ? `${step.label}: next step` : `${step.label}: pending`;
        item.textContent = step.done ? `✓ ${step.label}` : step.label;
        wrapper.appendChild(item);
    }
    const completed = steps.filter(step => step.done).length;
    const summary = document.createElement("small");
    summary.className = "workflow-summary";
    summary.textContent = `${completed}/${steps.length} steps`;
    wrapper.appendChild(summary);
    cell.replaceChildren(wrapper);
}

async function loadEventProgress({ render = true } = {}) {
    try {
        const response = await fetch("/api/event-progress", { headers: { "Accept": "application/json" } });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        progressByEvent.clear();
        sponsorCountByEvent.clear();
        for (const item of data.progress || []) {
            progressByEvent.set(String(item.event_id), item);
            sponsorCountByEvent.set(String(item.event_id), Number(item.sponsor_count || 0));
        }
        sponsorCountsLoading = false;
        if (render) renderEvents();
    } catch (error) {
        console.warn("Event progress could not be refreshed:", error);
    }
}

function renderEvents() {
    tableBody.replaceChildren();

    const query = (eventSearchInput?.value || "").trim().toLocaleLowerCase();
    const selectedType = eventTypeFilter?.value || "all";

    const filtered = allEvents.filter(event => {
        if (currentFilter === "past" && !isPastEvent(event)) return false;
        if (currentFilter === "upcoming" && isPastEvent(event)) return false;
        if (selectedType !== "all" && String(event.event_type || "") !== selectedType) return false;
        if (query && !eventSearchText(event).includes(query)) return false;
        return true;
    });

    const sorted = sortEvents(filtered);

    if (sorted.length === 0) {
        eventsMessage.textContent = allEvents.length === 0
            ? "No events found. Use the form above to create your first event."
            : "No events match your current search and filters.";
        return;
    }

    eventsMessage.textContent = `Showing ${sorted.length} of ${allEvents.length} event(s).`;

    for (const event of sorted) {
        const row = document.createElement("tr");

        addCell(row, event.event_id);
        addCell(row, event.event_name);
        addCell(row, formatDate(event.event_date));
        addCell(row, event.expected_participants == null ? "—" : Number(event.expected_participants).toLocaleString("en-IN"));

        const sponsorCount = sponsorCountByEvent.get(String(event.event_id));
        const countLabel = Number.isFinite(sponsorCount)
            ? sponsorCount.toLocaleString("en-IN")
            : sponsorCountsLoading
                ? "Loading…"
                : "—";
        addCell(row, countLabel);

        const progressCell = addCell(row, "");
        renderProgressCell(progressCell, event);

        const detailsCell = addCell(row, "");
        detailsCell.appendChild(
            createButton(
                "View / Edit",
                "button button-secondary",
                () => openEditForm(event.event_id)
            )
        );

        const sponsorCell = addCell(row, "");
        sponsorCell.appendChild(
            createButton(
                "View Sponsors",
                "button button-primary",
                () => { window.location.href = `/pipeline?event_id=${encodeURIComponent(event.event_id)}`; }
            )
        );

        tableBody.appendChild(row);
    }
}

async function loadSponsorCandidateCounts(events) {
    sponsorCountsLoading = true;
    for (const event of events) {
        sponsorCountByEvent.set(String(event.event_id), null);
    }
    renderEvents();

    // Limit concurrent calls so a workspace with many events does not flood the API.
    const batchSize = 4;
    for (let start = 0; start < events.length; start += batchSize) {
        const batch = events.slice(start, start + batchSize);
        await Promise.all(batch.map(async event => {
            try {
                const response = await fetch(
                    `${API_URL}/${event.event_id}/candidates`
                );
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                const count = Number.isFinite(Number(data.candidate_count))
                    ? Number(data.candidate_count)
                    : Array.isArray(data.candidates)
                        ? data.candidates.length
                        : null;
                sponsorCountByEvent.set(String(event.event_id), count);
            } catch (error) {
                console.warn(`Could not load sponsor count for event ${event.event_id}:`, error);
                sponsorCountByEvent.set(String(event.event_id), null);
            }
        }));
    }

    sponsorCountsLoading = false;
    renderEvents();
}

function parseArray(value) {
    if (Array.isArray(value)) return value;

    if (typeof value === "string" && value.trim()) {
        try {
            const parsed = JSON.parse(value);
            if (Array.isArray(parsed)) return parsed;
        } catch {
            // Stored values can also be comma-separated strings.
        }

        return value.split(",").map(item => item.trim()).filter(Boolean);
    }

    return [];
}

function getCheckedValues(name) {
    return Array.from(
        eventForm.querySelectorAll(`input[name="${name}"]:checked`)
    ).map(checkbox => checkbox.value);
}

function buildEventPayload() {
    return {
        event_name: document.getElementById("eventName").value.trim(),
        college: document.getElementById("college").value.trim(),
        city: document.getElementById("city").value.trim(),
        state: document.getElementById("state").value.trim(),
        event_date: document.getElementById("eventDate").value,
        expected_participants: Number(document.getElementById("participants").value),
        event_type: document.getElementById("eventType").value,
        description: document.getElementById("description").value.trim(),
        sponsorship_requirements: getCheckedValues("sponsorship"),
        age_groups: getCheckedValues("age_groups"),
        audience_types: getCheckedValues("audience_types"),
        interests: getCheckedValues("interests"),
        geographic_reach: document.getElementById("geographicReach").value || null,
        spending_profile: document.getElementById("spendingProfile").value,
        event_format: document.getElementById("eventFormat").value || null
    };
}

function setCreateMode({ clearForm = false, clearMessage = true } = {}) {
    editingEvent = null;
    if (clearForm) eventForm.reset();

    eventFormTitle.textContent = "Create an Event";
    eventFormDescription.textContent = "Enter your details to begin finding sponsors.";
    eventFormTag.textContent = "EVENT SETUP";
    eventFormSubmit.innerHTML = 'Create Event <span>→</span>';
    cancelEditButton.hidden = true;

    if (clearMessage) {
        eventResult.textContent = "";
        eventResult.className = "";
    }
}

function populateEventForm(eventData) {
    const fields = {
        eventName: eventData.event_name,
        college: eventData.college,
        city: eventData.city,
        state: eventData.state,
        eventDate: eventData.event_date ? String(eventData.event_date).slice(0, 10) : "",
        participants: eventData.expected_participants,
        eventType: eventData.event_type,
        description: eventData.description,
        geographicReach: eventData.geographic_reach,
        spendingProfile: eventData.spending_profile || "unknown",
        eventFormat: eventData.event_format
    };

    for (const [id, value] of Object.entries(fields)) {
        const field = document.getElementById(id);
        if (!field) continue;

        // The original form represents unknown reach/format with an empty option.
        if ((id === "geographicReach" || id === "eventFormat") &&
            (value == null || value === "Unknown" || value === "unknown")) {
            field.value = "";
        } else {
            field.value = value == null ? "" : String(value);
        }
    }

    const checkboxFields = {
        sponsorship: eventData.sponsorship_requirements,
        age_groups: eventData.age_groups,
        audience_types: eventData.audience_types,
        interests: eventData.interests
    };

    for (const [name, rawValues] of Object.entries(checkboxFields)) {
        const selectedValues = parseArray(rawValues);
        eventForm.querySelectorAll(`input[name="${name}"]`).forEach(checkbox => {
            checkbox.checked = selectedValues.includes(checkbox.value);
        });
    }
}

async function openEditForm(eventId) {
    setCreateMode({ clearForm: true, clearMessage: false });
    eventResult.textContent = "Loading event details...";
    eventResult.className = "";
    eventFormSubmit.disabled = true;

    try {
        const response = await fetch(`${API_URL}/${eventId}`);
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            const detail = Array.isArray(data.detail)
                ? data.detail.map(item => `${item.loc?.join(".") || "field"}: ${item.msg}`).join("; ")
                : data.detail || `HTTP ${response.status}`;
            throw new Error(detail);
        }

        if (!data.event) throw new Error("The server did not return the requested event.");

        editingEvent = data.event;
        populateEventForm(editingEvent);
        eventFormTitle.textContent = `Edit Event #${editingEvent.event_id}`;
        eventFormDescription.textContent = "Update the event using the same controls used to create it.";
        eventFormTag.textContent = "EDIT EVENT";
        eventFormSubmit.innerHTML = 'Save Changes <span>→</span>';
        cancelEditButton.hidden = false;
        eventResult.textContent = "Editing mode: review the selected dropdowns and checkboxes, then save.";
        eventForm.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        console.error("Failed to load event:", error);
        setCreateMode({ clearForm: true, clearMessage: false });
        eventResult.textContent = `Could not load event details: ${error.message}`;
        eventResult.className = "error";
    } finally {
        eventFormSubmit.disabled = false;
    }
}

cancelEditButton.addEventListener("click", () => {
    setCreateMode({ clearForm: true, clearMessage: true });
    eventForm.scrollIntoView({ behavior: "smooth", block: "start" });
});

eventForm.addEventListener("submit", async event => {
    event.preventDefault();

    const wasEditing = Boolean(editingEvent);
    const eventId = wasEditing ? editingEvent.event_id : null;
    const payload = buildEventPayload();
    const url = wasEditing
        ? `${API_URL}/${eventId}`
        : `/events`;

    eventFormSubmit.disabled = true;
    cancelEditButton.disabled = true;
    eventResult.textContent = wasEditing ? "Saving event changes..." : "Creating event...";
    eventResult.className = "";

    try {
        const response = await fetch(url, {
            method: wasEditing ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));

        if (!response.ok) {
            const detail = Array.isArray(result.detail)
                ? result.detail.map(item => `${item.loc?.join(".") || "field"}: ${item.msg}`).join("; ")
                : result.detail || `HTTP ${response.status}`;
            throw new Error(detail);
        }

        const savedId = result.event_id ?? eventId;
        eventForm.reset();
        setCreateMode({ clearForm: false, clearMessage: false });
        await loadEvents();
        eventResult.textContent = wasEditing
            ? `Event "${payload.event_name}" updated successfully.`
            : `Event "${payload.event_name}" saved successfully. Event ID: ${savedId}`;
        eventResult.className = "success";
        eventForm.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        console.error(wasEditing ? "Event update failed:" : "Event creation failed:", error);
        eventResult.textContent = `${wasEditing ? "Update" : "Create"} failed: ${error.message}`;
        eventResult.className = "error";
    } finally {
        eventFormSubmit.disabled = false;
        cancelEditButton.disabled = false;
    }
});

function addText(card, label, value) {
    if (value === null || value === undefined || value === "") return;

    const paragraph = document.createElement("p");
    const strong = document.createElement("strong");

    strong.textContent = `${label}: `;
    paragraph.appendChild(strong);
    paragraph.appendChild(document.createTextNode(String(value)));
    card.appendChild(paragraph);
}

function addSourceLink(card, url, label = "View research source") {
    if (!url) return;

    try {
        const parsed = new URL(url);

        if (!["https:", "http:"].includes(parsed.protocol)) return;

        const link = document.createElement("a");
        link.href = parsed.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = label;
        card.appendChild(link);
    } catch {
        // Ignore malformed URLs.
    }
}


function renderCandidates(candidates) {
    candidatesContainer.replaceChildren();

    if (!candidates.length) {
        reviewMessage.textContent =
            "No saved candidates for this event. You can run sponsor discovery.";
        return;
    }

    const ranked = [...candidates].sort((a, b) => {
        const scoreA = a.ai_score == null ? -Infinity : Number(a.ai_score);
        const scoreB = b.ai_score == null ? -Infinity : Number(b.ai_score);
        if (scoreA !== scoreB) return scoreB - scoreA;

        const rankA = a.human_rank == null ? Infinity : Number(a.human_rank);
        const rankB = b.human_rank == null ? Infinity : Number(b.human_rank);
        if (rankA !== rankB) return rankA - rankB;

        return String(a.company_name || "").localeCompare(
            String(b.company_name || "")
        );
    });

    reviewMessage.textContent =
        `${ranked.length} saved sponsor candidate(s).`;

    for (const [index, candidate] of ranked.entries()) {
        const card = document.createElement("article");
        card.className = "candidate-card";

        const heading = document.createElement("h3");
        heading.textContent = candidate.company_name || "Unnamed company";
        card.appendChild(heading);

        const status = String(candidate.status || "DISCOVERED").toUpperCase();
        const rank = candidate.human_rank ??
            (candidate.ai_score != null ? index + 1 : "Unranked");

        addText(card, "Company ID", candidate.company_id);
        addText(card, "Rank", rank);
        addText(card, "Industry", candidate.industry);
        addText(card, "Status", status);
        addText(card, "Discovery source", candidate.discovery_source);
        addText(card, "Relevance score", candidate.ai_score);
        addText(card, "Research evidence", candidate.evidence_snippet);
        addSourceLink(card, candidate.website, "Company website");
        addSourceLink(card, candidate.source_url, "Research source");

        const actions = document.createElement("div");
        actions.className = "candidate-actions";

        if (status === "SELECTED" || status === "CONTACTED" || status === "CLOSED") {
            actions.appendChild(createButton(
                status === "SELECTED" ? "✓ Selected" : status,
                "button button-secondary",
                () => {},
            ));
        } else {
            actions.appendChild(createButton(
                "Select Sponsor",
                "button button-primary",
                () => updateSponsorSelection(
                    activeSponsorEvent.event_id,
                    candidate.company_id,
                    "SELECTED"
                )
            ));
        }
        actions.appendChild(createButton(
            "🗑",
            "icon-button danger-icon sponsor-delete-button",
            () => deleteSponsorCandidate(activeSponsorEvent.event_id, candidate)
        ));

        actions.appendChild(createButton(
            "Sponsor History",
            "button button-secondary",
            () => loadCompanyHistory(
                activeSponsorEvent.event_id,
                candidate.company_id,
                card
            )
        ));

        if (status === "SELECTED") {
            actions.appendChild(createButton(
                "Find Contacts",
                "button button-primary",
                () => discoverSponsorContacts(
                    activeSponsorEvent.event_id,
                    candidate.company_id,
                    card
                )
            ));

            actions.appendChild(createButton(
                "View Contacts",
                "button button-secondary",
                () => loadSponsorContacts(
                    activeSponsorEvent.event_id,
                    candidate.company_id,
                    card
                )
            ));
        }

        actions.appendChild(createButton(
            "Outreach History",
            "button button-secondary",
            () => loadOutreachHistory(
                activeSponsorEvent.event_id,
                candidate.company_id,
                card
            )
        ));

        card.appendChild(actions);
        candidatesContainer.appendChild(card);
    }
}


// ---------- Shared helpers ----------

function getOrCreatePanel(card, className) {
    let panel = card.querySelector(`.${className}`);

    if (!panel) {
        panel = document.createElement("div");
        panel.className = className;
        card.appendChild(panel);
    }

    panel.replaceChildren();
    return panel;
}

function addPanelMessage(panel, message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    panel.appendChild(paragraph);
}

async function readApiResponse(response) {
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        const detail = typeof data.detail === "string"
            ? data.detail
            : `HTTP ${response.status}`;

        throw new Error(detail);
    }

    return data;
}


// ---------- Select or delete a sponsor ----------

async function deleteSponsorCandidate(eventId, candidate) {
    const companyName = candidate.company_name || "this sponsor";
    const confirmed = window.confirm(`Delete ${companyName} from this event's sponsor pipeline?

Event-level research/contact records will be removed. The global company record is kept. Sponsors with outreach history cannot be deleted.`);
    if (!confirmed) return;
    try {
        const response = await fetch(`${API_URL}/${eventId}/sponsors/${candidate.company_id}`, { method: "DELETE" });
        await readApiResponse(response);
        await loadCandidates(eventId);
        await loadEventProgress();
    } catch (error) {
        window.alert(`Could not delete sponsor: ${error.message}`);
    }
}

async function updateSponsorSelection(eventId, companyId, status) {
    try {
        const response = await fetch(
            `${API_URL}/${eventId}/sponsors/${companyId}/selection`,
            {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status })
            }
        );

        await readApiResponse(response);
        await loadCandidates(eventId);
    } catch (error) {
        alert(`Could not update sponsor selection: ${error.message}`);
    }
}


// ---------- Discover and list contacts ----------

async function discoverSponsorContacts(eventId, companyId, card) {
    const panel = getOrCreatePanel(card, "sponsor-contact-panel");
    addPanelMessage(panel, "Searching for suitable company contacts...");

    try {
        const response = await fetch(
            `${API_URL}/${eventId}/sponsors/${companyId}/contacts/discover`,
            { method: "POST" }
        );

        const data = await readApiResponse(response);

        await loadSponsorContacts(eventId, companyId, card);

        if (data.message) {
            reviewMessage.textContent = data.message;
        }
    } catch (error) {
        addPanelMessage(panel, `Contact discovery failed: ${error.message}`);
    }
}

async function loadSponsorContacts(eventId, companyId, card) {
    const panel = getOrCreatePanel(card, "sponsor-contact-panel");
    addPanelMessage(panel, "Loading saved contacts...");

    try {
        const response = await fetch(
            `${API_URL}/${eventId}/sponsors/${companyId}/contacts`
        );

        const data = await readApiResponse(response);
        panel.replaceChildren();

        const heading = document.createElement("h4");
        heading.textContent = "Ranked Contacts";
        panel.appendChild(heading);

        if (!data.contacts?.length) {
            addPanelMessage(panel, "No contacts found for this company.");
            return;
        }

        for (const contact of data.contacts) {
            const contactCard = document.createElement("div");
            contactCard.className = "contact-card";

            const name = document.createElement("h4");
            name.textContent = contact.full_name || contact.email_address;
            contactCard.appendChild(name);

            addText(contactCard, "Email", contact.email_address);
            addText(contactCard, "Role", contact.job_title);
            addText(contactCard, "Department", contact.department);
            addText(contactCard, "Priority", contact.priority_rank);
            addText(contactCard, "Category", contact.contact_category);
            addText(contactCard, "Hunter confidence", contact.confidence);
            addText(
                contactCard,
                "Verification",
                contact.verification_status || "Unverified"
            );
            addText(
                contactCard,
                "Why selected",
                contact.selection_reason
            );

            if (contact.verification_warning) {
                addText(
                    contactCard,
                    "Warning",
                    contact.verification_warning
                );
            }

            addSourceLink(contactCard, contact.source_url, "Contact source");

            if (contact.recommended && contact.can_generate_draft) {
                contactCard.appendChild(createButton(
                    "Generate Email Draft",
                    "button button-primary",
                    () => createSponsorDraft(
                        eventId,
                        companyId,
                        contact,
                        contactCard
                    )
                ));
            } else {
                addPanelMessage(
                    contactCard,
                    "Not recommended for sponsorship outreach."
                );
            }

            panel.appendChild(contactCard);
        }
    } catch (error) {
        panel.replaceChildren();
        addPanelMessage(panel, `Could not load contacts: ${error.message}`);
    }
}


// ---------- Generate and edit an email draft ----------

async function createSponsorDraft(eventId, companyId, contact, contactCard) {
    const panel = getOrCreatePanel(contactCard, "email-draft-panel");
    addPanelMessage(panel, "Generating email draft...");

    try {
        const response = await fetch(
            `${API_URL}/${eventId}/sponsors/${companyId}/contacts/${contact.contact_id}/draft`,
            { method: "POST" }
        );

        const draft = await readApiResponse(response);
        renderEmailDraftEditor(draft, eventId, contactCard, panel);
    } catch (error) {
        panel.replaceChildren();
        addPanelMessage(panel, `Draft generation failed: ${error.message}`);
    }
}

function renderEmailDraftEditor(draft, eventId, card, panel) {
    panel.replaceChildren();

    const heading = document.createElement("h4");
    heading.textContent = `Email draft #${draft.email_id}`;
    panel.appendChild(heading);

    const subjectLabel = document.createElement("label");
    subjectLabel.textContent = "Subject";

    const subjectInput = document.createElement("input");
    subjectInput.type = "text";
    subjectInput.value = draft.subject || "";
    subjectInput.className = "email-subject-input";
    subjectLabel.appendChild(subjectInput);
    panel.appendChild(subjectLabel);

    const bodyLabel = document.createElement("label");
    bodyLabel.textContent = "Email body";

    const bodyInput = document.createElement("textarea");
    bodyInput.rows = 12;
    bodyInput.value = draft.body || "";
    bodyInput.className = "email-body-input";
    bodyLabel.appendChild(bodyInput);
    panel.appendChild(bodyLabel);

    const status = document.createElement("p");
    status.textContent =
        `Status: ${draft.status}. Review the recipient and content before sending.`;
    panel.appendChild(status);

    const saveButton = createButton(
        "Save Draft",
        "button button-secondary",
        saveDraft
    );

    const sendButton = createButton(
        "Approve & Send",
        "button button-primary",
        sendDraft
    );

    // Sending remains disabled until the current text is saved.
    sendButton.disabled = true;

    subjectInput.addEventListener("input", () => {
        sendButton.disabled = true;
        status.textContent = "Draft changed. Save before sending.";
    });

    bodyInput.addEventListener("input", () => {
        sendButton.disabled = true;
        status.textContent = "Draft changed. Save before sending.";
    });

    panel.appendChild(saveButton);
    panel.appendChild(sendButton);

    async function saveDraft() {
        saveButton.disabled = true;
        status.textContent = "Saving draft...";

        try {
            const response = await fetch(
                `${API_URL}/${eventId}/outreach/${draft.email_id}`,
                {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        subject: subjectInput.value,
                        body: bodyInput.value
                    })
                }
            );

            await readApiResponse(response);
            sendButton.disabled = false;
            status.textContent = "Draft saved. Sending is now available.";
        } catch (error) {
            status.textContent = `Could not save draft: ${error.message}`;
        } finally {
            saveButton.disabled = false;
        }
    }

    async function sendDraft() {
        if (sendButton.disabled) return;

        const approved = confirm(
            `Send this email to ${draft.recipient_email}?\n\n` +
            `Subject: ${subjectInput.value}\n\n` +
            `Confirm only after reviewing the full email.`
        );

        if (!approved) return;

        sendButton.disabled = true;
        saveButton.disabled = true;
        status.textContent = "Sending email...";

        try {
            const response = await fetch(
                `${API_URL}/${eventId}/outreach/${draft.email_id}/send`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ confirm_send: true, confirm_recipient: true })
                }
            );

            const result = await readApiResponse(response);
            status.textContent = result.message || "SMTP accepted the email.";

            await loadOutreachHistory(eventId, draft.company_id, card);
        } catch (error) {
            status.textContent =
                `Send result needs checking: ${error.message}. ` +
                "Do not immediately retry; check the outreach record first.";
        } finally {
            saveButton.disabled = false;
        }
    }
}


// ---------- Previous event appearances and evidence ----------

async function loadCompanyHistory(eventId, companyId, card) {
    const panel = getOrCreatePanel(card, "company-history-panel");
    addPanelMessage(panel, "Loading sponsor history...");

    try {
        const response = await fetch(
            `${API_URL}/${eventId}/sponsors/${companyId}/history`
        );

        const history = await readApiResponse(response);
        panel.replaceChildren();

        const heading = document.createElement("h4");
        heading.textContent = `History: ${history.company_name}`;
        panel.appendChild(heading);

        const eventsHeading = document.createElement("h5");
        eventsHeading.textContent = "Previous SponsyBot event appearances";
        panel.appendChild(eventsHeading);

        if (!history.previous_events?.length) {
            addPanelMessage(
                panel,
                "No appearances in other events were found in this workspace."
            );
        } else {
            for (const item of history.previous_events) {
                const entry = document.createElement("div");
                entry.className = "history-entry";
                addText(entry, "Event", item.event_name);
                addText(entry, "Event ID", item.event_id);
                addText(entry, "Date", item.event_date);
                addText(entry, "Previous status", item.status);
                addText(entry, "Discovery source", item.discovery_source);
                panel.appendChild(entry);
            }
        }

        const evidenceHeading = document.createElement("h5");
        evidenceHeading.textContent = "Public sponsorship-related research";
        panel.appendChild(evidenceHeading);

        if (!history.sponsorship_evidence?.length) {
            addPanelMessage(
                panel,
                "No research sources classified as sponsorship-related were found. This does not prove the company has never sponsored an event."
            );
        } else {
            for (const item of history.sponsorship_evidence) {
                const entry = document.createElement("div");
                entry.className = "history-entry";
                addText(entry, "Research event", item.research_event_name);
                addText(entry, "Source title", item.source_title);
                addText(entry, "Evidence", item.evidence_snippet);
                addText(entry, "Research type", item.research_type);
                addSourceLink(entry, item.source_url, "Open evidence source");
                panel.appendChild(entry);
            }
        }
    } catch (error) {
        panel.replaceChildren();
        addPanelMessage(panel, `Could not load sponsor history: ${error.message}`);
    }
}


// ---------- Outreach draft/send history ----------

async function loadOutreachHistory(eventId, companyId, card) {
    const panel = getOrCreatePanel(card, "outreach-history-panel");
    addPanelMessage(panel, "Loading outreach history...");

    try {
        const response = await fetch(
            `${API_URL}/${eventId}/outreach`
        );

        const data = await readApiResponse(response);
        const emails = (data.outreach || []).filter(
            item => Number(item.company_id) === Number(companyId)
        );

        panel.replaceChildren();

        const heading = document.createElement("h4");
        heading.textContent = "Email and Follow-up Records";
        panel.appendChild(heading);

        if (!emails.length) {
            addPanelMessage(
                panel,
                "No email drafts or send records are saved for this company yet."
            );
            addPanelMessage(
                panel,
                "Reply detection and follow-up tracking are not implemented yet."
            );
            return;
        }

        for (const email of emails) {
            const entry = document.createElement("div");
            entry.className = "history-entry";

            addText(entry, "Recipient", email.recipient_email);
            addText(entry, "Subject", email.subject);
            addText(entry, "Status", email.status);
            addText(entry, "Created", email.created_at);
            addText(entry, "Approved", email.approved_at);
            addText(entry, "Sent", email.sent_at);
            addText(entry, "Error", email.error_message);

            panel.appendChild(entry);
        }

        addPanelMessage(
            panel,
            "This is stored draft/send history. Automatic reply detection and follow-up events are separate features not yet implemented."
        );
    } catch (error) {
        panel.replaceChildren();
        addPanelMessage(panel, `Could not load outreach history: ${error.message}`);
    }
}


async function apiRequest(url, options = {}) {
    const response = await fetch(url, options);

    let data = {};
    try {
        data = await response.json();
    } catch {
        // The server may return an empty or non-JSON response.
    }

    if (!response.ok) {
        let message = data.detail || `HTTP ${response.status}`;

        if (Array.isArray(message)) {
            message = message
                .map(item => `${item.loc?.join(".") || "field"}: ${item.msg}`)
                .join("; ");
        }

        throw new Error(String(message));
    }

    return data;
}

function showPanel(card, className, titleText) {
    let panel = card.querySelector(`.${className}`);

    if (!panel) {
        panel = document.createElement("section");
        panel.className = className;
        card.appendChild(panel);
    }

    panel.replaceChildren();

    const title = document.createElement("h4");
    title.textContent = titleText;
    panel.appendChild(title);

    return panel;
}


// ---------- Sponsor selection ----------

async function updateSponsorSelection(eventId, companyId, status) {
    try {
        await apiRequest(
            `${API_URL}/${eventId}/sponsors/${companyId}/selection`,
            {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status })
            }
        );

        await loadCandidates(eventId);
    } catch (error) {
        console.error("Failed to update sponsor selection:", error);
        reviewMessage.textContent =
            `Could not update sponsor selection: ${error.message}`;
    }
}


// ---------- Contact discovery and display ----------

async function discoverSponsorContacts(eventId, companyId, card) {
    const panel = showPanel(
        card,
        "contact-results",
        "Discovering business contacts..."
    );

    try {
        const data = await apiRequest(
            `${API_URL}/${eventId}/sponsors/${companyId}/contacts/discover`,
            { method: "POST" }
        );

        renderContacts(
            panel,
            eventId,
            companyId,
            data.contacts || [],
            data.message
        );
    } catch (error) {
        console.error("Contact discovery failed:", error);
        panel.textContent = `Contact discovery failed: ${error.message}`;
    }
}

async function loadSponsorContacts(eventId, companyId, card) {
    const panel = showPanel(
        card,
        "contact-results",
        "Saved business contacts"
    );

    try {
        const data = await apiRequest(
            `${API_URL}/${eventId}/sponsors/${companyId}/contacts`
        );

        renderContacts(
            panel,
            eventId,
            companyId,
            data.contacts || [],
            "Loaded saved contacts from MySQL."
        );
    } catch (error) {
        console.error("Failed to load contacts:", error);
        panel.textContent = `Could not load contacts: ${error.message}`;
    }
}

function renderContacts(
    panel,
    eventId,
    companyId,
    contacts,
    serverMessage = ""
) {
    panel.replaceChildren();

    const heading = document.createElement("h4");
    heading.textContent = `Business Contacts (${contacts.length})`;
    panel.appendChild(heading);

    if (serverMessage) {
        const message = document.createElement("p");
        message.textContent = serverMessage;
        panel.appendChild(message);
    }

    if (!contacts.length) {
        addText(
            panel,
            "Result",
            "No contacts were found. Review the company's official website."
        );
        return;
    }

    const ranked = [...contacts].sort((a, b) => {
        const rankA = a.priority_rank ?? Infinity;
        const rankB = b.priority_rank ?? Infinity;

        if (rankA !== rankB) return rankA - rankB;

        return (b.confidence ?? 0) - (a.confidence ?? 0);
    });

    for (const contact of ranked) {
        const contactCard = document.createElement("article");
        contactCard.className = "contact-card";

        const contactName = document.createElement("h5");
        contactName.textContent =
            contact.full_name || contact.email_address || "Unnamed contact";
        contactCard.appendChild(contactName);

        addText(contactCard, "Email", contact.email_address);
        addText(contactCard, "Job title", contact.job_title);
        addText(contactCard, "Department", contact.department);
        addText(contactCard, "Email type", contact.email_type);
        addText(contactCard, "Hunter confidence", contact.confidence);
        addText(
            contactCard,
            "Verification",
            contact.verification_status || "Not verified"
        );
        addText(
            contactCard,
            "Outreach priority",
            contact.priority_rank == null
                ? "Not recommended"
                : `Tier ${contact.priority_rank}`
        );
        addText(
            contactCard,
            "Contact category",
            contact.contact_category
        );
        addText(
            contactCard,
            "Why selected",
            contact.selection_reason
        );
        addText(
            contactCard,
            "Verification warning",
            contact.verification_warning
        );

        addSourceLink(contactCard, contact.source_url, "View email source");

        const draftButton = createButton(
            "Generate Email Draft",
            "button button-primary",
            () => generateContactDraft(
                eventId,
                companyId,
                contact,
                contactCard
            )
        );

        if (!contact.can_generate_draft || !contact.recommended) {
            draftButton.disabled = true;
            draftButton.title =
                "This contact is not recommended for sponsorship outreach.";
        }

        contactCard.appendChild(draftButton);
        panel.appendChild(contactCard);
    }
}


// ---------- Generate and edit an email draft ----------

async function generateContactDraft(
    eventId,
    companyId,
    contact,
    contactCard
) {
    const panel = showPanel(
        contactCard,
        "draft-panel",
        "Generating email draft..."
    );

    try {
        const data = await apiRequest(
            `${API_URL}/${eventId}/sponsors/${companyId}/contacts/${contact.contact_id}/draft`,
            { method: "POST" }
        );

        renderDraftEditor(panel, eventId, companyId, data);
    } catch (error) {
        console.error("Email draft generation failed:", error);
        panel.textContent = `Draft generation failed: ${error.message}`;
    }
}

function renderDraftEditor(panel, eventId, companyId, draft) {
    panel.replaceChildren();

    const heading = document.createElement("h4");
    heading.textContent = "Review Email Draft";
    panel.appendChild(heading);

    addText(panel, "Recipient", draft.recipient_email);
    addText(panel, "Recipient name", draft.recipient_name);
    addText(panel, "Contact category", draft.contact_category);
    addText(panel, "Selection reason", draft.selection_reason);
    addText(panel, "Verification warning", draft.verification_warning);
    addText(panel, "Draft ID", draft.email_id);
    addText(panel, "Status", draft.status);

    const subjectLabel = document.createElement("label");
    subjectLabel.className = "draft-field";
    subjectLabel.textContent = "Subject";

    const subjectInput = document.createElement("input");
    subjectInput.type = "text";
    subjectInput.value = draft.subject || "";
    subjectInput.required = true;
    subjectInput.maxLength = 500;
    subjectLabel.appendChild(subjectInput);
    panel.appendChild(subjectLabel);

    const bodyLabel = document.createElement("label");
    bodyLabel.className = "draft-field";
    bodyLabel.textContent = "Email body";

    const bodyInput = document.createElement("textarea");
    bodyInput.value = draft.body || "";
    bodyInput.rows = 12;
    bodyInput.required = true;
    bodyLabel.appendChild(bodyInput);
    panel.appendChild(bodyLabel);

    const message = document.createElement("p");
    message.className = "draft-status-message";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    panel.appendChild(message);

    const actions = document.createElement("div");
    actions.className = "draft-actions";

    const saveButton = createButton(
        "Save Draft",
        "button button-secondary",
        saveDraft
    );

    const sendButton = createButton(
        "Approve & Send Email",
        "button button-primary",
        sendDraft
    );

    actions.appendChild(saveButton);
    actions.appendChild(sendButton);
    panel.appendChild(actions);

    async function persistDraft() {
        const subject = subjectInput.value.trim();
        const body = bodyInput.value.trim();

        if (!subject || !body) {
            throw new Error("Subject and body must not be empty.");
        }

        await apiRequest(
            `${API_URL}/${eventId}/outreach/${draft.email_id}`,
            {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ subject, body })
            }
        );
    }

    async function saveDraft() {
        saveButton.disabled = true;
        message.textContent = "Saving draft...";

        try {
            await persistDraft();
            message.textContent = "Draft saved. It has not been sent.";
        } catch (error) {
            message.textContent = `Could not save draft: ${error.message}`;
        } finally {
            saveButton.disabled = false;
        }
    }

    async function sendDraft() {
        const confirmed = window.confirm(
            `Send this email to ${draft.recipient_email}?\n\n` +
            "Check the recipient, subject, and full email body first."
        );

        if (!confirmed) return;

        sendButton.disabled = true;
        saveButton.disabled = true;
        message.textContent = "Saving the draft before sending...";

        try {
            // Save any edits before attempting to send.
            await persistDraft();

            message.textContent = "Sending email...";

            const result = await apiRequest(
                `${API_URL}/${eventId}/outreach/${draft.email_id}/send`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ confirm_send: true, confirm_recipient: true })
                }
            );

            message.textContent =
                `${result.message} Status: ${result.status}.`;

            sendButton.disabled = true;
            saveButton.disabled = true;

            // Refresh the candidate list to display the new sponsor status.
            await loadCandidates(eventId);
        } catch (error) {
            message.textContent =
                `Send operation did not complete successfully: ${error.message}`;

            // Do not automatically retry: the SMTP server may have accepted
            // the message even if the final database update failed.
            sendButton.disabled = false;
            saveButton.disabled = false;
        }
    }
}


// ---------- Email and outreach history ----------

async function loadOutreachHistory(eventId, companyId, card) {
    const panel = showPanel(
        card,
        "outreach-history-panel",
        "Outreach History"
    );

    try {
        const data = await apiRequest(
            `${API_URL}/${eventId}/outreach`
        );

        const history = (data.outreach || []).filter(
            item => Number(item.company_id) === Number(companyId)
        );

        if (!history.length) {
            addText(panel, "History", "No email drafts or send records yet.");
            return;
        }

        const heading = document.createElement("h4");
        heading.textContent = `Outreach History (${history.length})`;
        panel.replaceChildren(heading);

        for (const item of history) {
            const record = document.createElement("details");
            record.className = "outreach-record";

            const summary = document.createElement("summary");
            summary.textContent =
                `${item.status} — ${item.recipient_email} — ${item.subject}`;
            record.appendChild(summary);

            addText(record, "Recipient name", item.recipient_name);
            addText(record, "Created", item.created_at);
            addText(record, "Approved", item.approved_at);
            addText(record, "Sent", item.sent_at);
            addText(record, "Error", item.error_message);
            addText(record, "Subject", item.subject);
            addText(record, "Email body", item.body);

            panel.appendChild(record);
        }
    } catch (error) {
        console.error("Failed to load outreach history:", error);
        panel.textContent = `Could not load outreach history: ${error.message}`;
    }
}


async function loadCandidates(eventId) {
    reviewMessage.textContent = "Loading saved candidates...";
    candidatesContainer.replaceChildren();

    const response = await fetch(
        `${API_URL}/${eventId}/candidates`
    );

    if (!response.ok) {
        throw new Error(`Candidate API returned HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!Array.isArray(data.candidates)) {
        throw new Error("Unexpected candidate API response.");
    }

    renderCandidates(data.candidates);
}

async function openSponsorReview(event) {
    activeSponsorEvent = event;
    reviewSection.hidden = false;
    reviewTitle.textContent = `Sponsors for ${event.event_name}`;
    runDiscoveryButton.disabled = false;

    reviewSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

    try {
        await loadCandidates(event.event_id);
    } catch (error) {
        console.error("Failed to load candidates:", error);
        reviewMessage.textContent =
            "Could not load saved candidates. Check the server.";
    }
}

runDiscoveryButton.addEventListener("click", async () => {
    if (!activeSponsorEvent) return;

    const eventId = activeSponsorEvent.event_id;

    runDiscoveryButton.disabled = true;
    reviewMessage.textContent = "Sponsor discovery is running...";
    candidatesContainer.replaceChildren();

    try {
        const response = await fetch(
            `${API_URL}/${eventId}/discover`,
            { method: "POST" }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                typeof data.detail === "string"
                    ? data.detail
                    : `HTTP ${response.status}`
            );
        }

        await loadCandidates(eventId);
    } catch (error) {
        console.error("Sponsor discovery failed:", error);
        reviewMessage.textContent =
            `Discovery failed: ${error.message}. Existing saved candidates have not been removed.`;
    } finally {
        runDiscoveryButton.disabled = false;
    }
});

document.getElementById("closeSponsorReview")
    .addEventListener("click", () => {
        reviewSection.hidden = true;
        activeSponsorEvent = null;
    });

filterButtons.forEach(button => {
    button.addEventListener("click", () => {
        currentFilter = button.dataset.filter;

        filterButtons.forEach(item => {
            item.classList.toggle("active", item === button);
        });

        renderEvents();
    });
});

eventSearchInput?.addEventListener("input", renderEvents);
eventTypeFilter?.addEventListener("change", renderEvents);
eventSortSelect?.addEventListener("change", renderEvents);
if (eventSearchInput) {
    const initialSearch = new URLSearchParams(window.location.search).get("search");
    if (initialSearch) eventSearchInput.value = initialSearch;
}

async function loadEvents() {
    eventsMessage.textContent = "Loading events...";

    try {
        const response = await fetch(`${API_URL}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (!Array.isArray(data.events)) {
            throw new Error("Unexpected events API response.");
        }

        allEvents = data.events;
        updateStatistics();
        await loadEventProgress({ render: false });
        renderEvents();
    } catch (error) {
        console.error("Failed to load events:", error);

        eventsMessage.textContent =
            "Could not load events. Check that FastAPI is running.";

        tableBody.replaceChildren();
        totalEventsElement.textContent = "—";
        pastEventsElement.textContent = "—";
        upcomingEventsElement.textContent = "—";
    }
}

loadEvents();

window.setInterval(() => {
    if (document.visibilityState === "visible") loadEventProgress();
}, 30000);
