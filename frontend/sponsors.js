

const directoryPanel = document.getElementById("directoryPanel");
const outreachPanel = document.getElementById("outreachPanel");
const directoryMessage = document.getElementById("directoryMessage");
const sponsorDirectory = document.getElementById("sponsorDirectory");
const companyCount = document.getElementById("companyCount");

const companySearch = document.getElementById("companySearch");
const industryFilter = document.getElementById("industryFilter");
const companySort = document.getElementById("companySort");

const outreachSearch = document.getElementById("outreachSearch");
const outreachStatus = document.getElementById("outreachStatus");
const outreachSort = document.getElementById("outreachSort");
const outreachMessage = document.getElementById("outreachMessage");
const outreachTableBody = document.getElementById("outreachTableBody");
const outreachCount = document.getElementById("outreachCount");
const sentCount = document.getElementById("sentCount");

const companyHistoryPanel = document.getElementById("companyHistoryPanel");
const historyTitle = document.getElementById("historyTitle");
const historyMessage = document.getElementById("historyMessage");
const companyHistoryContent = document.getElementById("companyHistoryContent");

const outreachDetailPanel = document.getElementById("outreachDetailPanel");
const outreachDetailContent = document.getElementById("outreachDetailContent");

let currentSponsors = [];
let currentOutreach = [];

function makeElement(tag, text, className) {
    const element = document.createElement(tag);

    if (text !== null && text !== undefined) {
        element.textContent = String(text);
    }

    if (className) {
        element.className = className;
    }

    return element;
}

function addText(parent, label, value) {
    if (value === null || value === undefined || value === "") return;

    const paragraph = document.createElement("p");
    const strong = makeElement("strong", `${label}: `);

    paragraph.appendChild(strong);
    paragraph.appendChild(document.createTextNode(String(value)));
    parent.appendChild(paragraph);
}

function makeButton(label, handler, className = "button button-secondary") {
    const button = makeElement("button", label, className);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
}

function makeSourceLink(parent, url, label = "Open source") {
    if (!url) return;

    try {
        const parsed = new URL(url);

        if (!["https:", "http:"].includes(parsed.protocol)) return;

        const anchor = makeElement("a", label);
        anchor.href = parsed.href;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        parent.appendChild(anchor);
    } catch {
        // Ignore invalid source URLs.
    }
}

async function readJsonResponse(response) {
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(
            typeof data.detail === "string"
                ? data.detail
                : `HTTP ${response.status}`
        );
    }

    return data;
}

function formatDate(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short"
    });
}


// ---------- Navigation between tabs ----------

document.getElementById("directoryTab").addEventListener("click", () => {
    directoryPanel.hidden = false;
    outreachPanel.hidden = true;

    document.getElementById("directoryTab").classList.add("active");
    document.getElementById("directoryTab").setAttribute("aria-selected", "true");

    document.getElementById("outreachTab").classList.remove("active");
    document.getElementById("outreachTab").setAttribute("aria-selected", "false");

    loadDirectory();
});

document.getElementById("outreachTab").addEventListener("click", () => {
    directoryPanel.hidden = true;
    outreachPanel.hidden = false;

    document.getElementById("outreachTab").classList.add("active");
    document.getElementById("outreachTab").setAttribute("aria-selected", "true");

    document.getElementById("directoryTab").classList.remove("active");
    document.getElementById("directoryTab").setAttribute("aria-selected", "false");

    loadOutreach();
});


// ---------- Sponsor directory ----------

async function loadDirectory() {
    directoryMessage.textContent = "Loading sponsor directory...";

    const params = new URLSearchParams({
        search: companySearch.value.trim(),
        industry: industryFilter.value,
        sort_by: companySort.value
    });

    try {
        const response = await fetch(`/api/sponsors?${params}`);
        const data = await readJsonResponse(response);

        currentSponsors = data.sponsors || [];
        companyCount.textContent = data.count ?? currentSponsors.length;

        // Update available industry filters while preserving the selection.
        const selectedIndustry = industryFilter.value;
        industryFilter.replaceChildren();

        industryFilter.appendChild(
            makeElement("option", "All industries")
        );
        industryFilter.options[0].value = "";

        for (const industry of data.industries || []) {
            const option = makeElement("option", industry);
            option.value = industry;
            industryFilter.appendChild(option);
        }

        industryFilter.value = selectedIndustry;

        renderSponsorDirectory(currentSponsors);
    } catch (error) {
        console.error("Sponsor directory failed:", error);
        directoryMessage.textContent =
            `Could not load sponsors: ${error.message}`;
        sponsorDirectory.replaceChildren();
    }
}

