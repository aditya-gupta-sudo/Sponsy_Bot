(() => {
    "use strict";

    const view = document.body.dataset.view;
    const isStudio = view === "email-studio";
    const $ = id => document.getElementById(id);

    const fmtDate = value => {
        if (!value) return "—";

        const date = new Date(value);

        return Number.isNaN(date.getTime())
            ? String(value)
            : date.toLocaleString("en-IN", {
                dateStyle: "medium",
                timeStyle: "short"
            });
    };

    const cleanStatus = value =>
        String(value || "UNKNOWN").toUpperCase();

    const cleanReplyStatus = value =>
        String(value || "NOT_CHECKED").toUpperCase();

    function getReplyStatusLabel(record) {
        const replyStatus = cleanReplyStatus(record?.reply_status);
        const decision = String(
            record?.reply_decision || "UNCLASSIFIED"
        ).toUpperCase();

        if (replyStatus === "REPLIED") {
            return decision !== "UNCLASSIFIED"
                ? `Reply received · ${decision.replaceAll("_", " ")}`
                : "Reply received";
        }

        if (replyStatus === "AWAITING") {
            return "Awaiting reply";
        }

        if (replyStatus === "NOT_CHECKED") {
            return "Not checked";
        }

        return replyStatus.replaceAll("_", " ");
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            credentials: "same-origin",
            headers: {
                "Accept": "application/json",
                ...(options.headers || {})
            }
        });

        if (response.status === 401) {
            window.location.replace(
                `/login?next=${encodeURIComponent(
                    location.pathname + location.search
                )}`
            );

            throw new Error("Your session expired. Sign in again.");
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

    function text(tag, value, className) {
        const node = document.createElement(tag);

        if (value !== undefined && value !== null) {
            node.textContent = String(value);
        }

        if (className) {
            node.className = className;
        }

        return node;
    }

    function action(label, klass, handler) {
        const button = text("button", label, klass);
        button.type = "button";
        button.addEventListener("click", handler);
        return button;
    }

    function showError(node, error) {
        if (!node) return;

        node.textContent = error?.message || String(error);
        node.classList.add("error");
    }

    if (isStudio) {
        initStudio();
    } else {
        initOutreach();
    }

    // ============================================================
    // EMAIL STUDIO
    // ============================================================

    function initStudio() {
        const table = $("studioTableBody");
        const message = $("studioMessage");
        const search = $("studioSearch");
        const status = $("studioStatus");
        const sort = $("studioSort");
        const dialog = $("studioDraftDialog");
        const subject = $("studioSubject");
        const body = $("studioBody");
        const recipientCheck = $("studioConfirmRecipient");

        const recipientCheckLabel =
            recipientCheck.closest(".email-confirm-recipient") ||
            recipientCheck.closest("label");

        const save = $("studioSaveDraft");
        const send = $("studioSendDraft");

        const defaultSendLabel =
            send.textContent.trim() || "Approve & Send";

        let rows = [];
        let sender = "Email account not configured";
        let current = null;
        let isDirty = false;
        let initialQueryHandled = false;

        async function load() {
            message.textContent = "Loading outreach records…";
            message.classList.remove("error");

            try {
                const params = new URLSearchParams({
                    sort_by: sort.value
                });

                if (status.value) {
                    params.set("status", status.value);
                }

                if (search.value.trim()) {
                    params.set("search", search.value.trim());
                }

                const data = await api(`/api/outreach?${params}`);

                rows = Array.isArray(data.outreach)
                    ? data.outreach
                    : [];

                sender =
                    data.sender_email ||
                    "Email account not configured";

                const all = await api("/api/outreach?sort_by=newest");
                const allRows = all.outreach || [];

                $("studioDraftCount").textContent = String(
                    allRows.filter(
                        r => cleanStatus(r.status) === "DRAFT"
                    ).length
                );

                $("studioSentCount").textContent = String(
                    allRows.filter(
                        r => cleanStatus(r.status) === "SENT"
                    ).length
                );

                $("studioAttentionCount").textContent = String(
                    allRows.filter(
                        r => ["FAILED", "SENDING"].includes(
                            cleanStatus(r.status)
                        )
                    ).length
                );

                render();

                const query = search.value.trim();

                message.textContent =
                    `Showing ${rows.length} ` +
                    `${status.value
                        ? status.value.toLowerCase() + " "
                        : ""}record(s)` +
                    `${query ? ` matching “${query}”` : ""}.`;

                maybeOpenFromQuery();

            } catch (error) {
                table.replaceChildren();
                showError(message, error);
            }
        }

        function render() {
            table.replaceChildren();

            if (!rows.length) {
                const row = text("tr");
                const cell = text(
                    "td",
                    "No records match these filters."
                );

                cell.colSpan = 7;
                row.appendChild(cell);
                table.appendChild(row);
                return;
            }

            rows.forEach(record => {
                const row = text("tr");

                row.append(
                    text("td", fmtDate(record.created_at)),
                    text("td", record.company_name || "—"),
                    text("td", record.event_name || "—"),
                    text("td", record.recipient_email || "—"),
                    text("td", record.subject || "(No subject)")
                );

                const recordStatus = cleanStatus(record.status);
                const statusCell = text("td");

                statusCell.appendChild(
                    text(
                        "span",
                        recordStatus,
                        `pipeline-status-pill status-${recordStatus.toLowerCase()}`
                    )
                );

                row.appendChild(statusCell);

                const actions = text(
                    "td",
                    undefined,
                    "table-actions"
                );

                if (recordStatus === "DRAFT") {
                    actions.appendChild(
                        action(
                            "Edit & Review",
                            "button button-primary",
                            () => openRecord(record)
                        )
                    );
                } else {
                    actions.appendChild(
                        action(
                            "View Details",
                            "button button-secondary",
                            () => openRecord(record)
                        )
                    );
                }

                row.appendChild(actions);
                table.appendChild(row);
            });
        }

        // Open drafts and sent/failed records in the same modal.
        function openRecord(record) {
            current = record;
            isDirty = false;

            const recordStatus = cleanStatus(record.status);
            const isDraft = recordStatus === "DRAFT";
            const readOnly = !isDraft;

            recipientCheck.checked = false;

            subject.readOnly = readOnly;
            body.readOnly = readOnly;

            if (recipientCheckLabel) {
                recipientCheckLabel.hidden = readOnly;
            }

            save.hidden = readOnly;
            save.disabled = readOnly;

            if (isDraft) {
                send.textContent = defaultSendLabel;
                send.disabled = true;
            } else if (recordStatus === "SENT") {
                send.textContent = "Sent";
                send.disabled = true;
            } else if (recordStatus === "SENDING") {
                send.textContent = "Sending…";
                send.disabled = true;
            } else if (recordStatus === "FAILED") {
                send.textContent = "Failed";
                send.disabled = true;
            } else {
                send.textContent = recordStatus;
                send.disabled = true;
            }

            $("studioSender").textContent = sender;

            $("studioRecipient").textContent =
                record.recipient_email || "No recipient saved";

            $("studioDialogHeading").textContent = isDraft
                ? `Review draft #${record.email_id}`
                : `Email record #${record.email_id}`;

            $("studioDialogSubtitle").textContent =
                `${record.company_name || "Company"} · ` +
                `${record.event_name || "Event"}`;

            subject.value = record.subject || "";
            body.value = record.body || "";

            if (isDraft) {
                $("studioDraftStatus").textContent =
                    "Review the recipient and message. Save changes before sending.";

            } else if (recordStatus === "SENT") {
                $("studioDraftStatus").textContent = record.sent_at
                    ? `This email was sent on ${fmtDate(record.sent_at)}. The message is read-only.`
                    : "This email is marked SENT. The message is read-only.";

            } else if (recordStatus === "SENDING") {
                $("studioDraftStatus").textContent =
                    "This email is marked SENDING. Check Outreach Tracking for the final result before retrying.";

            } else if (recordStatus === "FAILED") {
                $("studioDraftStatus").textContent =
                    `This email failed to send. ${
                        record.error_message ||
                        "Review the send error in Outreach Tracking."
                    }`;

            } else {
                $("studioDraftStatus").textContent =
                    `This record has status ${recordStatus} and is read-only here.`;
            }

            if (typeof dialog.showModal === "function") {
                if (!dialog.open) {
                    dialog.showModal();
                }
            } else {
                dialog.setAttribute("open", "open");
            }
        }

        async function persist() {
            if (!current || cleanStatus(current.status) !== "DRAFT") {
                throw new Error("Only DRAFT records can be edited.");
            }

            const cleanSubject = subject.value.trim();
            const cleanBody = body.value.trim();

            if (!cleanSubject || !cleanBody) {
                throw new Error(
                    "Subject and email body are required."
                );
            }

            await api(
                `/api/events/${current.event_id}/outreach/${current.email_id}`,
                {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        subject: cleanSubject,
                        body: cleanBody
                    })
                }
            );

            current.subject = cleanSubject;
            current.body = cleanBody;
            isDirty = false;
        }

        save.addEventListener("click", async () => {
            if (!current || cleanStatus(current.status) !== "DRAFT") {
                return;
            }

            save.disabled = true;
            $("studioDraftStatus").textContent = "Saving draft…";

            try {
                await persist();

                send.disabled = !recipientCheck.checked;

                $("studioDraftStatus").textContent =
                    "Draft saved. It has not been sent.";

                await load();

            } catch (error) {
                showError($("studioDraftStatus"), error);

            } finally {
                save.disabled = false;
            }
        });

        send.addEventListener("click", async () => {
            if (
                !current ||
                cleanStatus(current.status) !== "DRAFT" ||
                send.disabled
            ) {
                return;
            }

            if (isDirty) {
                $("studioDraftStatus").textContent =
                    "Save your edits before sending.";
                return;
            }

            if (!recipientCheck.checked) {
                $("studioDraftStatus").textContent =
                    "Confirm the recipient address before sending.";
                return;
            }

            const recipient =
                current.recipient_email || "(missing recipient)";

            const confirmed = window.confirm(
                `Confirm email delivery\n\n` +
                `From: ${sender}\n` +
                `To: ${recipient}\n` +
                `Subject: ${subject.value.trim()}\n\n` +
                "Only continue if you have verified the recipient " +
                "and reviewed the full email. Send now?"
            );

            if (!confirmed) {
                return;
            }

            send.disabled = true;
            save.disabled = true;

            $("studioDraftStatus").textContent =
                `Sending to ${recipient}…`;

            try {
                const result = await api(
                    `/api/events/${current.event_id}/outreach/${current.email_id}/send`,
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

                current.status = result.status || "SENT";
                current.sent_at = result.sent_at || current.sent_at;

                await load();

                // Refresh modal with the final record status.
                const updatedRecord = rows.find(
                    r => Number(r.email_id) === Number(current.email_id)
                );

                if (updatedRecord) {
                    current = updatedRecord;
                }

                openRecord(current);

            } catch (error) {
                showError($("studioDraftStatus"), error);

                $("studioDraftStatus").textContent +=
                    " Check Outreach Tracking before retrying to avoid duplicates.";

            } finally {
                save.disabled = false;
            }
        });

        function closeDialog() {
            if (dialog.open) {
                dialog.close();
            } else {
                dialog.removeAttribute("open");
            }

            current = null;
            isDirty = false;

            recipientCheck.checked = false;
            subject.readOnly = false;
            body.readOnly = false;

            if (recipientCheckLabel) {
                recipientCheckLabel.hidden = false;
            }

            save.hidden = false;
            save.disabled = false;

            send.textContent = defaultSendLabel;
            send.disabled = true;
        }

        $("studioCloseIcon").addEventListener(
            "click",
            closeDialog
        );

        $("studioCancelDraft").addEventListener(
            "click",
            closeDialog
        );

        dialog.addEventListener("cancel", event => {
            event.preventDefault();
            closeDialog();
        });

        recipientCheck.addEventListener("change", () => {
            send.disabled =
                !recipientCheck.checked || !current || isDirty;
        });

        for (const field of [subject, body]) {
            field.addEventListener("input", () => {
                isDirty = true;
                send.disabled = true;

                $("studioDraftStatus").textContent =
                    "Draft changed. Save before sending.";
            });
        }

        search.addEventListener("input", debounce(load, 250));
        status.addEventListener("change", load);
        sort.addEventListener("change", load);

        $("refreshStudio").addEventListener("click", load);

        function maybeOpenFromQuery() {
            if (initialQueryHandled) {
                return;
            }

            initialQueryHandled = true;

            const id = Number(
                new URLSearchParams(location.search).get("email_id")
            );

            if (id > 0) {
                const record = rows.find(
                    r => Number(r.email_id) === id
                );

                if (record) {
                    openRecord(record);
                }
            }
        }

        load();
    }

    // ============================================================
    // OUTREACH TRACKING AND GMAIL REPLY DETECTION
    // ============================================================

    function initOutreach() {
        const table = $("outreachTableBody");
        const message = $("outreachMessage");
        const search = $("outreachSearchInput");
        const status = $("outreachStatusFilter");
        const sort = $("outreachSortFilter");
        const dialog = $("outreachDetailDialog");

        const connectGmailButton = $("connectGmailInbox");
        const checkRepliesButton = $("checkRepliesButton");
        const gmailInboxStatus = $("gmailInboxStatus");

        const replyBox = $("outreachReplyBox");
        const replyDetails = $("outreachReplyDetails");
        const replyDecision = $("outreachReplyDecision");
        const saveReplyDecisionButton = $("saveReplyDecision");

        let activeDetailRecord = null;
        let rows = [];
        let sender = "Email account not configured";
        let initialQueryHandled = false;
        let gmailConnected = false;

        async function refreshGmailStatus() {
            if (
                !gmailInboxStatus ||
                !checkRepliesButton ||
                !connectGmailButton
            ) {
                return;
            }

            try {
                const data = await api("/api/gmail-inbox/status");
                gmailConnected = Boolean(data.connected);

                if (gmailConnected) {
                    gmailInboxStatus.textContent =
                        `Connected inbox: ${data.gmail_email}. ` +
                        `Last checked: ${
                            data.last_checked_at
                                ? fmtDate(data.last_checked_at)
                                : "Never"
                        }.`;

                    connectGmailButton.textContent = "Reconnect Gmail";
                    checkRepliesButton.disabled = false;
                } else {
                    gmailInboxStatus.textContent =
                        "Connect Gmail to check incoming sponsor replies.";

                    connectGmailButton.textContent = "Connect Gmail Inbox";
                    checkRepliesButton.disabled = true;
                }
            } catch (error) {
                gmailConnected = false;

                gmailInboxStatus.textContent =
                    `Could not check Gmail status: ${error.message}`;

                checkRepliesButton.disabled = true;
            }
        }

        async function checkReplies() {
            if (!checkRepliesButton) return;

            checkRepliesButton.disabled = true;
            message.classList.remove("error");
            message.textContent = "Checking the connected Gmail inbox…";

            try {
                const result = await api(
                    "/api/outreach/check-replies",
                    { method: "POST" }
                );

                await load();
                await refreshGmailStatus();

                message.classList.remove("error");
                message.textContent =
                    result.message || "Reply check finished.";

            } catch (error) {
                showError(message, error);

            } finally {
                checkRepliesButton.disabled = !gmailConnected;
            }
        }

        async function saveReplyDecision() {
            if (
                !activeDetailRecord ||
                cleanReplyStatus(activeDetailRecord.reply_status) !== "REPLIED" ||
                !replyDecision ||
                !saveReplyDecisionButton
            ) {
                return;
            }

            saveReplyDecisionButton.disabled = true;

            try {
                await api(
                    `/api/outreach/${activeDetailRecord.email_id}/reply-decision`,
                    {
                        method: "PATCH",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            decision: replyDecision.value
                        })
                    }
                );

                await load();

                message.classList.remove("error");
                message.textContent = "Reply outcome saved.";

            } catch (error) {
                showError(message, error);

            } finally {
                saveReplyDecisionButton.disabled =
                    !activeDetailRecord ||
                    cleanReplyStatus(activeDetailRecord.reply_status) !== "REPLIED";
            }
        }

        async function load() {
            message.textContent = "Loading outreach records…";
            message.classList.remove("error");

            try {
                const params = new URLSearchParams({
                    sort_by: sort.value
                });

                if (status.value) {
                    params.set("status", status.value);
                }

                if (search.value.trim()) {
                    params.set("search", search.value.trim());
                }

                const data = await api(`/api/outreach?${params}`);

                rows = data.outreach || [];
                sender = data.sender_email || "Email account not configured";

                const all = await api(
                    "/api/outreach?sort_by=newest"
                );

                const allRows = all.outreach || [];

                $("outreachTotal").textContent =
                    String(allRows.length);

                $("outreachSent").textContent = String(
                    allRows.filter(
                        r => cleanStatus(r.status) === "SENT"
                    ).length
                );

                $("outreachDrafts").textContent = String(
                    allRows.filter(
                        r => cleanStatus(r.status) === "DRAFT"
                    ).length
                );

                $("outreachAttention").textContent = String(
                    allRows.filter(
                        r => ["FAILED", "SENDING"].includes(
                            cleanStatus(r.status)
                        )
                    ).length
                );

                render();

                // If the detail dialog is open, refresh its reply data too.
                if (activeDetailRecord && dialog.open) {
                    const refreshedRecord = rows.find(
                        item =>
                            Number(item.email_id) ===
                            Number(activeDetailRecord.email_id)
                    );

                    if (refreshedRecord) {
                        activeDetailRecord = refreshedRecord;
                        populateReplyDetails(refreshedRecord);
                    }
                }

                message.textContent =
                    `Showing ${rows.length} of ${allRows.length} outreach record(s).`;

                maybeOpenFromQuery();

            } catch (error) {
                table.replaceChildren();
                showError(message, error);
            }
        }

        function render() {
            table.replaceChildren();

            if (!rows.length) {
                const row = text("tr");

                const cell = text(
                    "td",
                    "No outreach records match these filters."
                );

                cell.colSpan = 7;
                row.appendChild(cell);
                table.appendChild(row);
                return;
            }

            rows.forEach(record => {
                const row = text("tr");

                row.append(
                    text("td", fmtDate(record.created_at)),
                    text("td", record.company_name || "—"),
                    text("td", record.event_name || "—"),
                    text("td", record.recipient_email || "—"),
                    text("td", record.subject || "(No subject)")
                );

                const recordStatus = cleanStatus(record.status);
                const statusCell = text("td");

                statusCell.appendChild(
                    text(
                        "span",
                        recordStatus,
                        `pipeline-status-pill status-${recordStatus.toLowerCase()}`
                    )
                );

                // Display reply state underneath SENT.
                if (recordStatus === "SENT") {
                    const replyState = cleanReplyStatus(
                        record.reply_status
                    );

                    const replyBadge = text(
                        "small",
                        getReplyStatusLabel(record),
                        `outreach-reply-status reply-${replyState.toLowerCase()}`
                    );

                    replyBadge.style.display = "block";
                    replyBadge.style.marginTop = "5px";
                    replyBadge.style.fontSize = "0.8em";
                    replyBadge.style.color = replyState === "REPLIED"
                        ? "#087443"
                        : "#687991";

                    statusCell.appendChild(replyBadge);
                }

                row.appendChild(statusCell);

                const actions = text(
                    "td",
                    undefined,
                    "table-actions"
                );

                actions.appendChild(
                    action(
                        "Details",
                        "button button-secondary",
                        () => openDetails(record)
                    )
                );

                if (recordStatus === "DRAFT") {
                    actions.appendChild(
                        action(
                            "Edit Draft",
                            "button button-primary",
                            () => {
                                window.location.href =
                                    `/email-studio?email_id=${encodeURIComponent(
                                        record.email_id
                                    )}`;
                            }
                        )
                    );
                }

                // Do not delete records while a send could be in progress.
                if (recordStatus !== "SENDING") {
                    actions.appendChild(
                        action(
                            "Delete",
                            "button button-secondary",
                            () => deleteRecord(record)
                        )
                    );
                }

                row.appendChild(actions);
                table.appendChild(row);
            });
        }

        async function deleteRecord(record) {
            const isSent = cleanStatus(record.status) === "SENT";

            const warning = isSent
                ? "\n\nThis removes the local tracking record only. " +
                  "It cannot recall an email already sent."
                : "";

            const confirmed = window.confirm(
                `Permanently delete outreach record #${record.email_id}?\n\n` +
                `Recipient: ${record.recipient_email || "Unknown"}\n` +
                `Subject: ${record.subject || "(No subject)"}\n` +
                `Status: ${cleanStatus(record.status)}\n\n` +
                "This action cannot be undone." +
                warning
            );

            if (!confirmed) return;

            message.classList.remove("error");
            message.textContent =
                `Deleting outreach record #${record.email_id}…`;

            try {
                await api(
                    `/api/outreach/${encodeURIComponent(record.email_id)}`,
                    { method: "DELETE" }
                );

                await load();

                message.classList.remove("error");
                message.textContent =
                    `Outreach record #${record.email_id} was permanently deleted.`;

            } catch (error) {
                showError(message, error);
            }
        }

        function populateReplyDetails(record) {
            if (
                !replyBox ||
                !replyDetails ||
                !replyDecision ||
                !saveReplyDecisionButton
            ) {
                return;
            }

            const recordStatus = cleanStatus(record.status);
            const replyStatus = cleanReplyStatus(record.reply_status);
            const hasReply = replyStatus === "REPLIED";

            replyBox.hidden = recordStatus !== "SENT";

            replyDecision.value =
                record.reply_decision || "UNCLASSIFIED";

            replyDecision.disabled = !hasReply;
            saveReplyDecisionButton.disabled = !hasReply;

            replyDetails.style.whiteSpace = "pre-wrap";

            if (recordStatus !== "SENT") {
                replyDetails.textContent =
                    "Reply tracking is available after an email is sent.";
                return;
            }

            if (hasReply) {
                replyDetails.textContent = [
                    "Status: Reply received",
                    `Received: ${fmtDate(record.reply_received_at)}`,
                    `From: ${record.reply_from_email || "Unknown"}`,
                    `Subject: ${record.reply_subject || "(No subject)"}`,
                    `Preview: ${record.reply_snippet || "(No preview available)"}`,
                    `Outcome: ${String(
                        record.reply_decision || "UNCLASSIFIED"
                    ).replaceAll("_", " ")}`
                ].join("\n");

            } else if (replyStatus === "AWAITING") {
                replyDetails.textContent =
                    "Status: Awaiting reply. Run Check Replies to search the connected Gmail inbox again.";

            } else {
                replyDetails.textContent =
                    "Status: Not checked. Connect Gmail and click Check Replies to search for a matching response.";
            }
        }

        function openDetails(record) {
            activeDetailRecord = record;

            $("outreachDetailHeading").textContent =
                `Email record #${record.email_id}`;

            $("outreachDetailSubtitle").textContent =
                `${record.company_name || "Company"} · ` +
                `${record.event_name || "Event"}`;

            $("outreachDetailSender").textContent = sender;

            $("outreachDetailRecipient").textContent =
                record.recipient_email || "No recipient saved";

            $("outreachDetailEvent").textContent =
                record.event_name || "—";

            $("outreachDetailCompany").textContent =
                record.company_name || "—";

            const detailStatus = cleanStatus(record.status);

            $("outreachDetailStatus").textContent = detailStatus;

            $("outreachDetailCreated").textContent =
                fmtDate(record.created_at);

            $("outreachDetailApproved").textContent =
                fmtDate(record.approved_at);

            $("outreachDetailSent").textContent =
                fmtDate(record.sent_at);

            $("outreachDetailSubject").value =
                record.subject || "";

            $("outreachDetailBody").value =
                record.body || "";

            $("outreachDetailError").textContent =
                record.error_message || "No recorded send error.";

            populateReplyDetails(record);

            const openStudioLink = $("openDraftInStudio");

            if (openStudioLink) {
                if (detailStatus === "SENT") {
                    openStudioLink.textContent = "Sent";
                    openStudioLink.hidden = false;
                    openStudioLink.removeAttribute("href");
                    openStudioLink.setAttribute("aria-disabled", "true");
                    openStudioLink.tabIndex = -1;
                    openStudioLink.style.pointerEvents = "none";

                } else if (detailStatus === "DRAFT") {
                    openStudioLink.textContent = "Open Email Studio";
                    openStudioLink.hidden = false;

                    openStudioLink.href =
                        `/email-studio?email_id=${encodeURIComponent(
                            record.email_id
                        )}`;

                    openStudioLink.removeAttribute("aria-disabled");
                    openStudioLink.removeAttribute("tabindex");
                    openStudioLink.style.pointerEvents = "";

                } else {
                    openStudioLink.hidden = true;
                    openStudioLink.removeAttribute("href");
                }
            }

            if (typeof dialog.showModal === "function") {
                if (!dialog.open) {
                    dialog.showModal();
                }
            } else {
                dialog.setAttribute("open", "open");
            }
        }

        function closeDetails() {
            if (dialog.open) {
                dialog.close();
            } else {
                dialog.removeAttribute("open");
            }

            activeDetailRecord = null;
        }

        $("closeOutreachDetailIcon").addEventListener(
            "click",
            closeDetails
        );

        $("closeOutreachDetail").addEventListener(
            "click",
            closeDetails
        );

        dialog.addEventListener("cancel", event => {
            event.preventDefault();
            closeDetails();
        });

        search.addEventListener("input", debounce(load, 250));
        status.addEventListener("change", load);
        sort.addEventListener("change", load);

        $("refreshOutreach").addEventListener("click", load);

        // These handlers were missing in the uploaded version.
        if (checkRepliesButton) {
            checkRepliesButton.addEventListener("click", checkReplies);
        }

        if (saveReplyDecisionButton) {
            saveReplyDecisionButton.addEventListener(
                "click",
                saveReplyDecision
            );
        }

        // The connect control is an anchor; its href starts OAuth.
        const query = new URLSearchParams(window.location.search);

        if (query.get("gmail_connected") === "1") {
            if (gmailInboxStatus) {
                gmailInboxStatus.textContent =
                    "Gmail inbox connected. You can now check sponsor replies.";
            }
        } else if (query.get("gmail_error")) {
            if (gmailInboxStatus) {
                gmailInboxStatus.textContent =
                    `Gmail connection was not completed: ${query.get("gmail_error")}`;
            }
        }

        function maybeOpenFromQuery() {
            if (initialQueryHandled) return;

            initialQueryHandled = true;

            const id = Number(
                new URLSearchParams(location.search).get("email_id")
            );

            if (id > 0) {
                const row = rows.find(
                    r => Number(r.email_id) === id
                );

                if (row) openDetails(row);
            }
        }

        load();
        refreshGmailStatus();
    }

    function debounce(fn, wait) {
        let handle;

        return (...args) => {
            window.clearTimeout(handle);

            handle = window.setTimeout(
                () => fn(...args),
                wait
            );
        };
    }
})();