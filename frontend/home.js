(() => {
    "use strict";
    const totalEvents = document.getElementById("homeTotalEvents");
    if (!totalEvents) return;
    const companies = document.getElementById("homeCompaniesFound");
    const pipeline = document.getElementById("homePipelineCount");
    const sent = document.getElementById("homeEmailsSent");
    const recentBody = document.getElementById("homeRecentEvents");
    const message = document.getElementById("homeEventsMessage");
    const search = document.getElementById("globalSearchBox");

    if (search) {
        search.addEventListener("keydown", event => {
            if (event.key !== "Enter") return;
            const term = search.value.trim();
            if (term) window.location.href = `/events?search=${encodeURIComponent(term)}`;
        });
    }

    function addCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value == null || value === "" ? "—" : String(value);
        row.appendChild(cell);
        return cell;
    }

    async function getJson(url) {
        const response = await fetch(url, { headers: { "Accept": "application/json" } });
        if (response.status === 401) {
            window.location.replace("/login");
            throw new Error("Sign in required.");
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        return data;
    }

    function formatDate(value) {
        if (!value) return "—";
        const text = String(value).slice(0, 10);
        const parts = text.split("-").map(Number);
        if (parts.length !== 3 || parts.some(n => !n)) return text;
        return new Date(parts[0], parts[1] - 1, parts[2]).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    }

    async function loadDashboard() {
        try {
            const [eventData, sponsorData, outreachData, progressData] = await Promise.all([
                getJson("/api/events"),
                getJson("/api/sponsors"),
                getJson("/api/outreach"),
                getJson("/api/event-progress")
            ]);
            const events = Array.isArray(eventData.events) ? eventData.events : [];
            const sponsorRows = Array.isArray(sponsorData.sponsors) ? sponsorData.sponsors : [];
            const outreach = Array.isArray(outreachData.outreach) ? outreachData.outreach : [];
            const progress = Array.isArray(progressData.progress) ? progressData.progress : [];
            const pipelineCompanies = sponsorRows.filter(row => /SELECTED|CONTACTED|CLOSED/i.test(String(row.statuses || ""))).length;
            totalEvents.textContent = String(events.length);
            companies.textContent = String(sponsorData.count ?? sponsorRows.length);
            pipeline.textContent = String(pipelineCompanies);
            sent.textContent = String(outreach.filter(item => String(item.status).toUpperCase() === "SENT").length);

            const progressMap = new Map(progress.map(item => [String(item.event_id), item]));
            recentBody.replaceChildren();
            const recent = [...events].sort((a, b) => Number(b.event_id) - Number(a.event_id)).slice(0, 5);
            message.textContent = recent.length ? `Showing ${recent.length} recent event(s).` : "No events yet. Create your first event to begin.";
            for (const event of recent) {
                const row = document.createElement("tr");
                const eventCell = addCell(row, event.event_name);
                const link = document.createElement("a");
                link.href = `/pipeline?event_id=${encodeURIComponent(event.event_id)}`;
                link.className = "table-link";
                link.textContent = event.event_name || `Event #${event.event_id}`;
                eventCell.replaceChildren(link);
                addCell(row, formatDate(event.event_date));
                addCell(row, Number(event.expected_participants || 0).toLocaleString("en-IN"));
                addCell(row, event.event_type);
                const item = progressMap.get(String(event.event_id)) || {};
                const done = [item.details_complete, Number(item.sponsor_count || 0) > 0, Number(item.selected_sponsor_count || 0) > 0, Number(item.contact_count || 0) > 0, Number(item.email_count || 0) > 0, Number(item.sent_email_count || 0) > 0].filter(Boolean).length;
                addCell(row, `${done}/6 stages complete`);
                recentBody.appendChild(row);
            }
        } catch (error) {
            console.error("Dashboard loading failed:", error);
            message.textContent = `Some dashboard data could not be loaded: ${error.message}`;
        }
    }

    loadDashboard();
    window.setInterval(() => {
        if (document.visibilityState === "visible") loadDashboard();
    }, 30000);
})();
