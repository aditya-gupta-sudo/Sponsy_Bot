(() => {
    "use strict";

    const params = new URLSearchParams(window.location.search);
    const requestedEventId = Number(params.get("event_id"));

    let activeEventId =
        Number.isInteger(requestedEventId) && requestedEventId > 0
            ? requestedEventId
            : null;

    let activeEvent = null;
    let currentCandidates = [];
    let currentDraft = null;
    let isDraftSaved = true;

    const $ = id => document.getElementById(id);
    const title = $("pipelineEventTitle");
    const meta = $("pipelineEventMeta");
    const message = $("pipelineMessage");
    const candidateContainer = $("pipelineCandidates");
    const pipelineStats = document.querySelector(".pipeline-stats");
    const picker = $("pipelineEventPicker");
    const pickerList = $("pipelineEventList");
    const discoveryButton = $("runPipelineDiscoveryButton");
    const refreshButton = $("refreshPipelineButton");
    const searchInput = $("pipelineSearch");
    const draftDialog = $("emailDraftDialog");
    const draftStatus = $("emailDraftStatus");
    const subjectInput = $("emailDraftSubject");
    const bodyInput = $("emailDraftBody");
    const recipientCheck = $("confirmRecipientCheckbox");
    const saveDraftButton = $("saveEmailDraft");
    const sendDraftButton = $("sendEmailDraft");

    function escapeHtml(value) {
        return String(value ?? "").replace(
            /[&<>"']/g,
            c => ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;"
            })[c]
        );
    }

    function makeElement(tag, content, className) {
        const element = document.createElement(tag);

        if (content !== undefined && content !== null) {
            element.textContent = String(content);
        }

        if (className) {
            element.className = className;
        }

        return element;
    }

    function makeButton(label, className, handler, options = {}) {
        const button = document.createElement("button");

        button.type = "button";
        button.className = className;
        button.textContent = label;

        if (options.title) {
            button.title = options.title;
        }

        if (options.ariaLabel) {
            button.setAttribute("aria-label", options.ariaLabel);
        }

        if (options.disabled) {
            button.disabled = true;
        }

        button.addEventListener("click", handler);

        return button;
    }

    function appendText(parent, label, value) {
        if (
            value === undefined ||
            value === null ||
            value === ""
        ) {
            return;
        }

        const p = document.createElement("p");
        const strong = document.createElement("strong");

        strong.textContent = `${label}: `;

        p.append(
            strong,
            document.createTextNode(String(value))
        );

        parent.appendChild(p);
    }

    function appendLink(parent, href, label) {
        if (!href) return;

        try {
            const url = new URL(href);

            if (!["https:", "http:"].includes(url.protocol)) {
                return;
            }

            const link = makeElement("a", label);

            link.href = url.href;
            link.target = "_blank";
            link.rel = "noopener noreferrer";

            parent.appendChild(link);
        } catch {
            // Invalid source URLs are omitted.
        }
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: {
                "Accept": "application/json",
                ...(options.headers || {})
            },
            ...options
        });

        if (response.status === 401) {
            window.location.replace(
                `/login?next=${encodeURIComponent(
                    window.location.pathname +
                    window.location.search
                )}`
            );

            throw new Error(
                "Your session expired. Sign in again."
            );
        }

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            const detail = Array.isArray(data.detail)
                ? data.detail
                    .map(item =>
                        `${item.loc?.join(".") || "field"}: ${item.msg}`
                    )
                    .join("; ")
                : data.detail || `HTTP ${response.status}`;

            throw new Error(String(detail));
        }

        return data;
    }

    // ============================================================
    // SHARED SPONSOR ACTION MODAL
    // ============================================================

    let sponsorActionDialog = null;
    let sponsorActionTitle = null;
    let sponsorActionSubtitle = null;
    let sponsorActionBody = null;
    let sponsorActionFooter = null;
    let sponsorActionResult = null;

    function ensureSponsorActionDialog() {
        if (sponsorActionDialog) return;

        sponsorActionDialog = document.createElement("dialog");
        sponsorActionDialog.id = "sponsorActionDialog";
        sponsorActionDialog.className =
            "event-dialog email-modal sponsor-action-dialog";

        sponsorActionDialog.setAttribute(
            "aria-labelledby",
            "sponsorActionHeading"
        );

        sponsorActionDialog.style.width = "min(1000px, 94vw)";
        sponsorActionDialog.style.maxWidth = "94vw";
        sponsorActionDialog.style.maxHeight = "90vh";
        sponsorActionDialog.style.overflow = "hidden";

        const header = makeElement(
            "div",
            null,
            "dialog-header"
        );

        const headerCopy = makeElement("div");

        headerCopy.appendChild(
            makeElement("p", "SPONSOR WORKSPACE", "eyebrow")
        );

        sponsorActionTitle = makeElement(
            "h2",
            "Sponsor details"
        );

        sponsorActionTitle.id = "sponsorActionHeading";

        sponsorActionSubtitle = makeElement("p", "");

        headerCopy.append(
            sponsorActionTitle,
            sponsorActionSubtitle
        );

        const closeIcon = makeButton(
            "✕",
            "icon-button",
            closeSponsorActionDialog,
            {
                ariaLabel: "Close sponsor details"
            }
        );

        header.append(
            headerCopy,
            closeIcon
        );

        sponsorActionBody = makeElement(
            "div",
            null,
            "sponsor-action-content"
        );

        sponsorActionBody.style.maxHeight = "60vh";
        sponsorActionBody.style.overflowY = "auto";
        sponsorActionBody.style.padding = "8px 2px";

        sponsorActionResult = makeElement(
            "div",
            null,
            "sponsor-action-result"
        );

        sponsorActionBody.appendChild(sponsorActionResult);

        sponsorActionFooter = makeElement(
            "div",
            null,
            "dialog-actions sponsor-action-footer"
        );

        sponsorActionFooter.style.display = "flex";
        sponsorActionFooter.style.flexWrap = "wrap";
        sponsorActionFooter.style.gap = "8px";
        sponsorActionFooter.style.justifyContent = "flex-end";

        const closeButton = makeButton(
            "Close",
            "button button-secondary",
            closeSponsorActionDialog
        );

        sponsorActionFooter.appendChild(closeButton);

        sponsorActionDialog.append(
            header,
            sponsorActionBody,
            sponsorActionFooter
        );

        document.body.appendChild(sponsorActionDialog);

        sponsorActionDialog.addEventListener("cancel", event => {
            event.preventDefault();
            closeSponsorActionDialog();
        });

        sponsorActionDialog.addEventListener("click", event => {
            if (event.target === sponsorActionDialog) {
                closeSponsorActionDialog();
            }
        });
    }

    function closeSponsorActionDialog() {
        if (sponsorActionDialog?.open) {
            sponsorActionDialog.close();
        } else {
            sponsorActionDialog?.removeAttribute("open");
        }
    }

    function setSponsorActionFooter(candidate, options = {}) {
        ensureSponsorActionDialog();

        sponsorActionFooter.replaceChildren();

        const status = String(
            candidate.status || "DISCOVERED"
        ).toUpperCase();

        if (
            options.allowContactActions &&
            status === "SELECTED"
        ) {
            sponsorActionFooter.appendChild(
                makeButton(
                    "Find Contacts",
                    "button button-secondary",
                    () => findContacts(candidate)
                )
            );

            sponsorActionFooter.appendChild(
                makeButton(
                    "View Contacts",
                    "button button-secondary",
                    () => viewContacts(candidate)
                )
            );
        } else if (status === "SELECTED") {
            sponsorActionFooter.appendChild(
                makeButton(
                    "View Contacts",
                    "button button-secondary",
                    () => viewContacts(candidate)
                )
            );
        }

        sponsorActionFooter.appendChild(
            makeButton(
                "Sponsor History",
                "button button-secondary",
                () => showSponsorHistory(candidate)
            )
        );

        sponsorActionFooter.appendChild(
            makeButton(
                "Outreach History",
                "button button-secondary",
                () => showOutreachHistory(candidate)
            )
        );

        sponsorActionFooter.appendChild(
            makeButton(
                "Remove from Event",
                "button button-secondary danger-button",
                () => deleteSponsor(candidate)
            )
        );

        sponsorActionFooter.appendChild(
            makeButton(
                "Close",
                "button button-secondary",
                closeSponsorActionDialog
            )
        );
    }

    function openSponsorActionDialog(
        candidate,
        heading,
        subtitle,
        options = {}
    ) {
        ensureSponsorActionDialog();

        sponsorActionTitle.textContent =
            heading ||
            candidate.company_name ||
            "Sponsor details";

        sponsorActionSubtitle.textContent =
            subtitle ||
            "Review the saved information and available actions.";

        sponsorActionResult.replaceChildren();

        const summary = makeElement(
            "section",
            null,
            "panel sponsor-modal-summary"
        );

        summary.appendChild(
            makeElement(
                "h3",
                candidate.company_name || "Unnamed company"
            )
        );

        const status = String(
            candidate.status || "DISCOVERED"
        ).toUpperCase();

        summary.appendChild(
            makeElement(
                "span",
                status,
                `pipeline-status-pill status-${status.toLowerCase()}`
            )
        );

        appendText(summary, "Rank", candidate.human_rank);
        appendText(summary, "Industry", candidate.industry);

        appendText(
            summary,
            "Discovery source",
            candidate.discovery_source
        );

        appendText(
            summary,
            "Research evidence",
            candidate.evidence_snippet
        );

        appendLink(
            summary,
            candidate.website,
            "Company website ↗"
        );

        appendLink(
            summary,
            candidate.source_url,
            candidate.source_title ||
                "Open research source ↗"
        );

        sponsorActionResult.appendChild(summary);

        setSponsorActionFooter(candidate, options);

        if (!sponsorActionDialog.open) {
            sponsorActionDialog.showModal();
        }

        return sponsorActionResult;
    }

    function setStat(id, value) {
        $(id).textContent = String(value);
    }

    // ============================================================
    // EVENT PICKER
    // ============================================================

    async function chooseEventList() {
        if (pipelineStats) {
            pipelineStats.hidden = true;
        }
        picker.hidden = false;
        discoveryButton.disabled = true;

        message.textContent =
            "Choose an event to open its pipeline.";

        title.innerHTML = "Sponsor <span>Pipeline</span>";

        meta.textContent =
            "Every event has its own sponsor list, contact records, and outreach history.";

        try {
            const data = await api("/api/events");

            pickerList.replaceChildren();

            const events = data.events || [];

            if (!events.length) {
                pickerList.appendChild(
                    makeElement(
                        "p",
                        "No events yet. Create an event before discovering sponsors."
                    )
                );

                return;
            }

            for (const event of events) {
                const card = makeElement(
                    "article",
                    null,
                    "pipeline-event-choice"
                );

                card.appendChild(
                    makeElement(
                        "h3",
                        event.event_name ||
                            `Event #${event.event_id}`
                    )
                );

                appendText(
                    card,
                    "Date",
                    formatDate(event.event_date)
                );

                appendText(
                    card,
                    "Organization",
                    event.college
                );

                appendText(
                    card,
                    "Location",
                    [event.city, event.state]
                        .filter(Boolean)
                        .join(", ")
                );

                card.appendChild(
                    makeButton(
                        "Open pipeline →",
                        "button button-primary",
                        () => {
                            window.location.href =
                                `/pipeline?event_id=${encodeURIComponent(
                                    event.event_id
                                )}`;
                        }
                    )
                );

                pickerList.appendChild(card);
            }
        } catch (error) {
            message.textContent =
                `Could not load events: ${error.message}`;
        }
    }

    function formatDate(value) {
        if (!value) return "Not specified";

        const parts = String(value)
            .slice(0, 10)
            .split("-")
            .map(Number);

        if (
            parts.length !== 3 ||
            parts.some(value => !value)
        ) {
            return String(value);
        }

        return new Date(
            parts[0],
            parts[1] - 1,
            parts[2]
        ).toLocaleDateString("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric"
        });
    }

    // ============================================================
    // SPONSOR CARD RENDERING
    // ============================================================

    function renderCandidates() {
        const query = (searchInput.value || "")
            .trim()
            .toLocaleLowerCase();

        const candidates = currentCandidates.filter(candidate => {
            const haystack = [
                candidate.company_name,
                candidate.industry,
                candidate.discovery_source,
                candidate.evidence_snippet,
                candidate.source_title,
                candidate.status
            ]
                .filter(Boolean)
                .join(" ")
                .toLocaleLowerCase();

            return haystack.includes(query);
        });

        candidateContainer.replaceChildren();

        setStat(
            "pipelineCandidateCount",
            currentCandidates.length
        );

        setStat(
            "pipelineSelectedCount",
            currentCandidates.filter(candidate =>
                ["SELECTED", "CONTACTED", "CLOSED"].includes(
                    String(candidate.status || "").toUpperCase()
                )
            ).length
        );

        if (!currentCandidates.length) {
            message.textContent =
                "No saved sponsor candidates yet. Run sponsor discovery to start researching companies.";

            return;
        }

        message.textContent =
            `Showing ${candidates.length} of ` +
            `${currentCandidates.length} candidate(s). ` +
            "All recommendations should be reviewed before outreach.";

        if (!candidates.length) {
            candidateContainer.appendChild(
                makeElement(
                    "p",
                    "No sponsors match the current search."
                )
            );

            return;
        }

        for (const [index, candidate] of candidates.entries()) {
            const card = makeElement(
                "article",
                null,
                "candidate-card pipeline-candidate-card"
            );

            card.appendChild(
                makeElement(
                    "h3",
                    candidate.company_name || "Unnamed company"
                )
            );

            const status = String(
                candidate.status || "DISCOVERED"
            ).toUpperCase();

            const metaRow = makeElement(
                "div",
                null,
                "candidate-meta-row"
            );

            metaRow.appendChild(
                makeElement(
                    "span",
                    status,
                    `pipeline-status-pill status-${status.toLowerCase()}`
                )
            );

            if (
                candidate.ai_score !== undefined &&
                candidate.ai_score !== null
            ) {
                metaRow.appendChild(
                    makeElement(
                        "span",
                        `Relevance ${candidate.ai_score}`,
                        "candidate-score"
                    )
                );
            }

            card.appendChild(metaRow);

            appendText(
                card,
                "Rank",
                candidate.human_rank ?? index + 1
            );

            appendText(card, "Industry", candidate.industry);

            appendText(
                card,
                "Discovery source",
                candidate.discovery_source
            );

            appendText(
                card,
                "Research evidence",
                candidate.evidence_snippet
            );

            appendLink(
                card,
                candidate.website,
                "Company website ↗"
            );

            appendLink(
                card,
                candidate.source_url,
                candidate.source_title ||
                    "Open research source ↗"
            );

            const actions = makeElement(
                "div",
                null,
                "candidate-actions"
            );

            // Selecting a sponsor remains a direct action.
            if (
                status === "SELECTED" ||
                status === "CONTACTED" ||
                status === "CLOSED"
            ) {
                actions.appendChild(
                    makeButton(
                        status === "SELECTED"
                            ? "✓ Selected"
                            : status,
                        "button button-secondary",
                        () => {},
                        { disabled: true }
                    )
                );
            } else {
                actions.appendChild(
                    makeButton(
                        "Select Sponsor",
                        "button button-primary",
                        () => selectSponsor(candidate)
                    )
                );
            }

            // All other actions open the shared modal.
            actions.appendChild(
                makeButton(
                    "Find Contacts",
                    "button button-secondary",
                    () => findContacts(candidate),
                    { disabled: status !== "SELECTED" }
                )
            );

            actions.appendChild(
                makeButton(
                    "View Contacts",
                    "button button-secondary",
                    () => viewContacts(candidate),
                    { disabled: status !== "SELECTED" }
                )
            );

            actions.appendChild(
                makeButton(
                    "Sponsor History",
                    "button button-secondary",
                    () => showSponsorHistory(candidate)
                )
            );

            actions.appendChild(
                makeButton(
                    "Outreach History",
                    "button button-secondary",
                    () => showOutreachHistory(candidate)
                )
            );

            actions.appendChild(
                makeButton(
                    "🗑",
                    "icon-button danger-icon sponsor-delete-button",
                    () => deleteSponsor(candidate),
                    {
                        title: "Delete sponsor from this event",
                        ariaLabel:
                            `Delete ${candidate.company_name} from this event`
                    }
                )
            );

            card.appendChild(actions);
            candidateContainer.appendChild(card);
        }
    }

    // ============================================================
    // LOAD PIPELINE
    // ============================================================

    const workflowStepLabels = [
    "Details",
    "Sponsors",
    "Selected",
    "Contacts",
    "Draft",
    "Sent"
];