function renderSponsorDirectory(sponsors) {
    sponsorDirectory.replaceChildren();

    if (!sponsors.length) {
        directoryMessage.textContent =
            "No discovered companies match these filters.";
        return;
    }

    directoryMessage.textContent =
        `Showing ${sponsors.length} distinct company record(s).`;

    // Group companies by industry without duplicating them in the list.
    const groups = new Map();

    for (const sponsor of sponsors) {
        const industry = sponsor.industry || "Unclassified industry";

        if (!groups.has(industry)) {
            groups.set(industry, []);
        }

        groups.get(industry).push(sponsor);
    }

    for (const [industry, companies] of groups) {
        const section = document.createElement("section");
        section.className = "industry-section";

        const heading = makeElement(
            "h2",
            `${industry} (${companies.length})`,
            "industry-heading"
        );
        section.appendChild(heading);

        const grid = document.createElement("div");
        grid.className = "sponsor-directory-grid";

        for (const sponsor of companies) {
            const card = document.createElement("article");
            card.className = "sponsor-directory-card";

            card.appendChild(
                makeElement("h3", sponsor.company_name || "Unnamed company")
            );

            addText(card, "Company ID", sponsor.company_id);
            addText(card, "Website", sponsor.website);
            addText(card, "Events associated", sponsor.event_count);
            addText(card, "Latest event date", sponsor.latest_event_date);
            addText(card, "Statuses across events", sponsor.statuses);
            addText(
                card,
                "Sponsorship-related research records",
                sponsor.sponsorship_evidence_count
            );

            makeSourceLink(card, sponsor.website, "Visit company website");

            card.appendChild(
                makeButton(
                    "View History & Evidence",
                    () => loadCompanyHistory(sponsor),
                    "button button-primary"
                )
            );

            grid.appendChild(card);
        }

        section.appendChild(grid);
        sponsorDirectory.appendChild(section);
    }
}

async function loadCompanyHistory(sponsor) {
    companyHistoryPanel.hidden = false;
    historyTitle.textContent = `History: ${sponsor.company_name}`;
    historyMessage.textContent = "Loading company history...";
    companyHistoryContent.replaceChildren();

    companyHistoryPanel.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

    try {
        const response = await fetch(
            `/api/sponsors/${sponsor.company_id}/history`
        );

        const data = await readJsonResponse(response);

        historyMessage.textContent =
            "Event appearances and research evidence are shown separately.";

        const eventsHeading = makeElement(
            "h3",
            "Appearances in your SponsyBot events"
        );
        companyHistoryContent.appendChild(eventsHeading);

        if (!data.event_history?.length) {
            companyHistoryContent.appendChild(
                makeElement("p", "No event appearances were found.")
            );
        }

        for (const event of data.event_history || []) {
            const entry = document.createElement("article");
            entry.className = "history-card";

            addText(entry, "Event", event.event_name);
            addText(entry, "Event ID", event.event_id);
            addText(entry, "Date", event.event_date);
            addText(entry, "Event type", event.event_type);
            addText(entry, "Discovery source", event.discovery_source);
            addText(entry, "Workflow status", event.status);

            companyHistoryContent.appendChild(entry);
        }

        const evidenceHeading = makeElement(
            "h3",
            "Sponsorship-related research evidence"
        );
        companyHistoryContent.appendChild(evidenceHeading);

        if (!data.sponsorship_evidence?.length) {
            companyHistoryContent.appendChild(
                makeElement(
                    "p",
                    "No sponsorship-related research records were found. This does not mean the company has never sponsored an event."
                )
            );
        }

        for (const evidence of data.sponsorship_evidence || []) {
            const entry = document.createElement("article");
            entry.className = "history-card";

            addText(entry, "Source title", evidence.source_title);
            addText(entry, "Evidence", evidence.evidence_snippet);
            addText(entry, "Research type", evidence.research_type);
            addText(entry, "Recorded event", evidence.research_event_name);

            makeSourceLink(entry, evidence.source_url);
            companyHistoryContent.appendChild(entry);
        }
    } catch (error) {
        historyMessage.textContent =
            `Could not load company history: ${error.message}`;
    }
}

