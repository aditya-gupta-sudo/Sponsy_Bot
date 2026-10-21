(() => {
    "use strict";

    const form = document.getElementById("authForm");
    const nameWrap = document.getElementById("nameFieldWrap");
    const nameInput = document.getElementById("authName");
    const emailInput = document.getElementById("authEmail");
    const passwordInput = document.getElementById("authPassword");
    const submitButton = document.getElementById("authSubmitButton");
    const switchButton = document.getElementById("switchAuthMode");
    const switchPrompt = document.getElementById("switchPrompt");
    const heading = document.getElementById("authHeading");
    const modeLabel = document.getElementById("authModeLabel");
    const passwordHint = document.getElementById("passwordHint");
    const message = document.getElementById("authMessage");
    let mode = "login";

    const query = new URLSearchParams(window.location.search);
    const requestedNext = query.get("next");
    const nextPath = requestedNext && requestedNext.startsWith("/") && !requestedNext.startsWith("//")
        ? requestedNext
        : "/";
    const errors = {
        google_not_configured: "Google sign-in is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.",
        google_email_unverified: "Google did not return a verified email address.",
        google_signin_failed: "Google sign-in could not be completed. Check the OAuth callback URL and server logs."
    };
    if (query.get("error") && errors[query.get("error")]) {
        message.textContent = errors[query.get("error")];
        message.classList.add("error");
    }

    // If a valid session already exists, go straight to the workspace.
    fetch("/api/auth/me").then(response => {
        if (response.ok) window.location.replace(nextPath);
    }).catch(() => {});

    function setMode(nextMode) {
        mode = nextMode;
        const registering = mode === "register";
        nameWrap.hidden = !registering;
        nameInput.required = registering;
        passwordHint.hidden = !registering;
        passwordInput.autocomplete = registering ? "new-password" : "current-password";
        passwordInput.minLength = registering ? 10 : 1;
        heading.textContent = registering ? "Create your account" : "Sign in to SponsyBot";
        modeLabel.textContent = registering ? "GET STARTED" : "WELCOME BACK";
        submitButton.textContent = registering ? "Create Account" : "Sign In";
        switchPrompt.textContent = registering ? "Already have an account?" : "New to SponsyBot?";
        switchButton.textContent = registering ? "Sign in" : "Create an account";
        message.textContent = "";
        message.className = "auth-message";
    }

    switchButton.addEventListener("click", () => setMode(mode === "login" ? "register" : "login"));
    document.getElementById("googleLoginButton").addEventListener("click", () => {
        window.location.href = `/auth/google?next=${encodeURIComponent(nextPath)}`;
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();
        message.textContent = "";
        message.className = "auth-message";

        if (mode === "register" && passwordInput.value.length < 10) {
            message.textContent = "Choose a password with at least 10 characters.";
            message.classList.add("error");
            return;
        }

        submitButton.disabled = true;
        submitButton.textContent = mode === "register" ? "Creating account…" : "Signing in…";
        try {
            const endpoint = mode === "register" ? "/api/auth/register" : "/api/auth/login";
            const payload = {
                email: emailInput.value.trim(),
                password: passwordInput.value
            };
            if (mode === "register") payload.name = nameInput.value.trim();

            const response = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify(payload),
                credentials: "same-origin"
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                let detail = data.detail || `Request failed with HTTP ${response.status}`;
                if (Array.isArray(detail)) detail = detail.map(item => item.msg || "Invalid field").join("; ");
                throw new Error(detail);
            }
            window.location.replace(nextPath);
        } catch (error) {
            message.textContent = error.message || "Authentication failed.";
            message.classList.add("error");
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = mode === "register" ? "Create Account" : "Sign In";
        }
    });
})();
