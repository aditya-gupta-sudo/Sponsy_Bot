(() => {
    "use strict";
    const sidebar = document.getElementById("app-sidebar");
    if (!sidebar) return;

    sidebar.innerHTML = `
        <a class="brand" href="/" aria-label="SponsyBot Home">
            <span class="brand-mark" aria-hidden="true">✦</span><span>SponsyBot</span>
        </a>
        <p class="nav-caption">WORKSPACE</p>
        <nav class="navigation" aria-label="Main navigation">
            <a class="nav-link" href="/" data-nav-path="/"><span class="nav-icon" aria-hidden="true">⌂</span><span>Home</span></a>
            <a class="nav-link" href="/ai-usage" data-nav-path="/ai-usage"><span class="nav-icon" aria-hidden="true">◴</span><span>AI Usage &amp; Limits</span></a>
            <a class="nav-link" href="/events" data-nav-path="/events"><span class="nav-icon" aria-hidden="true">▦</span><span>Events</span></a>
            <a class="nav-link" href="/sponsors" data-nav-path="/sponsors"><span class="nav-icon" aria-hidden="true">⌕</span><span>Sponsor Discovery</span></a>
            <a class="nav-link" href="/pipeline" data-nav-path="/pipeline"><span class="nav-icon" aria-hidden="true">▤</span><span>Sponsor Pipeline</span></a>
            <a class="nav-link" href="/email-studio" data-nav-path="/email-studio"><span class="nav-icon" aria-hidden="true">✉</span><span>Email Studio</span></a>
            <a class="nav-link" href="/outreach" data-nav-path="/outreach"><span class="nav-icon" aria-hidden="true">↗</span><span>Outreach Tracking</span></a>
            <a class="nav-link" href="/email-settings" data-nav-path="/email-settings">
                    <span class="nav-icon" aria-hidden="true">⚙</span>
                    <span>Email Settings</span>
            </a>
        </nav>
        <div class="sidebar-bottom">
            <div class="avatar" id="sidebarAvatar" aria-hidden="true">U</div>
            <div class="sidebar-user-copy"><strong id="sidebarUserName">Organizer</strong><small id="sidebarUserEmail">Signed-in workspace</small></div>
            <button class="sidebar-logout" id="sidebarLogout" type="button" title="Sign out" aria-label="Sign out">↪</button>
        </div>
    `;

    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    sidebar.querySelectorAll("[data-nav-path]").forEach(link => {
        const linkPath = link.getAttribute("data-nav-path");
        const active = path === linkPath || (linkPath === "/pipeline" && path.startsWith("/pipeline/"));
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
    });

    fetch("/api/auth/me", { headers: { "Accept": "application/json" }, credentials: "same-origin" })
        .then(async response => {
            if (!response.ok) return null;
            return response.json();
        })
        .then(data => {
            if (!data?.user) return;
            const displayName = data.user.name || data.user.email || "Organizer";
            const nameNode = document.getElementById("sidebarUserName");
            const emailNode = document.getElementById("sidebarUserEmail");
            const avatarNode = document.getElementById("sidebarAvatar");
            if (nameNode) nameNode.textContent = displayName;
            if (emailNode) emailNode.textContent = data.user.email || "Signed-in workspace";
            if (avatarNode) avatarNode.textContent = displayName.trim().charAt(0).toUpperCase() || "U";
        })
        .catch(() => {});

    document.getElementById("sidebarLogout")?.addEventListener("click", async () => {
        const button = document.getElementById("sidebarLogout");
        if (button) button.disabled = true;
        try {
            await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin", headers: { "Accept": "application/json" } });
        } finally {
            window.location.replace("/login");
        }
    });
})();