document.getElementById("closeHistory").addEventListener("click", () => {
    companyHistoryPanel.hidden = true;
});

companySearch.addEventListener("input", loadDirectory);
industryFilter.addEventListener("change", loadDirectory);
companySort.addEventListener("change", loadDirectory);


// ---------- Outreach history ----------

async function loadOutreach() {
    outreachMessage.textContent = "Loading outreach records...";

    const params = new URLSearchParams({
        search: outreachSearch.value.trim(),
        status: outreachStatus.value,
        sort_by: outreachSort.value
    });

    try {
        const response = await fetch(`/api/outreach?${params}`);
        const data = await readJsonResponse(response);

        currentOutreach = data.outreach || [];

        outreachCount.textContent = data.count ?? currentOutreach.length;
        sentCount.textContent = currentOutreach.filter(
            record => record.status === "SENT"
        ).length;

        renderOutreach(currentOutreach);
    } catch (error) {
        console.error("Outreach history failed:", error);
        outreachMessage.textContent =
            `Could not load outreach history: ${error.message}`;
        outreachTableBody.replaceChildren();
    }
}

function renderOutreach(records) {
    outreachTableBody.replaceChildren();

    outreachMessage.textContent =
        `Showing ${records.length} outreach record(s).`;

    if (!records.length) {
        outreachMessage.textContent =
            "No draft or send records match the selected filters.";
        return;
    }

    for (const record of records) {
        const row = document.createElement("tr");

        const fields = [
            formatDate(record.created_at),
            record.company_name || "—",
            record.event_name || "—",
            record.recipient_email || "—",
            record.subject || "—",
            record.status || "—"
        ];

        for (const value of fields) {
            row.appendChild(makeElement("td", value));
        }

        const detailCell = document.createElement("td");

        detailCell.appendChild(
            makeButton(
                "View",
                () => showOutreachRecord(record),
                "button button-secondary"
            )
        );

        row.appendChild(detailCell);
        outreachTableBody.appendChild(row);
    }
}

function showOutreachRecord(record) {
    outreachDetailPanel.hidden = false;
    outreachDetailContent.replaceChildren();

    addText(outreachDetailContent, "Company", record.company_name);
    addText(outreachDetailContent, "Event", record.event_name);
    addText(outreachDetailContent, "Recipient", record.recipient_email);
    addText(outreachDetailContent, "Recipient name", record.recipient_name);
    addText(outreachDetailContent, "Subject", record.subject);
    addText(outreachDetailContent, "Status", record.status);
    addText(outreachDetailContent, "Created", formatDate(record.created_at));
    addText(outreachDetailContent, "Approved", formatDate(record.approved_at));
    addText(outreachDetailContent, "Sent", formatDate(record.sent_at));
    addText(outreachDetailContent, "Send error", record.error_message);

    const bodyHeading = makeElement("h3", "Email Body");
    outreachDetailContent.appendChild(bodyHeading);

    const body = makeElement("pre", record.body || "");
    body.className = "email-history-body";
    outreachDetailContent.appendChild(body);

    addText(
        outreachDetailContent,
        "Delivery note",
        record.status === "SENT"
            ? "The SMTP server accepted this email. Delivery and replies are not confirmed by this status."
            : "This record is not marked SENT."
    );

    outreachDetailPanel.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

document.getElementById("closeOutreachDetail")
    .addEventListener("click", () => {
        outreachDetailPanel.hidden = true;
    });

outreachSearch.addEventListener("input", loadOutreach);
outreachStatus.addEventListener("change", loadOutreach);
outreachSort.addEventListener("change", loadOutreach);


// ---------- Initial load ----------

const pagePath = window.location.pathname;
if (pagePath === "/outreach" || pagePath === "/email-studio") {
    directoryPanel.hidden = true;
    outreachPanel.hidden = false;
    document.getElementById("outreachTab").classList.add("active");
    document.getElementById("outreachTab").setAttribute("aria-selected", "true");
    document.getElementById("directoryTab").classList.remove("active");
    document.getElementById("directoryTab").setAttribute("aria-selected", "false");
}
loadDirectory();
loadOutreach();