function renderPipelineWorkflowProgress(steps) {
    const pills = document.getElementById("pipelineWorkflowPills");
    const count = document.getElementById("pipelineWorkflowCount");

    if (!pills || !count) return;

    pills.replaceChildren();

    for (const step of steps) {
        const chip = makeElement(
            "span",
            step.label,
            "pipeline-progress-chip"
        );

        if (step.complete) {
            chip.classList.add("is-complete");
        }

        chip.title = `${step.label}: ${
            step.complete ? "completed" : "pending"
        }`;

        pills.appendChild(chip);
    }

    const completed = steps.filter(
        step => step.complete
    ).length;

    count.textContent = `${completed}/6`;
}

async function updatePipelineWorkflowProgress(
    event,
    candidates,
    outreach
) {
    const selectedCandidates = candidates.filter(candidate =>
        ["SELECTED", "CONTACTED", "CLOSED"].includes(
            String(candidate.status || "").toUpperCase()
        )
    );

    let hasContacts = candidates.some(candidate => {
        const contactCount = Number(
            candidate.contact_count ??
            candidate.contacts_count ??
            candidate.contactCount ??
            candidate.contactsCount ??
            0
        );

        return contactCount > 0 ||
            (Array.isArray(candidate.contacts) &&
             candidate.contacts.length > 0);
    });

    // If the candidate data contains no contact count,
    // check the saved contacts through the existing API.
    if (!hasContacts && selectedCandidates.length > 0) {
        const results = await Promise.all(
            selectedCandidates.map(async candidate => {
                try {
                    const data = await api(
                        `/api/events/${activeEventId}/sponsors/${candidate.company_id}/contacts`
                    );

                    return Array.isArray(data.contacts) &&
                        data.contacts.length > 0;
                } catch (error) {
                    console.warn(
                        `Could not check contacts for sponsor ${candidate.company_id}:`,
                        error.message
                    );

                    return false;
                }
            })
        );

        hasContacts = results.some(Boolean);
    }

    const hasOutreach = outreach.length > 0;

    const hasSentEmail = outreach.some(
        item =>
            String(item.status || "").toUpperCase() === "SENT"
    );

    renderPipelineWorkflowProgress([
        {
            label: workflowStepLabels[0],
            complete: Boolean(event && event.event_name)
        },
        {
            label: workflowStepLabels[1],
            complete: candidates.length > 0
        },
        {
            label: workflowStepLabels[2],
            complete: selectedCandidates.length > 0
        },
        {
            label: workflowStepLabels[3],
            complete: hasContacts
        },
        {
            label: workflowStepLabels[4],
            complete: hasOutreach
        },
        {
            label: workflowStepLabels[5],
            complete: hasSentEmail
        }
    ]);
}

