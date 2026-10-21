(() => {
    "use strict";

    const grid = document.getElementById("aiUsageGrid");
    const notice = document.getElementById("usageNotice");
    const refreshButton = document.getElementById("refreshUsage");
    let countdownTimer = null;

    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, character => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
        })[character]);
    }

    function formatNumber(value) {
        return Number(value).toLocaleString("en-IN");
    }

    function getCountdown(resetAt) {
        const difference = new Date(resetAt).getTime() - Date.now();
        if (!Number.isFinite(difference) || difference <= 0) return "Reset time reached; refresh to reload usage.";
        const totalSeconds = Math.floor(difference / 1000);
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const parts = [];
        if (days) parts.push(`${days}d`);
        parts.push(`${String(hours).padStart(2, "0")}h`, `${String(minutes).padStart(2, "0")}m`, `${String(seconds).padStart(2, "0")}s`);
        return parts.join(" ");
    }

    function providerStatus(provider) {
        if (provider.status === "unconfigured") return { label: "Limit not configured", className: "status-neutral" };
        if (provider.status === "exhausted" || (Number.isFinite(provider.remaining) && provider.remaining <= 0)) {
            return { label: "Configured limit reached", className: "status-warning" };
        }
        if (String(provider.source_label || "").startsWith("Live Hunter usage API")) {
            return { label: "Live account usage", className: "status-ok" };
        }
        return { label: "App-tracked estimate", className: "status-neutral" };
    }

    function renderProviders(providers, trackingReady) {
        if (countdownTimer) window.clearInterval(countdownTimer);
        grid.replaceChildren();

        if (!Array.isArray(providers) || providers.length === 0) {
            notice.textContent = "The usage API returned no provider data.";
            return;
        }

        notice.textContent = trackingReady
            ? "Provider usage data loaded. Gemini/Tavily values are app-tracked; Hunter values are live when its usage API is configured. Verify quota state in each provider dashboard."
            : "Usage API connected, but provider-call instrumentation is not marked complete. Remaining quotas are hidden rather than guessed.";

        for (const provider of providers) {
            const card = document.createElement("article");
            card.className = "ai-usage-card";
            const status = providerStatus(provider);
            const limitConfigured = Number.isFinite(provider.limit);
            const used = Number.isFinite(provider.used) ? provider.used : 0;
            const remaining = Number.isFinite(provider.remaining) ? Math.max(0, provider.remaining) : null;
            const percent = limitConfigured && provider.limit > 0
                ? Math.min(100, Math.max(0, used / provider.limit * 100))
                : 0;
            const isExhausted = status.className === "status-warning";

            card.innerHTML = `
                <div class="usage-card-top">
                    <div class="usage-provider-icon" aria-hidden="true">${escapeHtml(provider.icon || "✦")}</div>
                    <span class="usage-status ${status.className}">${escapeHtml(status.label)}</span>
                </div>
                <h2>${escapeHtml(provider.name || provider.id)}</h2>
                <p class="usage-provider-description">${escapeHtml(provider.description || "Provider usage")}</p>
                <div class="usage-primary-number">${formatNumber(used)} <span>${escapeHtml(provider.unit || "calls")} used</span></div>
                <div class="usage-progress-track" aria-label="Configured quota usage">
                    <div class="usage-progress-fill" style="width:${percent}%"></div>
                </div>
                <div class="usage-metrics">
                    <div><span>Configured limit</span><strong>${limitConfigured ? formatNumber(provider.limit) : "Not set"}</strong></div>
                    <div><span>${escapeHtml(provider.remaining_label || "Calculated remaining")}</span><strong>${remaining === null ? "Unknown" : formatNumber(remaining)}</strong></div>
                    <div><span>Period</span><strong>${escapeHtml(provider.period_label || provider.period || "Tracked")}</strong></div>
                </div>
                ${provider.reset_at ? `<div class="usage-reset ${isExhausted ? "usage-reset-warning" : ""}"><span>${isExhausted ? "Estimated reset in" : "Next reset"}</span><strong data-reset-at="${escapeHtml(provider.reset_at)}">${escapeHtml(getCountdown(provider.reset_at))}</strong><small>${escapeHtml(provider.reset_note || "Based on configured reset schedule")}</small></div>` : `<div class="usage-reset"><span>Reset timer</span><strong>Not available</strong><small>Configure the provider's reset cycle in the backend.</small></div>`}
                <p class="usage-source">${escapeHtml(provider.source_label || "Tracked by SponsyBot")}</p>
            `;
            grid.appendChild(card);
        }

        const updateCountdowns = () => {
            grid.querySelectorAll("[data-reset-at]").forEach(element => {
                element.textContent = getCountdown(element.getAttribute("data-reset-at"));
            });
        };
        updateCountdowns();
        countdownTimer = window.setInterval(updateCountdowns, 1000);
    }

    async function loadUsage() {
        refreshButton.disabled = true;
        notice.textContent = "Loading usage data…";
        try {
            const response = await fetch("/api/ai-usage", { headers: { "Accept": "application/json" } });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const detail = typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`;
                throw new Error(detail);
            }
            renderProviders(data.providers || [], data.tracking_ready === true);
        } catch (error) {
            console.error("Could not load AI usage:", error);
            grid.innerHTML = `
                <article class="ai-usage-card usage-connection-error">
                    <div class="usage-card-top"><div class="usage-provider-icon">!</div><span class="usage-status status-warning">Backend connection required</span></div>
                    <h2>Live usage is not connected yet</h2>
                    <p>The page is ready, but <code>/api/ai-usage</code> did not return tracked provider data.</p>
                    <p>To avoid showing invented remaining limits, no quota numbers are displayed until the backend usage endpoint and provider-call tracking are connected.</p>
                    <small>Details: ${escapeHtml(error.message)}</small>
                </article>`;
            notice.textContent = "Usage integration incomplete. See the backend integration guide included in the project ZIP.";
        } finally {
            refreshButton.disabled = false;
        }
    }

    refreshButton.addEventListener("click", loadUsage);
    loadUsage();
})();
