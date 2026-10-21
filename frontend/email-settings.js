(() => {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const form = $("emailSettingsForm");
    const status = $("emailSettingsStatus");
    const badge = $("emailConnectionBadge");
    const saveButton = $("saveEmailSettings");
    const testButton = $("testEmailConnection");
    let hasSavedPassword = false;

    const presets = {
        gmail: {host: "smtp.gmail.com", port: 587, security: "STARTTLS"},
        outlook: {host: "smtp.office365.com", port: 587, security: "STARTTLS"},
        custom: null
    };

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: {"Accept": "application/json", ...(options.headers || {})},
            ...options
        });
        const data = await response.json().catch(() => ({}));
        if (response.status === 401) {
            window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
            throw new Error("Your session expired. Sign in again.");
        }
        if (!response.ok) throw new Error(String(data.detail || `HTTP ${response.status}`));
        return data;
    }

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.style.color = isError ? "#b42318" : "";
    }

    function applyPreset() {
        const preset = presets[$("providerPreset").value];
        if (!preset) return;
        $("smtpHost").value = preset.host;
        $("smtpPort").value = String(preset.port);
        $("smtpSecurity").value = preset.security;
    }

    async function loadSettings() {
        try {
            const data = await api("/api/email-settings");
            const settings = data.settings;
            if (settings) {
                $("fromName").value = settings.from_name || "";
                $("fromEmail").value = settings.from_email || "";
                $("smtpHost").value = settings.smtp_host || "";
                $("smtpPort").value = String(settings.smtp_port || 587);
                $("smtpSecurity").value = settings.smtp_security || "STARTTLS";
                $("smtpUsername").value = settings.smtp_username || "";
                hasSavedPassword = Boolean(settings.has_password);
                $("smtpPassword").required = !hasSavedPassword;
                $("smtpPassword").placeholder = hasSavedPassword
                    ? "Leave blank to keep the saved password"
                    : "Enter password / app password";
                $("passwordHint").textContent = hasSavedPassword
                    ? "A password is already saved securely. Leave this field blank to keep it, or enter a new one to replace it. The password is never returned to the browser."
                    : "The password is encrypted before it is stored. It is never sent back to the browser.";
                badge.textContent = "SETTINGS SAVED";
                testButton.disabled = false;
                if (settings.smtp_host === "smtp.gmail.com") $("providerPreset").value = "gmail";
                else if (settings.smtp_host === "smtp.office365.com") $("providerPreset").value = "outlook";
                else $("providerPreset").value = "custom";
            } else {
                badge.textContent = "NOT CONNECTED";
                $("providerPreset").value = "gmail";
                applyPreset();
                testButton.disabled = true;
            }
        } catch (error) {
            setStatus(`Could not load email settings: ${error.message}`, true);
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        saveButton.disabled = true;
        setStatus("Saving email account settings…");
        const payload = {
            from_name: $("fromName").value.trim(),
            from_email: $("fromEmail").value.trim(),
            smtp_host: $("smtpHost").value.trim(),
            smtp_port: Number($("smtpPort").value),
            smtp_security: $("smtpSecurity").value,
            smtp_username: $("smtpUsername").value.trim(),
            smtp_password: $("smtpPassword").value
        };
        try {
            const data = await api("/api/email-settings", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload)
            });
            hasSavedPassword = true;
            $("smtpPassword").value = "";
            $("smtpPassword").required = false;
            $("smtpPassword").placeholder = "Leave blank to keep the saved password";
            $("passwordHint").textContent = "A password is saved securely. Leave this field blank to keep it, or enter a new one to replace it.";
            badge.textContent = "SETTINGS SAVED";
            testButton.disabled = false;
            setStatus(data.message || "Email settings saved. Test the connection before sending.");
        } catch (error) {
            setStatus(`Could not save settings: ${error.message}`, true);
        } finally {
            saveButton.disabled = false;
        }
    });

    testButton.addEventListener("click", async () => {
        testButton.disabled = true;
        setStatus("Testing SMTP connection and login. No email will be sent…");
        try {
            const result = await api("/api/email-settings/test", {method: "POST"});
            badge.textContent = "CONNECTED";
            setStatus(result.message || "SMTP connection and login succeeded.");
        } catch (error) {
            badge.textContent = "CONNECTION FAILED";
            setStatus(`Connection test failed: ${error.message}`, true);
        } finally {
            testButton.disabled = false;
        }
    });

    $("providerPreset").addEventListener("change", applyPreset);
    loadSettings();
})();