async function refreshPipelineWorkflowProgress() {
    if (!activeEvent || !activeEventId) return;

    try {
        const data = await api(
            `/api/events/${activeEventId}/outreach`
        );

        await updatePipelineWorkflowProgress(
            activeEvent,
            currentCandidates,
            data.outreach || []
        );
    } catch (error) {
        console.warn(
            "Could not refresh workflow progress:",
            error.message
        );
    }
}

    async function loadPipeline() {
        if (!activeEventId) {
            return chooseEventList();
        }
        if (pipelineStats) {
            pipelineStats.hidden = false;
        }
        refreshButton.disabled = true;
        discoveryButton.disabled = true;

        message.textContent =
            "Loading event and saved sponsor records…";

        try {
            const [eventData, candidateData, outreachData] =
                await Promise.all([
                    api(`/api/events/${activeEventId}`),
                    api(`/api/events/${activeEventId}/candidates`),
                    api(`/api/events/${activeEventId}/outreach`)
                ]);

            activeEvent = eventData.event;

            if (!activeEvent) {
                throw new Error(
                    "The requested event was not found."
                );
            }

            title.innerHTML =
                `${escapeHtml(activeEvent.event_name || "Event")} ` +
                "<span>Pipeline</span>";

            meta.textContent =
                `${activeEvent.college || "Organization not set"} · ` +
                `${[activeEvent.city, activeEvent.state]
                    .filter(Boolean)
                    .join(", ")} · ` +
                `${formatDate(activeEvent.event_date)}`;

            currentCandidates = Array.isArray(
                candidateData.candidates
            )
                ? candidateData.candidates
                : [];

            const outreach = outreachData.outreach || [];

            setStat(
                "pipelineDraftCount",
                outreach.filter(item =>
                    ["DRAFT", "SENDING", "FAILED"].includes(
                        String(item.status).toUpperCase()
                    )
                ).length
            );

            setStat(
                "pipelineSentCount",
                outreach.filter(item =>
                    String(item.status).toUpperCase() === "SENT"
                ).length
            );

            picker.hidden = true;
            discoveryButton.disabled = false;

            renderCandidates();

            await updatePipelineWorkflowProgress(
                activeEvent,
                currentCandidates,
                outreach
            );

        } catch (error) {
            console.error("Pipeline load failed:", error);

            message.textContent =
                `Could not load this event's pipeline: ${error.message}`;

        } finally {
            refreshButton.disabled = false;
            discoveryButton.disabled = !activeEventId;
        }
    }

    // ============================================================
    // SELECT AND REMOVE SPONSORS
    // ============================================================

    async function selectSponsor(candidate) {
        try {
            await api(
                `/api/events/${activeEventId}/sponsors/${candidate.company_id}/selection`,
                {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        status: "SELECTED"
                    })
                }
            );

            await loadPipeline();

        } catch (error) {
            window.alert(
                `Could not select sponsor: ${error.message}`
            );
        }
    }

    async function deleteSponsor(candidate) {
        const panel = openSponsorActionDialog(
            candidate,
            "Remove sponsor from event",
            "Confirm removal of this sponsor from the current event. The global company record will be retained."
        );

        panel.appendChild(
            makeElement(
                "p",
                "Removing a sponsor also removes event-specific research and contacts. Sponsors with existing email/outreach history may not be removable."
            )
        );

        sponsorActionFooter.replaceChildren();

        sponsorActionFooter.appendChild(
            makeButton(
                "Remove Sponsor",
                "button button-secondary danger-button",
                () => performDeleteSponsor(candidate)
            )
        );

        sponsorActionFooter.appendChild(
            makeButton(
                "Close",
                "button button-secondary",
                closeSponsorActionDialog
            )
        );
    }

    async function performDeleteSponsor(candidate) {
        sponsorActionResult.appendChild(
            makeElement("p", "Removing sponsor…")
        );

        try {
            await api(
                `/api/events/${activeEventId}/sponsors/${candidate.company_id}`,
                { method: "DELETE" }
            );

            closeSponsorActionDialog();

            message.textContent =
                `${candidate.company_name} was removed from this event.`;

            await loadPipeline();

        } catch (error) {
            sponsorActionResult.appendChild(
                makeElement(
                    "p",
                    `Could not remove sponsor: ${error.message}`,
                    "error"
                )
            );
        }
    }

    // ============================================================
    // CONTACT DISCOVERY AND SAVED CONTACTS
    // ============================================================

    async function findContacts(candidate) {
        const panel = openSponsorActionDialog(
            candidate,
            "Find business contacts",
            `Search for contacts at ${candidate.company_name || "this sponsor"}.`,
            { allowContactActions: true }
        );

        panel.appendChild(
            makeElement("p", "Finding contacts…")
        );

        try {
            const data = await api(
                `/api/events/${activeEventId}/sponsors/${candidate.company_id}/contacts/discover`,
                { method: "POST" }
            );

            renderContactResults(
                panel,
                candidate,
                data.contacts || [],
                data.message || "Contact discovery finished."
            );
            await refreshPipelineWorkflowProgress();

        } catch (error) {
            panel.appendChild(
                makeElement(
                    "p",
                    `Contact discovery failed: ${error.message}`,
                    "error"
                )
            );
        }
    }

    async function viewContacts(candidate) {
        const panel = openSponsorActionDialog(
            candidate,
            "Business contacts",
            `Saved contact records for ${candidate.company_name || "this sponsor"}.`,
            { allowContactActions: true }
        );

        panel.appendChild(
            makeElement("p", "Loading saved contacts…")
        );

        try {
            const data = await api(
                `/api/events/${activeEventId}/sponsors/${candidate.company_id}/contacts`
            );

            renderContactResults(
                panel,
                candidate,
                data.contacts || [],
                "Loaded saved contact records."
            );

        } catch (error) {
            panel.appendChild(
                makeElement(
                    "p",
                    `Could not load contacts: ${error.message}`,
                    "error"
                )
            );
        }
    }

    function renderContactResults(
        panel,
        candidate,
        contacts,
        intro
    ) {
        panel.replaceChildren();

        panel.appendChild(
            makeElement("p", intro || "")
        );

        panel.appendChild(
            makeElement(
                "h3",
                `Business Contacts (${contacts.length})`
            )
        );

        if (!contacts.length) {
            panel.appendChild(
                makeElement(
                    "p",
                    "No contacts were found. Check the company's official website or retry later."
                )
            );

            return;
        }

        const ranked = [...contacts].sort(
            (a, b) =>
                Number(a.priority_rank || 999) -
                Number(b.priority_rank || 999)
        );

        for (const contact of ranked) {
            const box = makeElement(
                "article",
                null,
                "contact-card"
            );

            box.appendChild(
                makeElement(
                    "h4",
                    contact.full_name ||
                    contact.email_address ||
                    "Contact"
                )
            );

            appendText(box, "Email", contact.email_address);
            appendText(box, "Role", contact.job_title);
            appendText(box, "Department", contact.department);

            appendText(
                box,
                "Verification",
                contact.verification_status || "Not verified"
            );

            appendText(
                box,
                "Why selected",
                contact.selection_reason
            );

            appendLink(
                box,
                contact.source_url,
                "Contact source ↗"
            );

            const hasEmail =
                typeof contact.email_address === "string" &&
                contact.email_address.trim().length > 0;

            box.appendChild(
                makeButton(
                    "Generate Email Draft",
                    "button button-primary",
                    () => generateDraft(candidate, contact),
                    {
                        disabled: !hasEmail,
                        title: hasEmail
                            ? "Generate an email draft for this address."
                            : "An email address is required."
                    }
                )
            );

            if (!hasEmail) {
                box.appendChild(
                    makeElement(
                        "small",
                        "Cannot generate a draft because no email address was found."
                    )
                );
            }

            panel.appendChild(box);
        }
    }

    // ============================================================
    // EMAIL DRAFT GENERATION
    // ============================================================

    async function generateDraft(candidate, contact) {
        closeSponsorActionDialog();

        draftStatus.textContent =
            "Generating and saving a draft…";

        subjectInput.value = "";
        bodyInput.value = "";
        recipientCheck.checked = false;

        sendDraftButton.disabled = true;
        saveDraftButton.disabled = true;

        try {
            const data = await api(
                `/api/events/${activeEventId}/sponsors/${candidate.company_id}/contacts/${contact.contact_id}/draft`,
                { method: "POST" }
            );

            currentDraft = {
                ...data,
                company_id: candidate.company_id,
                recipient_email:
                    data.recipient_email ||
                    contact.email_address
            };

            $("emailDraftSender").textContent =
                currentDraft.sender_email ||
                "Email account not configured";

            $("emailDraftRecipient").textContent =
                currentDraft.recipient_email;

            $("emailDraftSubtitle").textContent =
                `${candidate.company_name} · Draft #${currentDraft.email_id}. ` +
                "Nothing is sent until you explicitly approve it.";

            subjectInput.value = currentDraft.subject || "";
            bodyInput.value = currentDraft.body || "";

            draftStatus.textContent =
                "Review the sender and recipient, edit the subject/body, and save before sending.";

            isDraftSaved = true;

            draftDialog.showModal();

        } catch (error) {
            window.alert(
                `Could not generate draft: ${error.message}`
            );

        } finally {
            saveDraftButton.disabled = false;
        }
    }

    async function persistDraft() {
        if (!currentDraft) {
            throw new Error("No draft is open.");
        }

        const subject = subjectInput.value.trim();
        const body = bodyInput.value.trim();

        if (!subject || !body) {
            throw new Error(
                "Subject and email body are required."
            );
        }

        await api(
            `/api/events/${activeEventId}/outreach/${currentDraft.email_id}`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    subject,
                    body
                })
            }
        );

        currentDraft.subject = subject;
        currentDraft.body = body;

        isDraftSaved = true;

        return true;
    }

    async function saveDraft() {
        saveDraftButton.disabled = true;
        draftStatus.textContent = "Saving draft…";

        try {
            await persistDraft();

            draftStatus.textContent =
                "Draft saved. It has not been sent.";

            isDraftSaved = true;

            await loadPipeline();

        } catch (error) {
            draftStatus.textContent =
                `Could not save draft: ${error.message}`;

        } finally {
            saveDraftButton.disabled = false;
        }
    }

    async function sendDraft() {
        if (!currentDraft) return;

        if (!recipientCheck.checked) {
            draftStatus.textContent =
                "Confirm that you checked the recipient address before sending.";

            return;
        }

        const sender =
            currentDraft.sender_email ||
            "the configured SponsyBot SMTP sender";

        const confirmed = window.confirm(
            `Confirm email delivery\n\n` +
            `From: ${sender}\n` +
            `To: ${currentDraft.recipient_email}\n` +
            `Subject: ${subjectInput.value.trim()}\n\n` +
            "Send this reviewed email now?"
        );

        if (!confirmed) return;

        sendDraftButton.disabled = true;
        saveDraftButton.disabled = true;

        draftStatus.textContent =
            "Saving your latest edits before sending…";

        try {
            await persistDraft();

            draftStatus.textContent =
                `Sending to ${currentDraft.recipient_email}…`;

            const result = await api(
                `/api/events/${activeEventId}/outreach/${currentDraft.email_id}/send`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        confirm_send: true,
                        confirm_recipient: true
                    })
                }
            );

            draftStatus.textContent =
                `${result.message || "Email send request completed."} ` +
                `Status: ${result.status || "updated"}.`;

            window.alert(
                `SponsyBot send result\n\n` +
                `To: ${currentDraft.recipient_email}\n` +
                `Status: ${result.status || "unknown"}\n\n` +
                `${result.message || "Check outreach history for the final record."}`
            );

            draftDialog.close();
            currentDraft = null;

            await loadPipeline();

        } catch (error) {
            draftStatus.textContent =
                `Send result needs review: ${error.message}. ` +
                "Check Outreach History before retrying to avoid duplicate emails.";

            sendDraftButton.disabled = false;
            saveDraftButton.disabled = false;
        }
    }

    // ============================================================
    // SPONSOR HISTORY
    // ============================================================

    async function showSponsorHistory(candidate) {
        const panel = openSponsorActionDialog(
            candidate,
            "Sponsor history",
            `Previous appearances and sponsorship evidence for ${candidate.company_name || "this sponsor"}.`
        );

        panel.appendChild(
            makeElement("p", "Loading sponsor history…")
        );

        try {
            const data = await api(
                `/api/events/${activeEventId}/sponsors/${candidate.company_id}/history`
            );

            const history = data.history || data;

            panel.replaceChildren();

            panel.appendChild(
                makeElement(
                    "h3",
                    "Previous appearances in your events"
                )
            );

            if (!history.previous_events?.length) {
                panel.appendChild(
                    makeElement(
                        "p",
                        "No previous appearances found in your workspace."
                    )
                );
            }

            for (const item of history.previous_events || []) {
                const row = makeElement(
                    "article",
                    null,
                    "history-entry"
                );

                appendText(row, "Event", item.event_name);
                appendText(row, "Date", item.event_date);
                appendText(row, "Status", item.status);

                panel.appendChild(row);
            }

            panel.appendChild(
                makeElement(
                    "h3",
                    "Sponsorship-related public evidence"
                )
            );

            if (!history.sponsorship_evidence?.length) {
                panel.appendChild(
                    makeElement(
                        "p",
                        "No sources classified as sponsorship evidence were found. This does not prove the company has never sponsored an event."
                    )
                );
            }

            for (
                const item of history.sponsorship_evidence || []
            ) {
                const row = makeElement(
                    "article",
                    null,
                    "history-entry"
                );

                appendText(row, "Source", item.source_title);
                appendText(row, "Evidence", item.evidence_snippet);

                appendLink(
                    row,
                    item.source_url,
                    "Open source ↗"
                );

                panel.appendChild(row);
            }

        } catch (error) {
            panel.appendChild(
                makeElement(
                    "p",
                    `Could not load sponsor history: ${error.message}`,
                    "error"
                )
            );
        }
    }

    // ============================================================
    // OUTREACH HISTORY
    // ============================================================

    async function showOutreachHistory(candidate) {
        const panel = openSponsorActionDialog(
            candidate,
            "Email and outreach history",
            `Drafts and delivery records for ${candidate.company_name || "this sponsor"}.`
        );

        panel.appendChild(
            makeElement("p", "Loading outreach history…")
        );

        try {
            const data = await api(
                `/api/events/${activeEventId}/outreach`
            );

            const history = (data.outreach || []).filter(
                item =>
                    Number(item.company_id) ===
                    Number(candidate.company_id)
            );

            panel.replaceChildren();

            panel.appendChild(
                makeElement(
                    "h3",
                    `Outreach records (${history.length})`
                )
            );

            if (!history.length) {
                panel.appendChild(
                    makeElement(
                        "p",
                        "No draft or send records exist for this sponsor yet."
                    )
                );

                return;
            }

            for (const item of history) {
                const record = makeElement(
                    "article",
                    null,
                    "history-entry outreach-record"
                );

                record.appendChild(
                    makeElement(
                        "h4",
                        `${cleanHistoryStatus(item.status)} · ` +
                        `${item.recipient_email || "No recipient"}`
                    )
                );

                appendText(record, "Subject", item.subject);
                appendText(record, "Recipient", item.recipient_email);
                appendText(record, "Status", item.status);
                appendText(record, "Created", item.created_at);
                appendText(record, "Approved", item.approved_at);
                appendText(record, "Sent", item.sent_at);
                appendText(record, "Error", item.error_message);
                appendText(record, "Body", item.body);

                if (
                    String(item.status || "").toUpperCase() === "DRAFT"
                ) {
                    record.appendChild(
                        makeButton(
                            "Open draft in Email Studio",
                            "button button-primary",
                            () => {
                                window.location.href =
                                    `/email-studio?email_id=${encodeURIComponent(
                                        item.email_id
                                    )}`;
                            }
                        )
                    );

                } else if (
                    String(item.status || "").toUpperCase() === "SENT"
                ) {
                    record.appendChild(
                        makeButton(
                            "Sent",
                            "button button-secondary",
                            () => {},
                            { disabled: true }
                        )
                    );
                }

                panel.appendChild(record);
            }

        } catch (error) {
            panel.appendChild(
                makeElement(
                    "p",
                    `Could not load outreach history: ${error.message}`,
                    "error"
                )
            );
        }
    }

    function cleanHistoryStatus(status) {
        return String(status || "UNKNOWN").toUpperCase();
    }

    // ============================================================
    // RUN SPONSOR DISCOVERY
    // ============================================================

    async function runDiscovery() {
        if (!activeEventId) return;

        discoveryButton.disabled = true;

        message.textContent =
            "Sponsor discovery is running. Existing saved candidates will be retained.";

        try {
            const result = await api(
                `/api/events/${activeEventId}/discover`,
                { method: "POST" }
            );

            message.textContent =
                result.message ||
                `Discovery finished: ${result.saved_count ?? 0} saved candidate(s).`;

            await loadPipeline();

        } catch (error) {
            message.textContent =
                `Discovery failed: ${error.message}`;

        } finally {
            discoveryButton.disabled = false;
        }
    }

    // ============================================================
    // EVENT LISTENERS
    // ============================================================

    refreshButton.addEventListener(
        "click",
        loadPipeline
    );

    discoveryButton.addEventListener(
        "click",
        runDiscovery
    );

    searchInput.addEventListener(
        "input",
        renderCandidates
    );

    recipientCheck.addEventListener("change", () => {
        sendDraftButton.disabled =
            !recipientCheck.checked;
    });

    subjectInput.addEventListener("input", () => {
        isDraftSaved = false;

        draftStatus.textContent =
            "Draft edited. Save before sending; sending will save automatically.";
    });

    bodyInput.addEventListener("input", () => {
        isDraftSaved = false;

        draftStatus.textContent =
            "Draft edited. Save before sending; sending will save automatically.";
    });

    saveDraftButton.addEventListener(
        "click",
        saveDraft
    );

    sendDraftButton.addEventListener(
        "click",
        sendDraft
    );

    function closeDraft() {
        if (draftDialog.open) {
            draftDialog.close();
        }
    }

    $("closeEmailDraft").addEventListener(
        "click",
        closeDraft
    );

    $("cancelEmailDraft").addEventListener(
        "click",
        closeDraft
    );

    draftDialog.addEventListener("close", () => {
        currentDraft = null;
        recipientCheck.checked = false;
        sendDraftButton.disabled = true;
    });

    // Load the current event's saved sponsors.
    loadPipeline();

})();
